from typing import Any, Dict, Optional


class HandelsregisterError(Exception):
    """Base exception for all Handelsregister-related errors."""


class APIError(HandelsregisterError):
    """Base class for HTTP API errors with lossless response context."""

    def __init__(
        self,
        message: str = "",
        *,
        status_code: Optional[int] = None,
        payload: Any = None,
        response_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.response_headers = response_headers or {}

    @property
    def meta(self) -> Dict[str, Any]:
        if isinstance(self.payload, dict) and isinstance(self.payload.get("meta"), dict):
            return self.payload["meta"]
        return {}

    @property
    def detail(self) -> Any:
        return self.payload.get("detail") if isinstance(self.payload, dict) else None

class InvalidResponseError(HandelsregisterError):
    """Raised when the API response is invalid or unexpected."""


class AuthenticationError(APIError):
    """Raised when invalid or missing API key is supplied."""


class RequestValidationError(APIError):
    """Raised for HTTP 400 validation failures."""


class InsufficientCreditsError(APIError):
    """Raised for HTTP 402 responses."""


class ForbiddenError(APIError):
    """Raised for HTTP 403 responses."""


class SubscriptionRequiredError(ForbiddenError):
    """Raised when an endpoint requires a paid subscription."""


class NotFoundError(APIError):
    """Raised for HTTP 404 responses."""


class RequestTimeoutError(APIError):
    """Raised after an HTTP 408 response remains unsuccessful."""


class RateLimitError(APIError):
    """Raised when the API rate limit is exhausted."""


class ServerError(APIError):
    """Raised when the API returns a 5xx response."""
