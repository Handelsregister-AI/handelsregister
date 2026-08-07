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


class ConflictError(APIError):
    """Raised for HTTP 409 responses (duplicates and domain conflicts)."""


class IdempotencyConflictError(ConflictError):
    """
    Raised for HTTP 409 idempotency conflicts and ambiguities.

    The API either saw the same ``Idempotency-Key`` with different parameters
    or cannot prove the outcome of an in-progress/ambiguous operation. Never
    retry automatically: for endpoint verify/test operations the receiver may
    already have been contacted, so re-driving the request or inventing a new
    key can duplicate side effects. Inspect the stored operation state (or
    contact support) instead.
    """


class IdempotencyKeyRequiredError(APIError):
    """Raised for HTTP 428 responses when a mutation is missing its Idempotency-Key."""


class ServerError(APIError):
    """Raised when the API returns a 5xx response."""


class ServiceUnavailableError(ServerError):
    """
    Raised for HTTP 503 kill-switch responses (``temporarily_unavailable``).

    The operation never started and the idempotency key was not claimed, so
    the same request can safely be retried later with the same key.
    """


class WebhookSignatureError(HandelsregisterError):
    """Raised when an incoming webhook fails signature or timestamp verification."""
