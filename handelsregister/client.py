import os
import json
import time
import logging
import httpx
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from glob import glob

try:
    from tqdm import tqdm
except ImportError as exc:
    raise ImportError("tqdm is required for this package to run. Please install it.") from exc

from .version import __version__
from .exceptions import HandelsregisterError, InvalidResponseError, AuthenticationError

logger = logging.getLogger(__name__)

BASE_URL = "https://handelsregister.ai/api/v1/"

class Handelsregister:
    """
    A modern Python client for interacting with handelsregister.ai.

    Usage:
        from handelsregister import Handelsregister
        
        client = Handelsregister(api_key="YOUR_API_KEY")
        result = client.fetch_organization(q="OroraTech GmbH aus München")
        print(result)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        base_url: str = BASE_URL,
        cache_enabled: bool = True,
        rate_limit: float = 0.0,
    ) -> None:
        """
        Initialize the Handelsregister client.

        :param api_key: The API key provided by handelsregister.ai (required if
                        HANDELSREGISTER_API_KEY env var is not set).
        :param timeout: Timeout for HTTP requests (in seconds).
        :param base_url: Base URL for the handelsregister.ai API.
        """
        # Support reading the API key from environment if none provided
        env_api_key = os.getenv("HANDELSREGISTER_API_KEY", "")
        if not api_key:
            api_key = env_api_key

        if not api_key:
            raise AuthenticationError(
                "An API key is required to use the Handelsregister client. "
                "Either pass it explicitly or set HANDELSREGISTER_API_KEY."
            )

        self.api_key = api_key
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "User-Agent": f"handelsregister-python-client/{__version__}"
        }

        self.cache_enabled = cache_enabled
        self.rate_limit = rate_limit
        self._cache: Dict[tuple, Dict[str, Any]] = {}
        self._last_request_time = 0.0

        logger.debug("Handelsregister client initialized with base_url=%s", self.base_url)

    def fetch_organization(
        self,
        q: str,
        features: Optional[List[str]] = None,
        ai_search: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Fetch organization data from handelsregister.ai.

        :param q: The search query (company name, location, etc.). (required)
        :param features: A list of desired feature flags, e.g.:
                         ["related_persons", "publications", "financial_kpi",
                          "balance_sheet_accounts", "profit_and_loss_account"]
        :param ai_search: If "on-default", uses the AI-based search (optional).
        :param kwargs: Additional query parameters that the API supports.
        :return: Parsed JSON response as a Python dictionary.
        :raises HandelsregisterError: For any request or response failures.
        """
        if not q:
            raise ValueError("Parameter 'q' is required.")

        logger.debug("Fetching organization data for q=%s, features=%s, ai_search=%s", q, features, ai_search)

        # Construct query parameters
        params = {
            "api_key": self.api_key,
            "q": q
        }

        if features:
            # If the API expects multiple 'feature' parameters:
            for feature in features:
                params.setdefault("feature", []).append(feature)

        if ai_search:
            params["ai_search"] = ai_search

        # Merge any additional user-supplied kwargs into params
        for key, value in kwargs.items():
            params[key] = value

        url = f"{self.base_url}/fetch-organization"

        cache_key = (
            q,
            tuple(sorted(features)) if features else (),
            ai_search,
            tuple(sorted(kwargs.items())),
        )

        if self.cache_enabled and cache_key in self._cache:
            logger.debug("Returning cached result for %s", q)
            return self._cache[cache_key]

        # Rate limiting
        if self.rate_limit > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.rate_limit:
                time.sleep(self.rate_limit - elapsed)

        # Up to 3 retries with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    logger.debug("Making GET request to %s with params=%s", url, params)
                    response = client.get(url, headers=self.headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    self._last_request_time = time.time()
                    if self.cache_enabled:
                        self._cache[cache_key] = data
                    return data

            except httpx.RequestError as exc:
                logger.warning("Request error (attempt %d/%d): %s", attempt + 1, max_retries, exc)
                time.sleep(2 ** attempt)
                if attempt == max_retries - 1:
                    raise HandelsregisterError(f"Error while requesting data: {exc}") from exc

            except httpx.HTTPStatusError as exc:
                logger.warning("HTTP status error (attempt %d/%d): %s", attempt + 1, max_retries, exc)
                if exc.response.status_code == 401:
                    raise AuthenticationError("Invalid API key or unauthorized access.") from exc
                time.sleep(2 ** attempt)
                if attempt == max_retries - 1:
                    raise HandelsregisterError(f"HTTP error occurred: {exc}") from exc

            except ValueError as exc:
                # Could not parse JSON
                logger.error("Invalid JSON response: %s", exc)
                raise InvalidResponseError(f"Received non-JSON response: {exc}") from exc

    def fetch_organization_df(self, *args, **kwargs):
        """Fetch organization data and return a pandas DataFrame."""
        data = self.fetch_organization(*args, **kwargs)
        import pandas as pd
        return pd.json_normalize(data)

    def enrich(
        self,
        file_path: str = "",
        input_type: str = "json",
        query_properties: Dict[str, str] = None,
        snapshot_dir: str = "",
        snapshot_steps: int = 10,
        snapshots: int = 120,
        params: Dict[str, Any] = None
    ):
        """
        Enrich a local data file with Handelsregister.ai results.

        Supported input formats: JSON, CSV and XLSX.

        The process:
          1. If there's a snapshot, load it.
          2. Load the current file.
          3. Merge them:
             - Keep previously enriched items (including ones removed from the file).
             - Add or update items from the file.
          4. Only re-process items that appear in the file and have not been enriched.
          5. Take periodic snapshots to allow resuming.
        
        :param file_path: Path to the input file.
        :param input_type: Type of input file ('json', 'csv' or 'xlsx').
        :param query_properties: Dict describing which fields are combined to form 'q'.
                                 Example: {'name': 'company_name', 'location': 'city'}
        :param snapshot_dir: Directory in which to store intermediate snapshots.
        :param snapshot_steps: Create a snapshot after processing this many new items.
        :param snapshots: Keep at most this many historical snapshots.
        :param params: Additional parameters for fetch_organization (e.g. features, ai_search).
        """
        input_type = input_type.lower()
        if input_type not in {"json", "csv", "xlsx"}:
            raise ValueError("enrich() supports only 'json', 'csv' or 'xlsx' input_type.")

        if not file_path:
            raise ValueError("file_path is required for enrich().")

        if query_properties is None:
            query_properties = {}

        if params is None:
            params = {}

        snapshot_path = Path(snapshot_dir) if snapshot_dir else None
        if snapshot_path:
            snapshot_path.mkdir(parents=True, exist_ok=True)

        logger.debug(
            "Starting enrichment process with file_path=%s, snapshot_dir=%s",
            file_path, snapshot_dir
        )

        # ------------------------------------------------
        # 1. Load snapshot if available
        # ------------------------------------------------
        snapshot_data = []
        if snapshot_path:
            latest_snapshot = self._get_latest_snapshot(snapshot_path)
            if latest_snapshot:
                logger.info("Continuing from existing snapshot: %s", latest_snapshot)
                with open(latest_snapshot, "r", encoding="utf-8") as f:
                    snapshot_data = json.load(f)
            else:
                logger.info("No existing snapshot found.")

        # ------------------------------------------------
        # 2. Load the current file
        # ------------------------------------------------
        if input_type == "json":
            with open(file_path, "r", encoding="utf-8") as f:
                file_data = json.load(f)
                if not isinstance(file_data, list):
                    raise ValueError("JSON data must be a list of items for enrichment.")
        else:
            import pandas as pd
            if input_type == "csv":
                df = pd.read_csv(file_path)
            else:  # xlsx
                df = pd.read_excel(file_path)
            file_data = df.to_dict(orient="records")

        logger.debug("Loaded %d items from file '%s'.", len(file_data), file_path)

        # ------------------------------------------------
        # 3. Merge snapshot_data + file_data
        # ------------------------------------------------
        # We'll use a dictionary keyed by a "unique key" derived from query_properties.
        merged_data = self._merge_data(snapshot_data, file_data, query_properties)

        logger.debug("Merged dataset size: %d items (includes removed items from snapshots).", len(merged_data))

        # ------------------------------------------------
        # 4. Only re-process items that are both in the file and not yet enriched
        # ------------------------------------------------
        processed_so_far = 0  # number of items that won't need re-processing
        for item in merged_data:
            if item.get("_handelsregister_result") is not None:
                processed_so_far += 1

        logger.debug("Already processed %d items (via snapshots).", processed_so_far)

        # Prepare progress bar
        total_file_items = sum(1 for x in merged_data if x["_in_file"])  # how many are in the new file
        already_done = sum(1 for x in merged_data if x["_in_file"] and x.get("_handelsregister_result") is not None)

        logger.info(
            "Enriching %d new items (file has %d total, %d already enriched).",
            total_file_items - already_done, total_file_items, already_done
        )

        current_step_count = 0  # track how many new items we've processed since last snapshot
        with tqdm(total=total_file_items, initial=already_done, desc="Enriching data") as pbar:
            for item in merged_data:
                # Only enrich if item is in the file and not enriched
                if not item["_in_file"]:
                    # It's an old item removed from the current file, keep but skip re-processing
                    continue
                if "_handelsregister_result" in item and item["_handelsregister_result"] is not None:
                    # Already enriched from snapshot
                    continue

                # Build q parameter from query_properties
                q_string = self._build_q_string(item, query_properties)
                if not q_string:
                    logger.debug("Skipping item because q-string is empty: %s", item)
                    item["_handelsregister_result"] = None
                else:
                    # Call the API
                    logger.debug("Enriching new item with q=%s", q_string)
                    api_response = self.fetch_organization(q=q_string, **params)
                    item["_handelsregister_result"] = api_response

                # Update progress
                pbar.update(1)
                current_step_count += 1

                # Snapshot logic: create snapshot every 'snapshot_steps' new items processed
                if snapshot_path and current_step_count % snapshot_steps == 0:
                    self._create_snapshot(merged_data, snapshot_path, snapshots)

        # ------------------------------------------------
        # 5. Final snapshot after the loop, if requested
        # ------------------------------------------------
        if snapshot_path:
            self._create_snapshot(merged_data, snapshot_path, snapshots)

        logger.info("Enrichment process completed.")

    def enrich_dataframe(
        self,
        df,
        query_properties: Dict[str, str] = None,
        params: Dict[str, Any] = None,
    ):
        """Enrich a pandas DataFrame with Handelsregister.ai results."""
        import pandas as pd

        if query_properties is None:
            query_properties = {}
        if params is None:
            params = {}

        records = df.to_dict(orient="records")
        enriched = []
        for record in records:
            q_string = self._build_q_string(record, query_properties)
            if q_string:
                result = self.fetch_organization(q=q_string, **params)
            else:
                result = None
            record["_handelsregister_result"] = result
            enriched.append(record)

        return pd.DataFrame(enriched)

    # -------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------

    def _build_q_string(self, item: dict, query_properties: Dict[str, str]) -> str:
        """
        Given a single item and the query_properties mapping,
        build the 'q' string (space-separated combination of fields).
        """
        parts = []
        for field_key in query_properties.values():
            val = str(item.get(field_key, "")).strip()
            if val:
                parts.append(val)
        return " ".join(parts).strip()

    def _merge_data(
        self,
        snapshot_data: List[dict],
        file_data: List[dict],
        query_properties: Dict[str, str]
    ) -> List[dict]:
        """
        Merge existing snapshot items with new file items, preserving:
          - Any items that were in the snapshot (even if removed from file).
          - Overwriting or adding items from the new file.
          - Retaining already-enriched data whenever possible.
        
        We identify items by a "key" built from query_properties.
        If query_properties is empty, we treat all items as distinct, 
        which can lead to duplicates unless the user manages IDs or fields.

        Items get a boolean `_in_file` indicating if they are in the new file.
        """

        # Build a dict keyed by item "signature"
        merged_dict = {}

        # 1. Insert snapshot items
        for snap_item in snapshot_data:
            key = self._build_key(snap_item, query_properties)
            merged_dict[key] = snap_item

        # 2. Incorporate file items
        #    - If key already exists, update with new fields from file but keep _handelsregister_result if present
        #    - If key doesn't exist, add it
        #    - Mark items as "_in_file": True
        for file_item in file_data:
            key = self._build_key(file_item, query_properties)
            if key in merged_dict:
                existing = merged_dict[key]
                enriched_result = existing.get("_handelsregister_result")
                # Overwrite with the new file item
                merged_dict[key] = file_item
                # Preserve the old result if it existed
                if enriched_result is not None:
                    merged_dict[key]["_handelsregister_result"] = enriched_result
            else:
                merged_dict[key] = file_item

            merged_dict[key]["_in_file"] = True

        # 3. For any items leftover from the snapshot that aren't in the new file, keep them but mark _in_file=False
        for key, item in merged_dict.items():
            if "_in_file" not in item:
                item["_in_file"] = False

        # 4. Convert merged_dict back to a list in a stable order
        #    The final list order will be:
        #       - snapshot_data items (original order),
        #       - plus any new items from file_data
        #       - plus anything leftover not in either (unlikely in typical usage).
        final_list = []
        used_keys = set()

        # Add items from the snapshot_data in original order if present in merged_dict
        for snap_item in snapshot_data:
            key = self._build_key(snap_item, query_properties)
            if key in merged_dict and key not in used_keys:
                final_list.append(merged_dict[key])
                used_keys.add(key)

        # Then add new items from the file that weren't in snapshot_data
        for file_item in file_data:
            key = self._build_key(file_item, query_properties)
            if key in merged_dict and key not in used_keys:
                final_list.append(merged_dict[key])
                used_keys.add(key)

        # Finally, if there are any leftover items in merged_dict not in snapshot_data or file_data, add them:
        for key, item in merged_dict.items():
            if key not in used_keys:
                final_list.append(item)
                used_keys.add(key)

        return final_list

    def _build_key(self, item: dict, query_properties: Dict[str, str]) -> tuple:
        """
        Build a tuple key based on query_properties. 
        If query_properties is empty, returns a placeholder key 
        that effectively treats every item as distinct.
        """
        if not query_properties:
            # No user-defined properties => treat each item as unique
            # Could also look for a built-in 'id' field, etc.
            return id(item)
        # If we have fields, build a tuple from those fields
        return tuple(item.get(field_name, "") for field_name in query_properties.values())

    def _create_snapshot(self, data, snapshot_path: Path, max_snapshots: int):
        """Creates a JSON snapshot of the data and prunes old snapshots."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_file = snapshot_path / f"snapshot_{timestamp}.json"
        logger.debug("Creating snapshot: %s", snapshot_file)

        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Prune old snapshots if we exceed max_snapshots
        existing_snapshots = sorted(glob(str(snapshot_path / "snapshot_*.json")))
        if len(existing_snapshots) > max_snapshots:
            to_remove = existing_snapshots[:-max_snapshots]
            for old_snapshot in to_remove:
                logger.debug("Removing old snapshot: %s", old_snapshot)
                os.remove(old_snapshot)

    def _get_latest_snapshot(self, snapshot_path: Path) -> Optional[str]:
        """Return the path to the latest snapshot, or None if none exist."""
        existing_snapshots = sorted(glob(str(snapshot_path / "snapshot_*.json")))
        if existing_snapshots:
            return existing_snapshots[-1]
        return None