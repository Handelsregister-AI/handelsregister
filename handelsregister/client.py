import os
import json
import time
import logging
import hashlib
import httpx
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Union, Iterable, Mapping
from pathlib import Path
from glob import glob

try:
    from tqdm import tqdm
except ImportError as exc:
    raise ImportError("tqdm is required for this package to run. Please install it.") from exc

from .version import __version__
from .constants import (
    DOCUMENT_TYPES,
    REALTIME_INCOMPATIBLE_FEATURES,
    normalize_features,
)
from .exceptions import (
    APIError,
    AuthenticationError,
    ForbiddenError,
    HandelsregisterError,
    InsufficientCreditsError,
    InvalidResponseError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    RequestValidationError,
    ServerError,
    SubscriptionRequiredError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://handelsregister.ai/api/v1/"


class Handelsregister:
    """
    A modern Python client for interacting with handelsregister.ai.

    Supports both API-key authentication (``x-api-key`` header, recommended)
    and Bearer token authentication (``Authorization: Bearer ...``).

    Usage:
        from handelsregister import Handelsregister

        # API key auth
        client = Handelsregister(api_key="YOUR_API_KEY")

        # Bearer token auth
        client = Handelsregister(bearer_token="YOUR_BEARER_TOKEN")

        result = client.fetch_organization(q="OroraTech GmbH aus München")
        print(result)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        timeout: float = 90.0,
        base_url: str = BASE_URL,
        cache_enabled: bool = True,
        rate_limit: float = 0.0,
    ) -> None:
        """
        Initialize the Handelsregister client.

        :param api_key: The API key provided by handelsregister.ai. Falls back to
                        the ``HANDELSREGISTER_API_KEY`` env var if not given.
        :param bearer_token: An API bearer token. Falls back to the
                             ``HANDELSREGISTER_BEARER_TOKEN`` env var. When set,
                             takes precedence over ``api_key``.
        :param timeout: Timeout for HTTP requests (in seconds).
        :param base_url: Base URL for the handelsregister.ai API.
        :param cache_enabled: Whether to cache identical requests in-memory.
        :param rate_limit: Minimum seconds between consecutive requests.
        """
        env_api_key = os.getenv("HANDELSREGISTER_API_KEY", "")
        env_bearer = os.getenv("HANDELSREGISTER_BEARER_TOKEN", "")

        if not bearer_token:
            bearer_token = env_bearer
        if not api_key:
            api_key = env_api_key

        if not api_key and not bearer_token:
            raise AuthenticationError(
                "An API key or Bearer token is required to use the Handelsregister client. "
                "Pass api_key/bearer_token explicitly or set HANDELSREGISTER_API_KEY / "
                "HANDELSREGISTER_BEARER_TOKEN."
            )

        self.api_key = api_key
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "User-Agent": f"handelsregister-python-client/{__version__}"
        }
        if self.bearer_token:
            self.headers["Authorization"] = f"Bearer {self.bearer_token}"
        elif self.api_key:
            self.headers["x-api-key"] = self.api_key

        self.cache_enabled = cache_enabled
        self.rate_limit = rate_limit
        self._cache: Dict[tuple, Any] = {}
        self._last_request_time = 0.0

        logger.debug("Handelsregister client initialized with base_url=%s", self.base_url)

    # -------------------------------------------------------------------
    # Core request helpers
    # -------------------------------------------------------------------

    def _respect_rate_limit(self) -> None:
        if self.rate_limit > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.rate_limit:
                time.sleep(self.rate_limit - elapsed)

    @staticmethod
    def _response_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _error_message(status_code: int, payload: Any) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, str) and error:
                return error
            meta = payload.get("meta")
            if isinstance(meta, dict) and isinstance(meta.get("message"), str):
                return meta["message"]
            detail = payload.get("detail")
            if isinstance(detail, str) and detail:
                return detail
            if isinstance(detail, list):
                messages = [
                    item.get("msg")
                    for item in detail
                    if isinstance(item, dict) and isinstance(item.get("msg"), str)
                ]
                if messages:
                    return "; ".join(messages)
        return f"handelsregister.ai API request failed with HTTP {status_code}"

    @staticmethod
    def _headers_dict(response: httpx.Response) -> Dict[str, str]:
        try:
            return {str(k): str(v) for k, v in response.headers.items()}
        except (AttributeError, TypeError, ValueError):
            return {}

    def _raise_api_error(self, response: httpx.Response) -> None:
        status_code = int(response.status_code)
        payload = self._response_payload(response)
        message = self._error_message(status_code, payload)
        kwargs = {
            "status_code": status_code,
            "payload": payload,
            "response_headers": self._headers_dict(response),
        }

        if status_code in {400, 422}:
            raise RequestValidationError(message, **kwargs)
        if status_code == 401:
            raise AuthenticationError(message, **kwargs)
        if status_code == 402:
            raise InsufficientCreditsError(message, **kwargs)
        if status_code == 403:
            if isinstance(payload, dict) and payload.get("error") == "subscription_required":
                raise SubscriptionRequiredError(message, **kwargs)
            raise ForbiddenError(message, **kwargs)
        if status_code == 404:
            raise NotFoundError(message, **kwargs)
        if status_code == 408:
            raise RequestTimeoutError(message, **kwargs)
        if status_code == 429:
            raise RateLimitError(message, **kwargs)
        if status_code >= 500:
            raise ServerError(message, **kwargs)
        raise APIError(message, **kwargs)

    @staticmethod
    def _retry_delay(response: Optional[httpx.Response], attempt: int) -> float:
        if response is not None:
            try:
                retry_after = response.headers.get("retry-after")
            except (AttributeError, TypeError):
                retry_after = None
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except (TypeError, ValueError):
                    try:
                        retry_at = parsedate_to_datetime(retry_after)
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=timezone.utc)
                        return max(
                            0.0,
                            (retry_at - datetime.now(timezone.utc)).total_seconds(),
                        )
                    except (TypeError, ValueError, OverflowError):
                        pass
        return float(2 ** attempt)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 429} or status_code >= 500

    def _request(
        self,
        path: str,
        params: Dict[str, Any],
        max_retries: int = 3,
        expect_json: bool = True,
    ) -> Any:
        """
        Send a GET request to the API, retrying on transient errors.

        :param path: Path segment (e.g. ``"fetch-organization"``).
        :param params: Query parameters.
        :param max_retries: How many times to retry on network errors.
        :param expect_json: If False, returns the raw ``httpx.Response``.
        :return: Parsed JSON (dict/list) or the ``httpx.Response`` when
                 ``expect_json`` is False.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"

        self._respect_rate_limit()

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    logger.debug("Making GET request to %s with params=%s", url, params)
                    response = client.get(url, headers=self.headers, params=params)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        error_response = exc.response
                        status_code = int(error_response.status_code)
                        if (
                            self._is_retryable_status(status_code)
                            and attempt < max_retries - 1
                        ):
                            delay = self._retry_delay(error_response, attempt)
                            logger.warning(
                                "Retryable HTTP %d (attempt %d/%d); retrying in %.1fs",
                                status_code,
                                attempt + 1,
                                max_retries,
                                delay,
                            )
                            time.sleep(delay)
                            continue
                        self._raise_api_error(error_response)
                    self._last_request_time = time.time()
                    if not expect_json:
                        return response
                    return response.json()

            except httpx.RequestError as exc:
                logger.warning("Request error (attempt %d/%d): %s", attempt + 1, max_retries, exc)
                if attempt == max_retries - 1:
                    raise HandelsregisterError(f"Error while requesting data: {exc}") from exc
                time.sleep(self._retry_delay(None, attempt))

            except ValueError as exc:
                logger.error("Invalid JSON response: %s", exc)
                raise InvalidResponseError(f"Received non-JSON response: {exc}") from exc

    def _post(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Any:
        """Send a POST request with a JSON body."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        self._respect_rate_limit()

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=self.headers, json=json_body or {})
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        error_response = exc.response
                        status_code = int(error_response.status_code)
                        if (
                            self._is_retryable_status(status_code)
                            and attempt < max_retries - 1
                        ):
                            time.sleep(self._retry_delay(error_response, attempt))
                            continue
                        self._raise_api_error(error_response)
                    self._last_request_time = time.time()
                    return response.json()
            except httpx.RequestError as exc:
                if attempt == max_retries - 1:
                    raise HandelsregisterError(f"Error while requesting data: {exc}") from exc
                time.sleep(self._retry_delay(None, attempt))
            except ValueError as exc:
                raise InvalidResponseError(f"Received non-JSON response: {exc}") from exc

    def _delete(
        self,
        path: str,
        max_retries: int = 3,
    ) -> Any:
        """Send a DELETE request."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        self._respect_rate_limit()

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.delete(url, headers=self.headers)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        error_response = exc.response
                        status_code = int(error_response.status_code)
                        if (
                            self._is_retryable_status(status_code)
                            and attempt < max_retries - 1
                        ):
                            time.sleep(self._retry_delay(error_response, attempt))
                            continue
                        self._raise_api_error(error_response)
                    self._last_request_time = time.time()
                    if not response.content:
                        return {}
                    return response.json()
            except httpx.RequestError as exc:
                if attempt == max_retries - 1:
                    raise HandelsregisterError(f"Error while requesting data: {exc}") from exc
                time.sleep(self._retry_delay(None, attempt))
            except ValueError as exc:
                raise InvalidResponseError(f"Received non-JSON response: {exc}") from exc

    # -------------------------------------------------------------------
    # Public endpoints
    # -------------------------------------------------------------------

    def fetch_organization(
        self,
        q: str,
        features: Optional[Iterable[Union[str, Enum]]] = None,
        ai_search: Optional[str] = None,
        realtime_mode: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Fetch organization data from handelsregister.ai.

        :param q: The search query (company name, register number, etc.). Required.
        :param features: Optional feature flags. Supported values include::

                related_persons, publications, financial_kpi,
                balance_sheet_accounts, profit_and_loss_account,
                annual_financial_statements, annual_financial_statements__html,
                insolvency_publications, news, website_content,
                shareholders, ubos, shareholdings, mergers_and_acquisitions

        :param ai_search: Pass ``"on-default"`` to enable AI-based search.
        :param realtime_mode: Pass ``"handelsregister-default"`` to enable live
                              lookups against the Handelsregister (+10 credits).
        :param kwargs: Additional query parameters supported by the API.
        :return: Parsed JSON response as a dictionary.
        :raises HandelsregisterError: On request or response failure.
        """
        if not q:
            raise ValueError("Parameter 'q' is required.")

        normalized_features = normalize_features(features)
        if ai_search == "off":
            ai_search = None
        if realtime_mode:
            incompatible = sorted(
                set(normalized_features) & REALTIME_INCOMPATIBLE_FEATURES
            )
            if incompatible:
                raise ValueError(
                    "realtime_mode cannot be combined with: "
                    + ", ".join(incompatible)
                )

        logger.debug(
            "Fetching organization data for q=%s, features=%s, ai_search=%s, realtime_mode=%s",
            q, normalized_features, ai_search, realtime_mode,
        )

        params: Dict[str, Any] = {"q": q}

        if normalized_features:
            params["feature"] = normalized_features
        if ai_search:
            params["ai_search"] = ai_search
        if realtime_mode:
            params["realtime_mode"] = realtime_mode

        for key, value in kwargs.items():
            params[key] = value

        cache_key = (
            "fetch-organization",
            q,
            tuple(sorted(normalized_features)),
            ai_search,
            realtime_mode,
            tuple(sorted((k, self._stable(v)) for k, v in kwargs.items())),
        )

        use_cache = self.cache_enabled and not realtime_mode
        if use_cache and cache_key in self._cache:
            logger.debug("Returning cached result for %s", q)
            return self._cache[cache_key]

        data = self._request("fetch-organization", params=params)

        if use_cache:
            self._cache[cache_key] = data
        return data

    def fetch_person(
        self,
        person_q: str,
        organization_q: str,
        features: Optional[Iterable[Union[str, Enum]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Fetch a person profile from handelsregister.ai.

        Combines Handelsregister records with public web data. The server always
        runs AI search for this endpoint; the 15 base credits include the
        AI enrichment.

        :param person_q: Full name of the person (required, min. 2 chars).
        :param organization_q: Company context used to disambiguate common names
                               (required, min. 2 chars).
        :param features: Optional feature list. Currently only ``"shareholdings"``
                         is supported (+5 credits when data is returned).
        :param kwargs: Additional query parameters supported by the API.
        :return: Parsed JSON response as a dictionary.
        """
        if not person_q or len(person_q.strip()) < 2:
            raise ValueError("Parameter 'person_q' is required (min. 2 characters).")
        if not organization_q or len(organization_q.strip()) < 2:
            raise ValueError("Parameter 'organization_q' is required (min. 2 characters).")

        normalized_features = normalize_features(features)
        params: Dict[str, Any] = {
            "person_q": person_q,
            "organization_q": organization_q,
        }
        if normalized_features:
            params["feature"] = normalized_features
        for key, value in kwargs.items():
            params[key] = value

        cache_key = (
            "fetch-person",
            person_q,
            organization_q,
            tuple(sorted(normalized_features)),
            tuple(sorted((k, self._stable(v)) for k, v in kwargs.items())),
        )
        if self.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        data = self._request("fetch-person", params=params)

        if self.cache_enabled:
            self._cache[cache_key] = data
        return data

    def search_organizations(
        self,
        q: Optional[str] = None,
        skip: int = 0,
        limit: int = 10,
        filters: Optional[Union[Mapping[str, Any], Any]] = None,
        ai_mode: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search German organizations.

        Either ``q`` or ``filters`` must be supplied.

        :param q: Optional search query (min. 2 characters).
        :param skip: Pagination offset (default 0).
        :param limit: Results per page (default 10, max 30).
        :param filters: Documented search filter mapping, including registration,
                        location, register, employee and financial range filters.
                        Objects exposing ``to_dict()`` are also accepted.
        :param ai_mode: Pass ``"on-default"`` to enable AI-assisted search.
        :param kwargs: Additional query parameters supported by the API.
        :return: Parsed JSON response (``{"results": [...], "total": int, ...}``).
        """
        filter_data = self._prepare_search_filters(filters)
        if q is not None:
            q = q.strip()
            if q and len(q) < 2:
                raise ValueError("Parameter 'q' must contain min. 2 characters.")
            if not q:
                q = None
        if q is None and not filter_data:
            raise ValueError("Either parameter 'q' or 'filters' is required.")
        if limit is not None and (limit < 1 or limit > 30):
            raise ValueError("Parameter 'limit' must be between 1 and 30.")
        if skip is not None and skip < 0:
            raise ValueError("Parameter 'skip' must be >= 0.")

        params: Dict[str, Any] = {
            "skip": skip,
            "limit": limit,
        }
        if q is not None:
            params["q"] = q
        if filter_data:
            params["filters"] = json.dumps(filter_data, ensure_ascii=False)
        if ai_mode:
            params["ai_mode"] = ai_mode
        for key, value in kwargs.items():
            params[key] = value

        cache_key = (
            "search-organizations",
            q,
            skip,
            limit,
            self._stable(filter_data),
            ai_mode,
            tuple(sorted((k, self._stable(v)) for k, v in kwargs.items())),
        )
        if self.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        data = self._request("search-organizations", params=params)

        if self.cache_enabled:
            self._cache[cache_key] = data
        return data

    @staticmethod
    def _prepare_search_filters(filters: Any) -> Dict[str, Any]:
        if filters is None:
            return {}
        if hasattr(filters, "to_dict") and callable(filters.to_dict):
            filters = filters.to_dict()
        if not isinstance(filters, Mapping):
            raise TypeError("Parameter 'filters' must be a mapping or expose to_dict().")

        data = dict(filters)

        # The public documentation exposes financial range filters as flat
        # keys. The live search service groups them under ``financial_filters``.
        # Keep the documented SDK input while emitting the current wire shape.
        financial_keys = {
            "emp_count",
            "bs_assets_total",
            "bs_equity_total",
            "bs_liabilities_total",
            "bs_cash_and_equivalents",
            "bs_cash_to_liabilities",
            "bs_equity_ratio",
            "bs_debt_to_assets",
            "pl_revenue",
            "pl_net_income",
            "pl_ebit",
        }
        financial_filters = data.get("financial_filters")
        if financial_filters is None:
            financial_filters = {}
        elif not isinstance(financial_filters, Mapping):
            raise TypeError("Filter 'financial_filters' must be a mapping.")
        else:
            financial_filters = dict(financial_filters)
        for key in financial_keys:
            if key in data:
                financial_filters[key] = data.pop(key)
        if financial_filters:
            data["financial_filters"] = financial_filters

        # The live API names the employee-based size bucket
        # ``emp_size_category``. Preserve the documented friendly name.
        if "company_size_category" in data and "emp_size_category" not in data:
            data["emp_size_category"] = data.pop("company_size_category")

        distance = data.get("location_max_distance_km")
        if distance is not None:
            if "location_coordinates" not in data:
                raise ValueError(
                    "Filter 'location_max_distance_km' requires "
                    "'location_coordinates'."
                )
            if not isinstance(distance, (int, float)) or not 1 <= distance <= 100:
                raise ValueError(
                    "Filter 'location_max_distance_km' must be between 1 and 100."
                )

        values_to_validate = dict(data)
        if isinstance(data.get("financial_filters"), Mapping):
            values_to_validate.update(data["financial_filters"])
        for key, value in values_to_validate.items():
            if isinstance(value, dict) and (
                "gte" in value or "lte" in value
            ):
                unknown = set(value) - {"gte", "lte"}
                if unknown:
                    raise ValueError(
                        f"Range filter '{key}' contains unsupported keys: "
                        + ", ".join(sorted(unknown))
                    )
                if not value:
                    raise ValueError(f"Range filter '{key}' must not be empty.")
        return data

    def fetch_organization_df(self, *args, **kwargs):
        """Fetch organization data and return a pandas DataFrame."""
        data = self.fetch_organization(*args, **kwargs)
        import pandas as pd
        return pd.json_normalize(data)

    def fetch_document(
        self,
        company_id: str,
        document_type: str,
        output_file: Optional[str] = None,
    ) -> bytes:
        """
        Fetch official documents from the German Handelsregister.

        :param company_id: Unique company entity ID returned by the search
                           or fetch endpoints.
        :param document_type: One of ``"shareholders_list"``,
                              ``"articles_of_association"``, ``"AD"``,
                              ``"CD"`` or ``"SI"``. SI is returned as XML;
                              all other document types are returned as PDF.
        :param output_file: Optional path to save the document. Its bytes are
                            always returned in addition to being written.
        :return: Document content as bytes.
        :raises HandelsregisterError: On request or response failure.
        :raises ValueError: When parameters are missing or invalid.
        """
        if not company_id:
            raise ValueError("Parameter 'company_id' is required.")
        if not document_type:
            raise ValueError("Parameter 'document_type' is required.")

        if isinstance(document_type, Enum):
            document_type = str(document_type.value)
        if document_type not in DOCUMENT_TYPES:
            raise ValueError(
                f"Invalid document_type '{document_type}'. "
                f"Valid values are: {', '.join(DOCUMENT_TYPES)}"
            )

        logger.debug(
            "Fetching document for company_id=%s, document_type=%s",
            company_id, document_type,
        )

        params = {
            "company_id": company_id,
            "document_type": document_type,
        }

        response = self._request("fetch-document", params=params, expect_json=False)

        content_type = response.headers.get("content-type", "").lower()
        expected_types = (
            ("application/xml", "text/xml")
            if document_type == "SI"
            else ("application/pdf",)
        )
        if not any(expected in content_type for expected in expected_types):
            error_data = self._response_payload(response)
            if isinstance(error_data, dict):
                error_msg = self._error_message(200, error_data)
                raise HandelsregisterError(f"API error: {error_msg}")
            expected_label = "XML" if document_type == "SI" else "PDF"
            raise InvalidResponseError(
                f"Expected {expected_label} response but got {content_type or 'unknown'}"
            )

        document_content = response.content
        if output_file:
            with open(output_file, "wb") as f:
                f.write(document_content)
            logger.info("Document saved to %s", output_file)
        return document_content

    # -------------------------------------------------------------------
    # Token management (Bearer tokens)
    # -------------------------------------------------------------------

    def create_token(
        self,
        token_name: str,
        abilities: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new API bearer token.

        :param token_name: Human-readable label for the token.
        :param abilities: List of abilities, e.g. ``["*"]``.
        :param expires_at: Optional expiry timestamp
                           (format ``"YYYY-MM-DD HH:MM:SS"``).
        :return: Response payload including the new token value.
        """
        if not token_name:
            raise ValueError("Parameter 'token_name' is required.")

        body: Dict[str, Any] = {"token_name": token_name}
        if abilities is not None:
            body["abilities"] = abilities
        if expires_at is not None:
            body["expires_at"] = expires_at
        return self._post("auth/tokens/create", json_body=body)

    def list_tokens(self) -> Dict[str, Any]:
        """List all API bearer tokens for the authenticated account."""
        return self._request("auth/tokens", params={})

    def revoke_token(self, token_id: Union[str, int]) -> Dict[str, Any]:
        """Revoke a specific API bearer token by its ID."""
        if not token_id and token_id != 0:
            raise ValueError("Parameter 'token_id' is required.")
        return self._delete(f"auth/tokens/{token_id}")

    def revoke_all_tokens(self) -> Dict[str, Any]:
        """Revoke all API bearer tokens for the authenticated account."""
        return self._delete("auth/tokens")

    # -------------------------------------------------------------------
    # Bulk enrichment
    # -------------------------------------------------------------------

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

        snapshot_data = []
        if snapshot_path:
            latest_snapshot = self._get_latest_snapshot(snapshot_path, param_hash)
            if latest_snapshot:
                logger.info("Continuing from existing snapshot: %s", latest_snapshot)
                with open(latest_snapshot, "r", encoding="utf-8") as f:
                    snapshot_data = json.load(f)
            else:
                logger.info("No existing snapshot found.")

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

        merged_data = self._merge_data(snapshot_data, file_data, query_properties)

        logger.debug("Merged dataset size: %d items (includes removed items from snapshots).", len(merged_data))

        processed_so_far = 0
        for item in merged_data:
            if item.get("_handelsregister_result") is not None:
                processed_so_far += 1

        logger.debug("Already processed %d items (via snapshots).", processed_so_far)

        total_file_items = sum(1 for x in merged_data if x["_in_file"])
        already_done = sum(1 for x in merged_data if x["_in_file"] and x.get("_handelsregister_result") is not None)

        logger.info(
            "Enriching %d new items (file has %d total, %d already enriched).",
            total_file_items - already_done, total_file_items, already_done
        )

        current_step_count = 0
        with tqdm(total=total_file_items, initial=already_done, desc="Enriching data") as pbar:
            for item in merged_data:
                if not item["_in_file"]:
                    continue
                if "_handelsregister_result" in item and item["_handelsregister_result"] is not None:
                    continue

                q_string = self._build_q_string(item, query_properties)
                if not q_string:
                    logger.debug("Skipping item because q-string is empty: %s", item)
                    item["_handelsregister_result"] = None
                else:
                    logger.debug("Enriching new item with q=%s", q_string)
                    api_response = self.fetch_organization(q=q_string, **params)
                    item["_handelsregister_result"] = api_response

                pbar.update(1)
                current_step_count += 1

                if snapshot_path and current_step_count % snapshot_steps == 0:
                    self._create_snapshot(
                        merged_data, snapshot_path, snapshots, param_hash
                    )

        if snapshot_path:
            self._create_snapshot(merged_data, snapshot_path, snapshots, param_hash)

        logger.info("Enrichment process completed.")

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

    @staticmethod
    def _stable(value: Any) -> Any:
        """Return a stable, hashable representation of a param value."""
        if isinstance(value, dict):
            return tuple(sorted((k, Handelsregister._stable(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(Handelsregister._stable(v) for v in value)
        return value

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

        # Preserve every additional current or future API field in tabular
        # enrichment output. Variable-depth structures (representation
        # schemes, ownership graphs, M&A transactions, reports, etc.) are
        # encoded as deterministic JSON rather than being silently dropped or
        # exploded into an unstable set of columns.
        for key, value in result.items():
            if key in flat:
                continue
            if isinstance(value, (dict, list)):
                flat[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            else:
                flat[key] = value

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
        """
        merged_dict = {}

        for snap_item in snapshot_data:
            key = self._build_key(snap_item, query_properties)
            merged_dict[key] = snap_item

        for file_item in file_data:
            key = self._build_key(file_item, query_properties)
            if key in merged_dict:
                existing = merged_dict[key]
                enriched_result = existing.get("_handelsregister_result")
                merged_dict[key] = file_item
                if enriched_result is not None:
                    merged_dict[key]["_handelsregister_result"] = enriched_result
            else:
                merged_dict[key] = file_item

            merged_dict[key]["_in_file"] = True

        for key, item in merged_dict.items():
            if "_in_file" not in item:
                item["_in_file"] = False

        final_list = []
        used_keys = set()

        for snap_item in snapshot_data:
            key = self._build_key(snap_item, query_properties)
            if key in merged_dict and key not in used_keys:
                final_list.append(merged_dict[key])
                used_keys.add(key)

        for file_item in file_data:
            key = self._build_key(file_item, query_properties)
            if key in merged_dict and key not in used_keys:
                final_list.append(merged_dict[key])
                used_keys.add(key)

        for key, item in merged_dict.items():
            if key not in used_keys:
                final_list.append(item)
                used_keys.add(key)

        return final_list

    def _build_key(self, item: dict, query_properties: Dict[str, str]) -> tuple:
        """Build a tuple key based on query_properties."""
        if not query_properties:
            return id(item)
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
