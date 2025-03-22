class HandelsregisterError(Exception):
    """Base exception for all Handelsregister-related errors."""
    pass

class InvalidResponseError(HandelsregisterError):
    """Raised when the API response is invalid or unexpected."""
    pass

class AuthenticationError(HandelsregisterError):
    """Raised when invalid or missing API key is supplied."""
    pass
