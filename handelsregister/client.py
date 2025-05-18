import os
import json
import time
import logging
import hashlib
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
        timeout: float = 90.0,
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
        params: Dict[str, Any] = None,
        output_file: str = "",
        output_type: str = ""
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
        :param output_file: Optional path for the enriched output file. If not
                            provided, ``file_path`` will be used as a base name
                            with ``_handelsregister_ai_enriched`` appended.
        :param output_type: Desired output type ('json', 'csv' or 'xlsx'). If empty,
                            defaults to the ``input_type``.
        """
        input_type = input_type.lower()
        if input_type not in {"json", "csv", "xlsx"}:
            raise ValueError("enrich() supports only 'json', 'csv' or 'xlsx' input_type.")

        output_type = (output_type or input_type).lower()
        if output_type not in {"json", "csv", "xlsx"}:
            raise ValueError("enrich() supports only 'json', 'csv' or 'xlsx' output_type.")

        if not file_path:
            raise ValueError("file_path is required for enrich().")

        if query_properties is None:
            query_properties = {}

        if params is None:
            params = {}

        param_hash = self._params_hash(params)

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
            latest_snapshot = self._get_latest_snapshot(snapshot_path, param_hash)
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
                    self._create_snapshot(
                        merged_data, snapshot_path, snapshots, param_hash
                    )

        # ------------------------------------------------
        # 5. Final snapshot after the loop, if requested
        # ------------------------------------------------
        if snapshot_path:
            self._create_snapshot(merged_data, snapshot_path, snapshots, param_hash)

        logger.info("Enrichment process completed.")

        # ------------------------------------------------
        # 6. Write enriched output file
        # ------------------------------------------------
        if not output_file:
            in_path = Path(file_path)
            suffix_map = {"json": ".json", "csv": ".csv", "xlsx": ".xlsx"}
            out_suffix = suffix_map.get(output_type, in_path.suffix)
            output_name = f"{in_path.stem}_handelsregister_ai_enriched{out_suffix}"
            output_file = str(in_path.with_name(output_name))

        if output_type == "json":
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)
        else:
            import pandas as pd
            for item in merged_data:
                flat = self._flatten_result(item.get("_handelsregister_result"))
                for k, v in flat.items():
                    item[f"hr_{k}"] = v
            df = pd.DataFrame(merged_data)
            df["_handelsregister_summary"] = df["_handelsregister_result"].apply(self._format_flat_result)
            df = df.drop(columns=["_handelsregister_result", "_in_file"], errors="ignore")
            if output_type == "csv":
                df.to_csv(output_file, index=False)
            else:
                df.to_excel(output_file, index=False)

        logger.info("Enriched data written to %s", output_file)

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

    def _format_flat_result(self, result: Any) -> str:
        """Create a short string summary from an API result."""
        if not isinstance(result, dict):
            return ""

        parts = []
        name = result.get("name")
        if name:
            parts.append(name)

        status = result.get("status")
        if status:
            parts.append(f"Status: {status}")

        reg = result.get("registration", {})
        reg_no = reg.get("register_number")
        court = reg.get("court")
        reg_parts = []
        if court:
            reg_parts.append(court)
        if reg_no:
            reg_parts.append(str(reg_no))
        if reg_parts:
            parts.append("Reg: " + " ".join(reg_parts))

        addr = result.get("address", {})
        addr_components = []
        street = addr.get("street")
        house_no = addr.get("house_number")
        if street or house_no:
            addr_components.append(" ".join(filter(None, [street, str(house_no) if house_no else None])).strip())
        pc = addr.get("postal_code")
        city = addr.get("city")
        if pc or city:
            addr_components.append(" ".join(filter(None, [str(pc) if pc else None, city])).strip())
        country = addr.get("country") or addr.get("country_code")
        if country:
            addr_components.append(str(country))
        if addr_components:
            parts.append(", ".join(addr_components))

        return " | ".join(parts)

    def _flatten_account(self, account: Any, prefix: str = "") -> List[str]:
        """Flatten a single account structure to lines."""
        if isinstance(account, dict) and "name" in account:
            name_dict = account.get("name", {})
            name = name_dict.get("de") or name_dict.get("en") or name_dict.get("in_report", "")
            value = account.get("value")
            line = f"{prefix}{name}: {value}" if value is not None else f"{prefix}{name}"
            lines = [line]
            for child in account.get("children", []):
                lines.extend(self._flatten_account(child, prefix + "> "))
            return lines
        elif isinstance(account, dict):
            lines = []
            for k, v in account.items():
                if isinstance(v, (dict, list)):
                    lines.extend(self._flatten_account(v, prefix + f"{k} > "))
                else:
                    lines.append(f"{prefix}{k}: {v}")
            return lines
        elif isinstance(account, list):
            lines = []
            for item in account:
                lines.extend(self._flatten_account(item, prefix))
            return lines
        else:
            return [f"{prefix}{account}"]

    def _flatten_result(self, result: Any) -> Dict[str, Any]:
        """Flatten a full API result into human readable strings."""
        if not isinstance(result, dict):
            return {}

        flat: Dict[str, Any] = {}

        simple_keys = ["name", "status", "legal_form", "registration_date", "purpose"]
        for key in simple_keys:
            if key in result:
                flat[key] = result.get(key)

        reg = result.get("registration", {})
        if reg:
            reg_parts = [reg.get("court"), reg.get("register_type"), reg.get("register_number")]
            flat["registration"] = " ".join(str(p) for p in reg_parts if p)

        addr = result.get("address", {})
        if addr:
            addr_parts = []
            if addr.get("street") or addr.get("house_number"):
                addr_parts.append(" ".join(filter(None, [addr.get("street"), str(addr.get("house_number"))])).strip())
            if addr.get("postal_code") or addr.get("city"):
                addr_parts.append(" ".join(filter(None, [str(addr.get("postal_code")), addr.get("city")])).strip())
            if addr.get("country"):
                addr_parts.append(addr.get("country"))
            flat["address"] = ", ".join(addr_parts)

        contact = result.get("contact_data", {})
        if contact:
            c_parts = []
            if contact.get("website"):
                c_parts.append(contact.get("website"))
            if contact.get("phone_number"):
                c_parts.append(contact.get("phone_number"))
            if contact.get("email"):
                c_parts.append(contact.get("email"))
            flat["contact_data"] = " | ".join(c_parts)

        if result.get("keywords"):
            flat["keywords"] = ", ".join(result["keywords"])
        if result.get("products_and_services"):
            flat["products_and_services"] = ", ".join(result["products_and_services"])

        kpis = result.get("financial_kpi")
        if kpis:
            kp_parts = []
            for entry in kpis:
                year = entry.get("year")
                metrics = [f"{k}: {v}" for k, v in entry.items() if k != "year" and v is not None]
                kp_parts.append(f"{year}: " + ", ".join(metrics))
            flat["financial_kpi"] = " | ".join(kp_parts)

        pla = result.get("profit_and_loss_account")
        if pla:
            pla_parts = []
            for entry in pla:
                year = entry.get("year")
                accounts_field = entry.get("profit_and_loss_accounts")
                accounts = []
                if isinstance(accounts_field, list):
                    for acc in accounts_field:
                        accounts.extend(self._flatten_account(acc))
                elif accounts_field is not None:
                    accounts.extend(self._flatten_account(accounts_field))
                else:
                    for k, v in entry.items():
                        if k != "year":
                            accounts.append(f"{k}: {v}")
                pla_parts.append(f"{year}: " + "; ".join(accounts))
            flat["profit_and_loss_account"] = " | ".join(pla_parts)

        bsa = result.get("balance_sheet_accounts")
        if bsa:
            bs_parts = []
            for entry in bsa:
                year = entry.get("year")
                accounts_field = entry.get("balance_sheet_accounts")
                accounts = []
                if isinstance(accounts_field, list):
                    for acc in accounts_field:
                        accounts.extend(self._flatten_account(acc))
                elif accounts_field is not None:
                    accounts.extend(self._flatten_account(accounts_field))
                else:
                    for k, v in entry.items():
                        if k != "year":
                            accounts.append(f"{k}: {v}")
                bs_parts.append(f"{year}: " + "; ".join(accounts))
            flat["balance_sheet_accounts"] = " | ".join(bs_parts)

        history = result.get("history")
        if history:
            hist_parts = []
            for h in history:
                name = (h.get("name", {}).get("en") or h.get("name", {}).get("de") or "").strip()
                start = h.get("start_date", "")
                desc = (h.get("description", {}).get("short", {}).get("en") or h.get("description", {}).get("short", {}).get("de") or "").strip()
                parts = [p for p in [name, desc, start] if p]
                hist_parts.append(" - ".join(parts))
            flat["history"] = " || ".join(hist_parts)

        return flat

    def _build_q_string(self, item: dict, query_properties: Dict[str, str]) -> str:
        """
        Given a single item and the query_properties mapping,
        build the 'q' string (space-separated combination of fields).
        """
        parts = []
        for field_key in query_properties.values():
            raw_val = item.get(field_key)
            if raw_val is None:
                continue
            val = str(raw_val).strip()
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

    def _params_hash(self, params: Dict[str, Any]) -> str:
        """Create a stable hash for the given parameters."""
        if not params:
            return "noparams"

        def _norm(value):
            if isinstance(value, list):
                return sorted(value)
            if isinstance(value, dict):
                return {k: _norm(v) for k, v in sorted(value.items())}
            return value

        normalized = {k: _norm(v) for k, v in sorted(params.items())}
        raw = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha1(raw).hexdigest()[:8]

    def _create_snapshot(
        self,
        data,
        snapshot_path: Path,
        max_snapshots: int,
        param_hash: str,
    ):
        """Creates a JSON snapshot of the data and prunes old snapshots."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_file = snapshot_path / f"snapshot_{param_hash}_{timestamp}.json"
        logger.debug("Creating snapshot: %s", snapshot_file)

        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Prune old snapshots if we exceed max_snapshots
        pattern = str(snapshot_path / f"snapshot_{param_hash}_*.json")
        existing_snapshots = sorted(glob(pattern))
        if len(existing_snapshots) > max_snapshots:
            to_remove = existing_snapshots[:-max_snapshots]
            for old_snapshot in to_remove:
                logger.debug("Removing old snapshot: %s", old_snapshot)
                os.remove(old_snapshot)

    def _get_latest_snapshot(self, snapshot_path: Path, param_hash: str) -> Optional[str]:
        """Return the path to the latest snapshot for the given parameters."""
        pattern = str(snapshot_path / f"snapshot_{param_hash}_*.json")
        existing_snapshots = sorted(glob(pattern))
        if existing_snapshots:
            return existing_snapshots[-1]
        return None