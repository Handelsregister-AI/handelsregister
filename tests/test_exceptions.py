import pytest

from handelsregister.exceptions import (
    HandelsregisterError,
    InvalidResponseError,
    AuthenticationError
)


def test_exception_hierarchy():
    """Test that the exception hierarchy is correct."""
    # Check inheritance
    assert issubclass(InvalidResponseError, HandelsregisterError)
    assert issubclass(AuthenticationError, HandelsregisterError)
    
    # Check instance relationships
    assert isinstance(InvalidResponseError(), HandelsregisterError)
    assert isinstance(AuthenticationError(), HandelsregisterError)


def test_exception_messages():
    """Test that exception messages are preserved."""
    error_message = "Test error message"
    
    # Test base exception
    exc = HandelsregisterError(error_message)
    assert str(exc) == error_message
    
    # Test derived exceptions
    exc = InvalidResponseError(error_message)
    assert str(exc) == error_message
    
    exc = AuthenticationError(error_message)
    assert str(exc) == error_message
