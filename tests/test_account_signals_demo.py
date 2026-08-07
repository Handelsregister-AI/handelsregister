import pytest

from examples.account_signals_demo import load_extra_headers, redact


def test_demo_redacts_common_secret_field_spellings():
    payload = {
        "api_key": {"id": 1, "key": "full-key"},
        "accessToken": "access-token",
        "client-secret": "client-secret",
        "Authorization": "Bearer token",
        "key_last_8": "12345678",
        "meta": {"request_id": "request-1"},
    }

    safe = redact(payload)

    assert safe["api_key"] == "<redacted>"
    assert safe["accessToken"] == "<redacted>"
    assert safe["client-secret"] == "<redacted>"
    assert safe["Authorization"] == "<redacted>"
    assert safe["key_last_8"] == "12345678"
    assert safe["meta"]["request_id"] == "request-1"


def test_demo_loads_generic_extra_headers(monkeypatch):
    monkeypatch.setenv(
        "HANDELSREGISTER_EXTRA_HEADERS_JSON",
        '{"X-Gateway-Token": "secret"}',
    )

    assert load_extra_headers() == {"X-Gateway-Token": "secret"}


@pytest.mark.parametrize("value", ["[]", '"value"', "null", "{invalid"])
def test_demo_rejects_invalid_extra_header_json(monkeypatch, value):
    monkeypatch.setenv("HANDELSREGISTER_EXTRA_HEADERS_JSON", value)

    with pytest.raises(ValueError):
        load_extra_headers()
