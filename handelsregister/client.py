import os
import json
import time
import logging
import hashlib
import re
import uuid
import httpx
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Union, Iterable, Iterator, Mapping
from pathlib import Path
from glob import glob
from urllib.parse import quote

try:
    from tqdm import tqdm
except ImportError as exc:
    raise ImportError("tqdm is required for this package to run. Please install it.") from exc

from .version import __version__
from .constants import (
    DOCUMENT_TYPES,
    INSOLVENCY_STATUSES,
    LEGAL_FORM_LIABILITY_TYPES,
    ORGANIZATION_STATUSES,
    OWNERSHIP_STRUCTURES,
    REALTIME_INCOMPATIBLE_FEATURES,
    SEARCH_ORGANIZATIONS_MAX_LIMIT,
    SEARCH_ORGANIZATIONS_MAX_QUERY_LENGTH,
    SEARCH_SORT_FIELDS,
    SIGNAL_TOPICS,
    SORT_ORDERS,
    normalize_features,
)
from .exceptions import (
    APIError,
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    HandelsregisterError,
    IdempotencyConflictError,
    IdempotencyKeyRequiredError,
    InsufficientCreditsError,
    InvalidResponseError,
    NotFoundError,
    RateLimitError,
    RequestTimeoutError,
    RequestValidationError,
    ServerError,
    ServiceUnavailableError,
    SubscriptionRequiredError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://handelsregister.ai/api/v1/"
_HTTP_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MONITOR_ID_PATTERN = re.compile(r"^mon_[a-z0-9]{26}$")
_WEBHOOK_ENDPOINT_ID_PATTERN = re.compile(r"^wep_[a-z0-9]{26}$")
_WEBHOOK_DELIVERY_ID_PATTERN = re.compile(r"^del_[a-z0-9]{26}$")
_MONITOR_ENTITY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")


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
        extra_headers: Optional[Mapping[str, str]] = None,
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
        :param extra_headers: Optional additional request headers for custom
                              gateways or proxies. Authentication and
                              User-Agent headers cannot be overridden.
                              Falls back to the ``HANDELSREGISTER_EXTRA_HEADERS``
                              env var (a JSON object) if not given.
        """
        env_api_key = os.getenv("HANDELSREGISTER_API_KEY", "")
        env_bearer = os.getenv("HANDELSREGISTER_BEARER_TOKEN", "")

        if not bearer_token:
            bearer_token = env_bearer
        if not api_key:
            api_key = env_api_key

        if base_url == BASE_URL:
            base_url = os.getenv("HANDELSREGISTER_BASE_URL") or base_url
        if extra_headers is None:
            env_extra_headers = os.getenv("HANDELSREGISTER_EXTRA_HEADERS", "")
            if env_extra_headers:
                try:
                    extra_headers = json.loads(env_extra_headers)
                except ValueError as exc:
                    raise ValueError(
                        "Environment variable 'HANDELSREGISTER_EXTRA_HEADERS' "
                        "must contain a JSON object."
                    ) from exc
                if not isinstance(extra_headers, dict):
                    raise ValueError(
                        "Environment variable 'HANDELSREGISTER_EXTRA_HEADERS' "
                        "must contain a JSON object."
                    )

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

        self.extra_headers: Dict[str, str] = {}
        if extra_headers is not None:
            if not isinstance(extra_headers, Mapping):
                raise ValueError("Parameter 'extra_headers' must be a mapping.")
            reserved_headers = {"authorization", "x-api-key", "user-agent"}
            for key, value in extra_headers.items():
                if not isinstance(key, str):
                    raise ValueError("Extra header names must be strings.")
                normalized_key = key.strip()
                if not normalized_key or not _HTTP_HEADER_NAME.fullmatch(
                    normalized_key
                ):
                    raise ValueError(
                        "Extra header names must use valid HTTP token characters."
                    )
                if normalized_key.lower() in reserved_headers:
                    raise ValueError(
                        f"Header '{normalized_key}' is managed by the SDK and "
                        "cannot be supplied through extra_headers."
                    )
                if (
                    not isinstance(value, str)
                    or not value
                    or "\r" in value
                    or "\n" in value
                ):
                    raise ValueError(
                        f"Extra header '{normalized_key}' must have a non-empty "
                        "single-line string value."
                    )
                self.extra_headers[normalized_key] = value
            self.headers.update(self.extra_headers)

        self.cache_enabled = cache_enabled
        self.rate_limit = rate_limit
        self._cache: Dict[tuple, Any] = {}
        self._last_request_time = 0.0
        #: ``Idempotency-Status`` header of the most recent monitoring
        #: mutation: ``"created"``, ``"replayed"`` or ``None``.
        self.last_idempotency_status: Optional[str] = None

        logger.debug("Handelsregister client initialized")

    # -------------------------------------------------------------------
    # Core request helpers
    # -------------------------------------------------------------------

    def _respect_rate_limit(self) -> None:
        if self.rate_limit > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.rate_limit:
                time.sleep(self.rate_limit - elapsed)

    def _json_headers(self) -> Dict[str, str]:
        """
        Request headers for JSON endpoints.

        ``Accept: application/json`` makes the API answer validation
        failures with 422 Problem JSON instead of a 302 redirect intended
        for browsers.
        """
        headers = dict(self.headers)
        headers.setdefault("Accept", "application/json")
        return headers

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
            if isinstance(error, dict):
                for key in ("message", "detail", "title", "code"):
                    value = error.get(key)
                    if isinstance(value, str) and value:
                        return value
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
            for key in ("message", "title"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
            if isinstance(error, str) and error:
                return error
            code = payload.get("code")
            if isinstance(code, str) and code:
                return code
        return f"handelsregister.ai API request failed with HTTP {status_code}"

    @staticmethod
    def _error_code(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        error = payload.get("error")
        candidates = [
            payload.get("code"),
            payload.get("error_code"),
            error.get("code") if isinstance(error, dict) else error,
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate.upper()
        return ""

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
            if self._error_code(payload) in {
                "PLAN_REQUIRED",
                "SUBSCRIPTION_REQUIRED",
            }:
                raise SubscriptionRequiredError(message, **kwargs)
            raise ForbiddenError(message, **kwargs)
        if status_code == 404:
            raise NotFoundError(message, **kwargs)
        if status_code == 408:
            raise RequestTimeoutError(message, **kwargs)
        if status_code == 409:
            if self._error_code(payload).startswith("IDEMPOTENCY"):
                raise IdempotencyConflictError(message, **kwargs)
            raise ConflictError(message, **kwargs)
        if status_code == 428:
            raise IdempotencyKeyRequiredError(message, **kwargs)
        if status_code == 429:
            raise RateLimitError(message, **kwargs)
        if status_code == 503 and self._error_code(payload) == "TEMPORARILY_UNAVAILABLE":
            raise ServiceUnavailableError(message, **kwargs)
        if status_code >= 500:
            raise ServerError(message, **kwargs)
        if 300 <= status_code < 400:
            location = kwargs["response_headers"].get("location", "")
            raise APIError(
                f"Unexpected HTTP {status_code} redirect"
                + (f" to {location}" if location else "")
                + "; the API returned a browser response instead of JSON.",
                **kwargs,
            )
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
        params: Optional[Dict[str, Any]] = None,
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
        headers = self._json_headers() if expect_json else self.headers

        self._respect_rate_limit()

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    logger.debug(
                        "Making GET request to path=%s with query parameters=%s",
                        path,
                        sorted((params or {}).keys()),
                    )
                    response = client.get(url, headers=headers, params=params or {})
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
                    response = client.post(
                        url, headers=self._json_headers(), json=json_body or {}
                    )
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
                    response = client.delete(url, headers=self._json_headers())
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
    # Idempotent mutations (monitoring & webhooks)
    # -------------------------------------------------------------------

    @staticmethod
    def _idempotency_key(idempotency_key: Optional[str]) -> str:
        """Validate a caller-supplied Idempotency-Key or generate a fresh one."""
        if idempotency_key is None:
            return f"sdk-py-{uuid.uuid4().hex}"
        if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(
            idempotency_key
        ):
            raise ValueError(
                "Parameter 'idempotency_key' must be 1-128 ASCII characters "
                "matching [A-Za-z0-9._:-] and start with an alphanumeric "
                "character."
            )
        return idempotency_key

    def _mutate(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3,
        network_io: bool = False,
        verified_result_on_422: bool = False,
    ) -> Any:
        """
        Send an idempotent mutation (POST/PATCH/DELETE) with an
        ``Idempotency-Key`` header, retrying safely on transient errors.

        Retries always reuse the same idempotency key, so the durable
        server-side ledger replays the original result instead of repeating
        the effect. HTTP 409 is never retried: for plain database mutations
        it signals a parameter conflict, for endpoint verify/test it can
        signal an ambiguity the client must not re-drive.

        :param network_io: True for operations that contact the customer's
                           webhook receiver (verify/test). For those, only
                           HTTP 429 and the pre-operation 503 kill switch are
                           retried; other 5xx responses are ambiguous and
                           surface immediately.
        :param verified_result_on_422: Return the payload instead of raising
                                       when a 422 body carries a ``verified``
                                       key (endpoint verification failure is
                                       a normal domain outcome).
        """
        key = self._idempotency_key(idempotency_key)
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._json_headers()
        headers["Idempotency-Key"] = key
        self.last_idempotency_status = None
        self._respect_rate_limit()

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    logger.debug(
                        "Making idempotent %s request to path=%s",
                        method,
                        path,
                    )
                    response = client.request(
                        method,
                        url,
                        headers=headers,
                        json=json_body,
                    )
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        error_response = exc.response
                        status_code = int(error_response.status_code)
                        if (
                            verified_result_on_422
                            and status_code == 422
                        ):
                            payload = self._response_payload(error_response)
                            if isinstance(payload, dict) and "verified" in payload:
                                self._last_request_time = time.time()
                                self._store_idempotency_status(error_response)
                                return payload
                        if (
                            self._is_retryable_mutation_status(
                                status_code, error_response, network_io
                            )
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
                    self._store_idempotency_status(response)
                    if not response.content:
                        return {}
                    return response.json()
            except httpx.RequestError as exc:
                logger.warning(
                    "Request error (attempt %d/%d): %s", attempt + 1, max_retries, exc
                )
                if attempt == max_retries - 1:
                    raise HandelsregisterError(f"Error while requesting data: {exc}") from exc
                time.sleep(self._retry_delay(None, attempt))
            except ValueError as exc:
                raise InvalidResponseError(f"Received non-JSON response: {exc}") from exc

    def _is_retryable_mutation_status(
        self,
        status_code: int,
        response: httpx.Response,
        network_io: bool,
    ) -> bool:
        if status_code == 409:
            return False
        if network_io:
            if status_code == 429:
                return True
            if status_code == 503:
                payload = self._response_payload(response)
                return self._error_code(payload) == "TEMPORARILY_UNAVAILABLE"
            return False
        return self._is_retryable_status(status_code)

    def _store_idempotency_status(self, response: httpx.Response) -> None:
        try:
            status = response.headers.get("idempotency-status")
        except (AttributeError, TypeError):
            status = None
        self.last_idempotency_status = status if isinstance(status, str) and status else None

    # -------------------------------------------------------------------
    # Public endpoints
    # -------------------------------------------------------------------

    def _network_subscription_access(self) -> Optional[bool]:
        """
        Return whether the current plan includes ``network``.

        ``None`` means the account endpoint could not provide a definitive
        answer, in which case the organization request remains backward
        compatible and the API decides what to return.
        """
        try:
            account = self.get_account_subscription()
        except HandelsregisterError as exc:
            logger.debug("Could not preflight network plan access: %s", exc)
            return None
        if not isinstance(account, dict) or "subscription" not in account:
            return None
        subscription = account.get("subscription")
        if subscription is None:
            return False
        if not isinstance(subscription, dict):
            return None
        plan = subscription.get("plan")
        if not isinstance(plan, str) or not plan.strip():
            return None
        return plan.strip().lower() in {"pro", "max"}

    def _require_network_subscription(self) -> None:
        if self._network_subscription_access() is not False:
            return
        message = (
            "The 'network' feature requires an active Pro or Max subscription."
        )
        raise SubscriptionRequiredError(
            message,
            status_code=403,
            payload={
                "error": "subscription_required",
                "meta": {
                    "message": message,
                    "required_plans": ["pro", "max"],
                    "blocked_features": ["network"],
                    "request_credit_cost": 0,
                },
            },
        )

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
                shareholders, ubos, shareholdings, mergers_and_acquisitions,
                network

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

        # The service currently omits ``network`` silently for accounts below
        # Pro, returning a billable base profile instead of the documented 403.
        # A free account read lets the SDK fail clearly before that charge.
        if "network" in normalized_features:
            self._require_network_subscription()

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
        sort: Optional[Union[str, Enum]] = None,
        order: Optional[Union[str, Enum]] = None,
        match_context: Optional[bool] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search German organizations.

        Either ``q`` or ``filters`` must be supplied.

        :param q: Optional search query (2-500 characters).
        :param skip: Pagination offset (default 0).
        :param limit: Results per page (default 10, max
                      ``SEARCH_ORGANIZATIONS_MAX_LIMIT``).
        :param filters: Documented search filter mapping, including registration,
                        location, register, employee and financial range filters.
                        Objects exposing ``to_dict()`` are also accepted.
        :param ai_mode: Pass ``"on-default"`` to enable AI-assisted search.
        :param sort: Documented result sort field, such as ``"revenue"`` or
                     ``"registration_date"``.
        :param order: Optional sort direction, ``"asc"`` or ``"desc"``.
        :param match_context: Include the matching ownership, executive, or
                              lifecycle values in each result.
        :param kwargs: Additional query parameters supported by the API.
        :return: Parsed JSON response (``{"results": [...], "total": int, ...}``).
        """
        filter_data = self._prepare_search_filters(filters)
        if q is not None:
            q = q.strip()
            if q and len(q) < 2:
                raise ValueError("Parameter 'q' must contain min. 2 characters.")
            if q and len(q) > SEARCH_ORGANIZATIONS_MAX_QUERY_LENGTH:
                raise ValueError(
                    "Parameter 'q' must contain at most "
                    f"{SEARCH_ORGANIZATIONS_MAX_QUERY_LENGTH} characters."
                )
            if not q:
                q = None
        if q is None and not filter_data:
            raise ValueError("Either parameter 'q' or 'filters' is required.")
        if limit is not None and (
            limit < 1 or limit > SEARCH_ORGANIZATIONS_MAX_LIMIT
        ):
            raise ValueError(
                "Parameter 'limit' must be between 1 and "
                f"{SEARCH_ORGANIZATIONS_MAX_LIMIT}."
            )
        if skip is not None and skip < 0:
            raise ValueError("Parameter 'skip' must be >= 0.")

        sort_value = self._normalize_choice("sort", sort, SEARCH_SORT_FIELDS)
        order_value = self._normalize_choice("order", order, SORT_ORDERS)
        if match_context is not None and not isinstance(match_context, bool):
            raise TypeError("Parameter 'match_context' must be a boolean.")
        if sort_value == "distance" and "location_coordinates" not in filter_data:
            raise ValueError(
                "Sort field 'distance' requires filter 'location_coordinates'."
            )

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
        if sort_value:
            params["sort"] = sort_value
        if order_value:
            params["order"] = order_value
        if match_context is not None:
            params["match_context"] = int(match_context)
        for key, value in kwargs.items():
            params[key] = value

        cache_key = (
            "search-organizations",
            q,
            skip,
            limit,
            self._stable(filter_data),
            ai_mode,
            sort_value,
            order_value,
            match_context,
            tuple(sorted((k, self._stable(v)) for k, v in kwargs.items())),
        )
        if self.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        data = self._request("search-organizations", params=params)

        if self.cache_enabled:
            self._cache[cache_key] = data
        return data

    def iter_search_organizations(
        self,
        q: Optional[str] = None,
        skip: int = 0,
        page_size: int = SEARCH_ORGANIZATIONS_MAX_LIMIT,
        max_results: Optional[int] = None,
        filters: Optional[Union[Mapping[str, Any], Any]] = None,
        ai_mode: Optional[str] = None,
        sort: Optional[Union[str, Enum]] = None,
        order: Optional[Union[str, Enum]] = None,
        match_context: Optional[bool] = None,
        **kwargs,
    ) -> Iterable[Dict[str, Any]]:
        """
        Iterate over organization search results across API pages.

        The search endpoint returns at most
        ``SEARCH_ORGANIZATIONS_MAX_LIMIT`` results per request. This helper
        advances ``skip`` automatically and sizes the final request so callers
        can retrieve an exact maximum such as 100 without implementing their
        own pagination loop.

        Every fetched page is a separate, billable ``search-organizations``
        request. Iteration is lazy, so requests stop when the caller stops
        consuming results.

        :param q: Optional search query (2-500 characters).
        :param skip: Initial pagination offset (default 0).
        :param page_size: Results requested per API call (default/max 30).
        :param max_results: Optional maximum number of results to yield.
        :param filters: Search filter mapping or object exposing ``to_dict()``.
        :param ai_mode: Pass ``"on-default"`` for AI-assisted search.
        :param sort: Result sort field applied consistently to every page.
        :param order: Optional ``"asc"`` or ``"desc"`` sort direction.
        :param match_context: Include matching register-data values per result.
        :param kwargs: Additional query parameters supported by the API.
        :yield: Individual organization result dictionaries.
        """
        if page_size < 1 or page_size > SEARCH_ORGANIZATIONS_MAX_LIMIT:
            raise ValueError(
                "Parameter 'page_size' must be between 1 and "
                f"{SEARCH_ORGANIZATIONS_MAX_LIMIT}."
            )
        if skip < 0:
            raise ValueError("Parameter 'skip' must be >= 0.")
        if max_results is not None and max_results < 0:
            raise ValueError("Parameter 'max_results' must be >= 0.")
        if max_results == 0:
            return

        next_skip = skip
        yielded = 0

        while max_results is None or yielded < max_results:
            request_limit = page_size
            if max_results is not None:
                request_limit = min(request_limit, max_results - yielded)

            search_kwargs = dict(kwargs)
            if sort is not None:
                search_kwargs["sort"] = sort
            if order is not None:
                search_kwargs["order"] = order
            if match_context is not None:
                search_kwargs["match_context"] = match_context

            page = self.search_organizations(
                q=q,
                skip=next_skip,
                limit=request_limit,
                filters=filters,
                ai_mode=ai_mode,
                **search_kwargs,
            )
            results = page.get("results") if isinstance(page, dict) else None
            if not isinstance(results, list):
                raise InvalidResponseError(
                    "search-organizations response must contain a 'results' list."
                )
            if not results:
                return

            for result in results:
                if not isinstance(result, dict):
                    raise InvalidResponseError(
                        "search-organizations results must be objects."
                    )
                yield result
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return

            next_skip += len(results)
            total = page.get("total")
            if isinstance(total, int) and next_skip >= total:
                return
            if len(results) < request_limit:
                return

    @staticmethod
    def _normalize_choice(
        name: str,
        value: Optional[Union[str, Enum]],
        allowed: Iterable[str],
    ) -> Optional[str]:
        if value is None:
            return None
        normalized = value.value if isinstance(value, Enum) else value
        if not isinstance(normalized, str) or not normalized.strip():
            raise TypeError(f"Parameter '{name}' must be a non-empty string or enum.")
        normalized = normalized.strip()
        allowed_values = tuple(allowed)
        if normalized not in allowed_values:
            raise ValueError(
                f"Parameter '{name}' must be one of: "
                + ", ".join(allowed_values)
                + "."
            )
        return normalized

    @classmethod
    def _filter_json_value(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "to_dict") and callable(value.to_dict):
            return cls._filter_json_value(value.to_dict())
        if isinstance(value, Mapping):
            return {
                str(key): cls._filter_json_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [cls._filter_json_value(item) for item in value]
        return value

    @staticmethod
    def _validate_condition_object(group: str, field: str, value: Any) -> None:
        if not isinstance(value, Mapping):
            return
        if not value:
            raise ValueError(
                f"Filter '{group}.{field}' condition must not be empty."
            )
        allowed_operators = {"gte", "lte", "gt", "lt", "eq", "exists"}
        unknown = set(value) - allowed_operators
        if unknown:
            raise ValueError(
                f"Filter '{group}.{field}' contains unsupported operators: "
                + ", ".join(sorted(unknown))
            )
        if "exists" in value and not isinstance(value["exists"], bool):
            raise TypeError(
                f"Filter '{group}.{field}.exists' must be a boolean."
            )

    @classmethod
    def _condition_values(cls, value: Any) -> List[Any]:
        if isinstance(value, Mapping):
            values = [item for key, item in value.items() if key != "exists"]
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
        else:
            values = [value]
        flattened: List[Any] = []
        for item in values:
            if isinstance(item, (list, tuple, set)):
                flattened.extend(item)
            else:
                flattened.append(item)
        return flattened

    @classmethod
    def _validate_advanced_filter_group(
        cls,
        group: str,
        value: Any,
        allowed_fields: Iterable[str],
    ) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError(f"Filter '{group}' must be an object.")
        data = dict(value)
        unknown = set(data) - set(allowed_fields)
        if unknown:
            raise ValueError(
                f"Filter '{group}' contains unsupported fields: "
                + ", ".join(sorted(unknown))
            )
        if not data:
            raise ValueError(f"Filter '{group}' must not be empty.")
        for field, condition in data.items():
            cls._validate_condition_object(group, field, condition)
        return data

    @classmethod
    def _prepare_search_filters(cls, filters: Any) -> Dict[str, Any]:
        if filters is None:
            return {}
        if hasattr(filters, "to_dict") and callable(filters.to_dict):
            filters = filters.to_dict()
        if not isinstance(filters, Mapping):
            raise TypeError("Parameter 'filters' must be a mapping or expose to_dict().")

        data = cls._filter_json_value(filters)

        legal_form_code = data.get("legal_form_code")
        if legal_form_code is not None and (
            not isinstance(legal_form_code, str) or not legal_form_code.strip()
        ):
            raise TypeError("Filter 'legal_form_code' must be one non-empty string.")

        if "active" in data and not isinstance(data["active"], bool):
            raise TypeError("Filter 'active' must be a boolean.")

        for key, allowed in (
            ("status", ORGANIZATION_STATUSES),
            ("legal_form_liability_type", LEGAL_FORM_LIABILITY_TYPES),
        ):
            if key in data:
                cls._normalize_choice(key, data[key], allowed)

        company_size = data.get("company_size_category")
        if company_size is not None and company_size not in {
            "micro",
            "small",
            "medium",
            "large",
        }:
            raise ValueError(
                "Filter 'company_size_category' must be one of: "
                "micro, small, medium, large."
            )

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

        coordinates = data.get("location_coordinates")
        if coordinates is not None:
            if not isinstance(coordinates, Mapping):
                raise TypeError("Filter 'location_coordinates' must be an object.")
            coordinates = dict(coordinates)
            if "lat" not in coordinates and "latitude" in coordinates:
                coordinates["lat"] = coordinates.pop("latitude")
            if "lon" not in coordinates and "longitude" in coordinates:
                coordinates["lon"] = coordinates.pop("longitude")
            unknown = set(coordinates) - {"lat", "lon"}
            if unknown or set(coordinates) != {"lat", "lon"}:
                raise ValueError(
                    "Filter 'location_coordinates' must contain exactly "
                    "'lat' and 'lon'."
                )
            lat = coordinates["lat"]
            lon = coordinates["lon"]
            if (
                isinstance(lat, bool)
                or not isinstance(lat, (int, float))
                or not -90 <= lat <= 90
            ):
                raise ValueError("Filter coordinate 'lat' must be between -90 and 90.")
            if (
                isinstance(lon, bool)
                or not isinstance(lon, (int, float))
                or not -180 <= lon <= 180
            ):
                raise ValueError(
                    "Filter coordinate 'lon' must be between -180 and 180."
                )
            data["location_coordinates"] = coordinates

        distance = data.get("location_max_distance_km")
        if distance is not None:
            if "location_coordinates" not in data:
                raise ValueError(
                    "Filter 'location_max_distance_km' requires "
                    "'location_coordinates'."
                )
            if (
                isinstance(distance, bool)
                or not isinstance(distance, (int, float))
                or not 1 <= distance <= 100
            ):
                raise ValueError(
                    "Filter 'location_max_distance_km' must be between 1 and 100."
                )
        elif coordinates is not None:
            raise ValueError(
                "Filter 'location_coordinates' requires "
                "'location_max_distance_km'."
            )

        for key, value in financial_filters.items():
            if not isinstance(value, Mapping) or not value:
                raise TypeError(
                    f"Financial range filter '{key}' must be a non-empty object."
                )
            unknown = set(value) - {"gte", "lte"}
            if unknown:
                raise ValueError(
                    f"Financial range filter '{key}' contains unsupported keys: "
                    + ", ".join(sorted(unknown))
                )

        advanced_groups = {
            "ownership_filters": {
                "structure",
                "owner_managed",
                "likely_family_owned",
                "largest_share_ratio",
                "oldest_owner_birth_date",
                "youngest_owner_birth_date",
            },
            "executive_filters": {
                "md_oldest_birth_date",
                "md_youngest_birth_date",
            },
            "lifecycle_filters": {
                "insolvency_active",
                "insolvency_status",
                "insolvency_opened_date",
            },
        }
        for group, allowed_fields in advanced_groups.items():
            if group in data:
                data[group] = cls._validate_advanced_filter_group(
                    group,
                    data[group],
                    allowed_fields,
                )

        ownership = data.get("ownership_filters")
        if isinstance(ownership, Mapping) and "structure" in ownership:
            for value in cls._condition_values(ownership["structure"]):
                if value not in OWNERSHIP_STRUCTURES:
                    raise ValueError(
                        "Filter 'ownership_filters.structure' contains an "
                        f"unsupported value: {value!r}."
                    )
        if isinstance(ownership, Mapping) and "largest_share_ratio" in ownership:
            for value in cls._condition_values(ownership["largest_share_ratio"]):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 <= value <= 1
                ):
                    raise ValueError(
                        "Filter 'ownership_filters.largest_share_ratio' values "
                        "must be between 0 and 1."
                    )

        lifecycle = data.get("lifecycle_filters")
        if isinstance(lifecycle, Mapping) and "insolvency_status" in lifecycle:
            for value in cls._condition_values(lifecycle["insolvency_status"]):
                if value not in INSOLVENCY_STATUSES:
                    raise ValueError(
                        "Filter 'lifecycle_filters.insolvency_status' contains "
                        f"an unsupported value: {value!r}."
                    )
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
    # Account and usage
    # -------------------------------------------------------------------

    @staticmethod
    def _date_query_value(
        value: Optional[Union[str, date, datetime]],
        parameter_name: str,
    ) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        raise ValueError(
            f"Parameter '{parameter_name}' must be a non-empty ISO 8601 "
            "string, date, or datetime."
        )

    @staticmethod
    def _csv_query_value(
        values: Optional[Union[str, Enum, Iterable[Union[str, Enum]]]],
        parameter_name: str,
    ) -> Optional[str]:
        if values is None:
            return None
        if isinstance(values, str):
            raw_values: Iterable[Union[str, Enum]] = values.split(",")
        elif isinstance(values, Enum):
            raw_values = [values]
        else:
            raw_values = values

        normalized: List[str] = []
        seen = set()
        for item in raw_values:
            value = item.value if isinstance(item, Enum) else str(item)
            value = value.strip()
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)
        if not normalized:
            raise ValueError(f"Parameter '{parameter_name}' must not be empty.")
        return ",".join(normalized)

    def get_account(self) -> Dict[str, Any]:
        """Return the authenticated account's profile and current plan."""
        return self._request("account")

    def get_account_credits(self) -> Dict[str, Any]:
        """Return the account's credit balance and credit bookings."""
        return self._request("account/credits")

    def get_account_usage(
        self,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
        group_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return aggregated request and credit usage.

        ``from_date`` and ``to_date`` map to the API's ``from`` and ``to``
        parameters. The server defaults to the current month and accepts a
        maximum range of 366 days.
        """
        params: Dict[str, Any] = {}
        normalized_from = self._date_query_value(from_date, "from_date")
        normalized_to = self._date_query_value(to_date, "to_date")
        if normalized_from is not None:
            params["from"] = normalized_from
        if normalized_to is not None:
            params["to"] = normalized_to
        if group_by is not None:
            normalized_group_by = str(group_by).strip().lower()
            if normalized_group_by not in {"day", "month"}:
                raise ValueError("Parameter 'group_by' must be 'day' or 'month'.")
            params["group_by"] = normalized_group_by
        return self._request("account/usage", params=params)

    def get_account_usage_transactions(
        self,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
        endpoint: Optional[str] = None,
        per_page: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return one cursor-paginated page of billed request transactions."""
        params: Dict[str, Any] = {}
        normalized_from = self._date_query_value(from_date, "from_date")
        normalized_to = self._date_query_value(to_date, "to_date")
        if normalized_from is not None:
            params["from"] = normalized_from
        if normalized_to is not None:
            params["to"] = normalized_to
        if endpoint is not None:
            normalized_endpoint = str(endpoint).strip()
            if not normalized_endpoint:
                raise ValueError("Parameter 'endpoint' must not be empty.")
            params["endpoint"] = normalized_endpoint
        if per_page is not None:
            if isinstance(per_page, bool) or not isinstance(per_page, int):
                raise ValueError("Parameter 'per_page' must be an integer.")
            if not 1 <= per_page <= 100:
                raise ValueError("Parameter 'per_page' must be between 1 and 100.")
            params["per_page"] = per_page
        if cursor is not None:
            normalized_cursor = str(cursor).strip()
            if not normalized_cursor:
                raise ValueError("Parameter 'cursor' must not be empty.")
            params["cursor"] = normalized_cursor
        return self._request("account/usage/transactions", params=params)

    def iter_account_usage_transactions(
        self,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
        endpoint: Optional[str] = None,
        per_page: int = 25,
    ) -> Iterator[Dict[str, Any]]:
        """Yield all account usage transactions across cursor pages."""
        cursor: Optional[str] = None
        seen_cursors = set()
        while True:
            page = self.get_account_usage_transactions(
                from_date=from_date,
                to_date=to_date,
                endpoint=endpoint,
                per_page=per_page,
                cursor=cursor,
            )
            transactions = page.get("transactions") if isinstance(page, dict) else None
            pagination = page.get("pagination") if isinstance(page, dict) else None
            if not isinstance(transactions, list) or not isinstance(pagination, dict):
                raise InvalidResponseError(
                    "Account transactions response must contain a transactions "
                    "list and pagination object."
                )
            for transaction in transactions:
                if not isinstance(transaction, dict):
                    raise InvalidResponseError(
                        "Account transactions entries must be JSON objects."
                    )
                yield transaction

            next_cursor = pagination.get("next_cursor")
            has_more = pagination.get("has_more")
            if has_more is False or not next_cursor:
                return
            if next_cursor in seen_cursors:
                raise InvalidResponseError(
                    "Account transactions pagination repeated a cursor."
                )
            seen_cursors.add(next_cursor)
            cursor = str(next_cursor)

    def get_account_subscription(self) -> Dict[str, Any]:
        """Return the account's current subscription and included features."""
        return self._request("account/subscription")

    def list_api_keys(self) -> Dict[str, Any]:
        """List active API keys in the server's masked representation."""
        return self._request("account/api-keys")

    def create_api_key(self) -> Dict[str, Any]:
        """
        Create an API key using a Bearer token with ``account:keys``.

        The full key is returned by the server only once.
        """
        if not self.bearer_token:
            raise AuthenticationError(
                "Creating an API key requires a Bearer token with the "
                "'account:keys' ability."
            )
        # The endpoint has no documented idempotency key. Avoid retrying a
        # response-lost POST because that could create multiple credentials.
        return self._post("account/api-keys", max_retries=1)

    def revoke_api_key(self, api_key_id: Union[str, int]) -> Dict[str, Any]:
        """Revoke an API key using a Bearer token with ``account:keys``."""
        if not self.bearer_token:
            raise AuthenticationError(
                "Revoking an API key requires a Bearer token with the "
                "'account:keys' ability."
            )
        normalized_id = str(api_key_id).strip()
        if not normalized_id:
            raise ValueError("Parameter 'api_key_id' is required.")
        return self._delete(f"account/api-keys/{quote(normalized_id, safe='')}")

    # -------------------------------------------------------------------
    # Signals
    # -------------------------------------------------------------------

    def list_signals(
        self,
        cursor: Optional[str] = None,
        topics: Optional[Union[str, Enum, Iterable[Union[str, Enum]]]] = None,
        organization_ids: Optional[Union[str, Iterable[str]]] = None,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
    ) -> Dict[str, Any]:
        """Return one fixed-size, cursor-paginated page of company signals."""
        params: Dict[str, Any] = {}
        if cursor is not None:
            normalized_cursor = str(cursor).strip()
            if not normalized_cursor:
                raise ValueError("Parameter 'cursor' must not be empty.")
            params["cursor"] = normalized_cursor

        normalized_topics = self._csv_query_value(topics, "topics")
        if normalized_topics is not None:
            topic_values = normalized_topics.split(",")
            unknown_topics = [
                topic for topic in topic_values if topic not in SIGNAL_TOPICS
            ]
            if unknown_topics:
                raise ValueError(
                    "Unsupported signal topic(s): "
                    + ", ".join(unknown_topics)
                    + ". Valid values are: "
                    + ", ".join(SIGNAL_TOPICS)
                )
            params["topics"] = normalized_topics

        normalized_organization_ids = self._csv_query_value(
            organization_ids,
            "organization_ids",
        )
        if normalized_organization_ids is not None:
            params["organization_ids"] = normalized_organization_ids

        normalized_from = self._date_query_value(from_date, "from_date")
        normalized_to = self._date_query_value(to_date, "to_date")
        if normalized_from is not None:
            params["from"] = normalized_from
        if normalized_to is not None:
            params["to"] = normalized_to
        return self._request("signals", params=params)

    def iter_signals(
        self,
        topics: Optional[Union[str, Enum, Iterable[Union[str, Enum]]]] = None,
        organization_ids: Optional[Union[str, Iterable[str]]] = None,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
        max_results: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield signals lazily while preserving filters across cursor pages."""
        if max_results is not None:
            if isinstance(max_results, bool) or not isinstance(max_results, int):
                raise ValueError("Parameter 'max_results' must be an integer.")
            if max_results < 1:
                raise ValueError("Parameter 'max_results' must be at least 1.")

        cursor: Optional[str] = None
        seen_cursors = set()
        yielded = 0
        while True:
            page = self.list_signals(
                cursor=cursor,
                topics=topics,
                organization_ids=organization_ids,
                from_date=from_date,
                to_date=to_date,
            )
            signals = page.get("signals") if isinstance(page, dict) else None
            pagination = page.get("pagination") if isinstance(page, dict) else None
            if not isinstance(signals, list) or not isinstance(pagination, dict):
                raise InvalidResponseError(
                    "Signals response must contain a signals list and "
                    "pagination object."
                )
            for signal in signals:
                if not isinstance(signal, dict):
                    raise InvalidResponseError(
                        "Signals entries must be JSON objects."
                    )
                yield signal
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return

            next_cursor = pagination.get("next_cursor")
            if not pagination.get("has_more") or not next_cursor:
                return
            if next_cursor in seen_cursors:
                raise InvalidResponseError("Signals pagination repeated a cursor.")
            seen_cursors.add(next_cursor)
            cursor = str(next_cursor)

    def get_signal_catalog(self) -> Dict[str, Any]:
        """Return the public Signals topic catalog."""
        return self._request("signals/catalog")

    def get_signal(self, signal_id: str) -> Dict[str, Any]:
        """Return one signal by its stable event ID."""
        normalized_id = str(signal_id).strip()
        if not normalized_id:
            raise ValueError("Parameter 'signal_id' is required.")
        return self._request(f"signals/{quote(normalized_id, safe='')}")

    # -------------------------------------------------------------------
    # Monitoring (monitors, webhook endpoints, deliveries, events)
    # -------------------------------------------------------------------

    @staticmethod
    def _validate_public_id(
        value: Any,
        pattern: "re.Pattern",
        param_name: str,
        example: str,
    ) -> str:
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ValueError(
                f"Parameter '{param_name}' must be a public id like "
                f"'{example}' (got {value!r})."
            )
        return value

    @staticmethod
    def _validate_poll_interval(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Parameter 'poll_interval_days' must be an integer.")
        if not 1 <= value <= 30:
            raise ValueError(
                "Parameter 'poll_interval_days' must be between 1 and 30."
            )
        return value

    def get_monitoring_pricing(
        self,
        poll_interval_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Return the current monitoring pricing policy, topic entitlement and a
        fresh-cycle estimate. Free.

        :param poll_interval_days: Optional interval (1-30 days, default 30)
                                   used for the returned estimate.
        """
        params: Dict[str, Any] = {}
        if poll_interval_days is not None:
            params["poll_interval_days"] = self._validate_poll_interval(
                poll_interval_days
            )
        return self._request("account/monitoring/pricing", params=params)

    def list_monitors(self) -> Dict[str, Any]:
        """Return the newest 100 non-archived monitors (no cursor). Free."""
        return self._request("account/monitors", params={})

    def create_monitor(
        self,
        entity_id: str,
        poll_interval_days: int,
        endpoint_ids: Union[str, Iterable[str]],
        label: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a monitor for one organization and queue its free baseline.

        The request itself charges zero credits and returns HTTP 202 with the
        monitor in status ``initializing``. Activation and the first 10-credit
        cycle floor happen asynchronously after the baseline completes.

        :param entity_id: Organization entity id (e.g. from
                          :meth:`fetch_organization`).
        :param poll_interval_days: Polling interval, 1-30 days.
        :param endpoint_ids: One or more owned, active, verified webhook
                             endpoint ids (``wep_...``).
        :param label: Optional display label (max 200 characters).
        :param idempotency_key: Optional explicit ``Idempotency-Key``;
                                generated when omitted.
        """
        if not isinstance(entity_id, str) or not _MONITOR_ENTITY_ID_PATTERN.fullmatch(
            entity_id
        ):
            raise ValueError(
                "Parameter 'entity_id' must be a 1-128 character organization "
                "id using [A-Za-z0-9._~-]."
            )
        if isinstance(endpoint_ids, str):
            endpoint_values: List[str] = [endpoint_ids]
        else:
            endpoint_values = [str(item) for item in endpoint_ids]
        deduped_endpoints: List[str] = []
        for endpoint_id in endpoint_values:
            self._validate_public_id(
                endpoint_id,
                _WEBHOOK_ENDPOINT_ID_PATTERN,
                "endpoint_ids",
                "wep_01hzy2q6j3g5m8v9x0abcde123",
            )
            if endpoint_id not in deduped_endpoints:
                deduped_endpoints.append(endpoint_id)
        if not deduped_endpoints:
            raise ValueError("Parameter 'endpoint_ids' must contain at least one id.")
        if label is not None and (not isinstance(label, str) or len(label) > 200):
            raise ValueError(
                "Parameter 'label' must be a string of at most 200 characters."
            )

        body: Dict[str, Any] = {
            "entity_id": entity_id,
            "poll_interval_days": self._validate_poll_interval(poll_interval_days),
            "endpoint_ids": deduped_endpoints,
        }
        if label is not None:
            body["label"] = label
        return self._mutate(
            "POST",
            "account/monitors",
            json_body=body,
            idempotency_key=idempotency_key,
        )

    def get_monitor(self, monitor_id: str) -> Dict[str, Any]:
        """
        Return one monitor with its active billing-cycle summary (or null)
        and the newest 20 poll runs. Archived monitors remain readable. Free.
        """
        self._validate_public_id(
            monitor_id, _MONITOR_ID_PATTERN, "monitor_id", "mon_01hzy2q6j3g5m8v9x0abcde123"
        )
        return self._request(f"account/monitors/{monitor_id}", params={})

    def update_monitor(
        self,
        monitor_id: str,
        poll_interval_days: int,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Change a monitor's polling interval prospectively.

        Cannot change label or destinations and never refunds or rewrites
        settled charges.
        """
        self._validate_public_id(
            monitor_id, _MONITOR_ID_PATTERN, "monitor_id", "mon_01hzy2q6j3g5m8v9x0abcde123"
        )
        body = {
            "poll_interval_days": self._validate_poll_interval(poll_interval_days),
        }
        return self._mutate(
            "PATCH",
            f"account/monitors/{monitor_id}",
            json_body=body,
            idempotency_key=idempotency_key,
        )

    def pause_monitor(
        self,
        monitor_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Pause an active monitor (``paused_user``); every other state is a
        200 no-op. Pausing ``initializing`` does not stop the baseline or a
        possible activation floor - archive instead to stop before
        activation. No refund.
        """
        self._validate_public_id(
            monitor_id, _MONITOR_ID_PATTERN, "monitor_id", "mon_01hzy2q6j3g5m8v9x0abcde123"
        )
        return self._mutate(
            "POST",
            f"account/monitors/{monitor_id}/pause",
            idempotency_key=idempotency_key,
        )

    def resume_monitor(
        self,
        monitor_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resume a paused monitor.

        Requeues an incomplete baseline for free. With a completed baseline
        the API rechecks policy, endpoints and topic access before funding;
        it reuses a live funded cycle for 0 credits or charges a new
        10-credit floor. Inspect ``meta.activated``, ``meta.baseline_queued``
        and ``meta.billing`` in the response.

        """
        self._validate_public_id(
            monitor_id, _MONITOR_ID_PATTERN, "monitor_id", "mon_01hzy2q6j3g5m8v9x0abcde123"
        )
        return self._mutate(
            "POST",
            f"account/monitors/{monitor_id}/resume",
            idempotency_key=idempotency_key,
        )

    def archive_monitor(
        self,
        monitor_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Archive a monitor (never hard-deletes). History stays readable."""
        self._validate_public_id(
            monitor_id, _MONITOR_ID_PATTERN, "monitor_id", "mon_01hzy2q6j3g5m8v9x0abcde123"
        )
        return self._mutate(
            "DELETE",
            f"account/monitors/{monitor_id}",
            idempotency_key=idempotency_key,
        )

    # -- Webhook endpoints ----------------------------------------------

    def list_webhook_endpoints(self) -> Dict[str, Any]:
        """
        Return all non-archived webhook endpoints (maximum 10). URLs and
        custom headers are masked. Free.
        """
        return self._request("account/webhook-endpoints", params={})

    def create_webhook_endpoint(
        self,
        name: str,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a webhook receiver endpoint.

        Returns HTTP 201 with the endpoint in ``pending_verification`` plus a
        one-time ``whsec_`` signing secret - store it immediately, it is
        never shown again. Requires a Bearer token with ``account:read`` and
        ``account:keys``.

        :param name: Display name (1-120 characters).
        :param url: Public HTTPS URL on port 443. IP literals, userinfo,
                    fragments and private DNS answers are rejected.
        :param headers: Optional write-only custom headers (encrypted at
                        rest; transport, forwarding and ``webhook-*`` names
                        are reserved).
        """
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError(
                "Parameter 'name' must be a non-empty string of at most 120 "
                "characters."
            )
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Parameter 'url' is required.")
        body: Dict[str, Any] = {"name": name, "url": url}
        if headers is not None:
            if not isinstance(headers, Mapping) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
            ):
                raise ValueError(
                    "Parameter 'headers' must map string names to string values."
                )
            body["headers"] = dict(headers)
        return self._mutate(
            "POST",
            "account/webhook-endpoints",
            json_body=body,
            idempotency_key=idempotency_key,
        )

    def verify_webhook_endpoint(
        self,
        endpoint_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a synchronous signed challenge to a ``pending_verification``
        endpoint. The receiver must answer 2xx and echo ``data.challenge`` in
        a ``webhook-verification`` header. A successful first verification
        activates the endpoint immediately.

        A failed challenge is a normal outcome: this method returns the
        ``{"verified": false, ...}`` payload instead of raising. An already
        verified or disabled endpoint returns its stored state without
        network I/O and is not re-enabled; use
        :meth:`enable_webhook_endpoint` to reactivate after a disable.

        Never retried automatically beyond the documented safe cases: a 409
        ambiguity raises :class:`IdempotencyConflictError` and must not be
        re-driven with a new key.
        """
        self._validate_public_id(
            endpoint_id,
            _WEBHOOK_ENDPOINT_ID_PATTERN,
            "endpoint_id",
            "wep_01hzy2q6j3g5m8v9x0abcde123",
        )
        return self._mutate(
            "POST",
            f"account/webhook-endpoints/{endpoint_id}/verify",
            idempotency_key=idempotency_key,
            network_io=True,
            verified_result_on_422=True,
        )

    def rotate_webhook_endpoint_secret(
        self,
        endpoint_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Rotate the signing secret; returns a new one-time ``whsec_`` value.

        Normal deliveries, tests and samples are signed with both current and
        predecessor secrets for seven days; verification challenges use only
        the current secret. Requires ``account:read`` plus ``account:keys``.
        """
        self._validate_public_id(
            endpoint_id,
            _WEBHOOK_ENDPOINT_ID_PATTERN,
            "endpoint_id",
            "wep_01hzy2q6j3g5m8v9x0abcde123",
        )
        return self._mutate(
            "POST",
            f"account/webhook-endpoints/{endpoint_id}/rotate-secret",
            idempotency_key=idempotency_key,
        )

    def test_webhook_endpoint(
        self,
        endpoint_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a synchronous signed ``endpoint.test`` attempt.

        HTTP 200 means the attempt was recorded, not necessarily delivered -
        inspect ``delivery.status`` in the response.
        """
        self._validate_public_id(
            endpoint_id,
            _WEBHOOK_ENDPOINT_ID_PATTERN,
            "endpoint_id",
            "wep_01hzy2q6j3g5m8v9x0abcde123",
        )
        return self._mutate(
            "POST",
            f"account/webhook-endpoints/{endpoint_id}/test",
            idempotency_key=idempotency_key,
            network_io=True,
        )

    def enable_webhook_endpoint(
        self,
        endpoint_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Enable a verified endpoint - needed to reactivate after a disable
        (a successful first verification activates automatically). Requires
        ``account:read`` plus ``account:keys``.
        """
        return self._set_webhook_endpoint_state(
            endpoint_id, "enable", idempotency_key
        )

    def disable_webhook_endpoint(
        self,
        endpoint_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Disable an endpoint. Monitors that lose their last active endpoint
        are parked in ``paused_configuration``. Requires ``account:read``
        plus ``account:keys``.
        """
        return self._set_webhook_endpoint_state(
            endpoint_id, "disable", idempotency_key
        )

    def _set_webhook_endpoint_state(
        self,
        endpoint_id: str,
        state: str,
        idempotency_key: Optional[str],
    ) -> Dict[str, Any]:
        self._validate_public_id(
            endpoint_id,
            _WEBHOOK_ENDPOINT_ID_PATTERN,
            "endpoint_id",
            "wep_01hzy2q6j3g5m8v9x0abcde123",
        )
        return self._mutate(
            "POST",
            f"account/webhook-endpoints/{endpoint_id}/{state}",
            idempotency_key=idempotency_key,
        )

    def archive_webhook_endpoint(
        self,
        endpoint_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Archive an endpoint and its subscriptions. Requires ``account:read``
        plus ``account:keys``.
        """
        self._validate_public_id(
            endpoint_id,
            _WEBHOOK_ENDPOINT_ID_PATTERN,
            "endpoint_id",
            "wep_01hzy2q6j3g5m8v9x0abcde123",
        )
        return self._mutate(
            "DELETE",
            f"account/webhook-endpoints/{endpoint_id}",
            idempotency_key=idempotency_key,
        )

    # -- Webhook deliveries & events ------------------------------------

    def list_webhook_deliveries(
        self,
        endpoint_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return the newest 50 delivery summaries (no cursor/detail). Free.

        :param endpoint_id: Optional ``wep_...`` id to filter by endpoint.
        """
        params: Dict[str, Any] = {}
        if endpoint_id is not None:
            self._validate_public_id(
                endpoint_id,
                _WEBHOOK_ENDPOINT_ID_PATTERN,
                "endpoint_id",
                "wep_01hzy2q6j3g5m8v9x0abcde123",
            )
            params["endpoint"] = endpoint_id
        return self._request("account/webhook-deliveries", params=params)

    def retry_webhook_delivery(
        self,
        delivery_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retry an eligible retained failed delivery with the same message id
        and body. The public ``delivery.attempts`` counter resets to 0;
        append-only audit attempt numbers remain monotonic.
        """
        self._validate_public_id(
            delivery_id,
            _WEBHOOK_DELIVERY_ID_PATTERN,
            "delivery_id",
            "del_01hzy2q6j3g5m8v9x0abcde123",
        )
        return self._mutate(
            "POST",
            f"account/webhook-deliveries/{delivery_id}/retry",
            idempotency_key=idempotency_key,
        )

    def list_webhook_events(self) -> Dict[str, Any]:
        """Return the newest 50 webhook event summaries (no body/replay). Free."""
        return self._request("account/webhook-events", params={})

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
        # This is a non-security cache namespace. Keep SHA-1 for compatibility
        # with snapshot filenames produced by earlier SDK releases.
        return hashlib.sha1(raw).hexdigest()[:8]  # noqa: S324

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
