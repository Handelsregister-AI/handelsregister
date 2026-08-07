"""Tests for receiver-side webhook signature verification helpers."""

import base64
import hashlib
import hmac
import json
import time

import pytest

from handelsregister import (
    VERIFICATION_RESPONSE_HEADER,
    WebhookSignatureError,
    construct_event,
    extract_verification_challenge,
    verification_response_headers,
    verify_webhook_signature,
)

SECRET_BYTES = b"0123456789abcdef0123456789abcdef"
SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode("ascii")
OTHER_SECRET_BYTES = b"fedcba9876543210fedcba9876543210"
OTHER_SECRET = "whsec_" + base64.b64encode(OTHER_SECRET_BYTES).decode("ascii")

WEBHOOK_ID = "msg_01j7n1abcdefghijklmnopqrst"


def _sign(body, timestamp, secret_bytes=SECRET_BYTES, webhook_id=WEBHOOK_ID):
    if isinstance(body, str):
        body = body.encode("utf-8")
    signed_content = (
        webhook_id.encode() + b"." + str(timestamp).encode() + b"." + body
    )
    digest = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode("ascii")


def _headers(body, timestamp=None, signature=None, secret_bytes=SECRET_BYTES):
    timestamp = int(time.time()) if timestamp is None else timestamp
    return {
        "webhook-id": WEBHOOK_ID,
        "webhook-timestamp": str(timestamp),
        "webhook-signature": signature or _sign(body, timestamp, secret_bytes),
    }


@pytest.fixture
def event_body():
    return json.dumps(
        {
            "id": WEBHOOK_ID,
            "event_id": "evt_01j7n3abcdefghijklmnopqrst",
            "type": "organization.signal.detected",
            "timestamp": "2026-08-02T12:05:00.000Z",
            "schema_version": 1,
            "data": {"monitor": {"id": "mon_x"}, "signal": {}},
        }
    ).encode("utf-8")


def test_valid_signature_passes(event_body):
    verify_webhook_signature(event_body, _headers(event_body), SECRET)


def test_str_payload_is_accepted(event_body):
    body_str = event_body.decode("utf-8")
    verify_webhook_signature(body_str, _headers(event_body), SECRET)


def test_headers_are_matched_case_insensitively(event_body):
    headers = {
        key.title(): value for key, value in _headers(event_body).items()
    }
    verify_webhook_signature(event_body, headers, SECRET)


def test_secret_without_prefix_is_accepted(event_body):
    raw_secret = base64.b64encode(SECRET_BYTES).decode("ascii")
    verify_webhook_signature(event_body, _headers(event_body), raw_secret)


def test_multiple_space_separated_candidates(event_body):
    timestamp = int(time.time())
    rotated = _sign(event_body, timestamp, OTHER_SECRET_BYTES)
    current = _sign(event_body, timestamp)
    headers = _headers(
        event_body, timestamp=timestamp, signature=f"{rotated} {current}"
    )
    verify_webhook_signature(event_body, headers, SECRET)


def test_multiple_known_secrets_during_rotation(event_body):
    headers = _headers(event_body, secret_bytes=OTHER_SECRET_BYTES)
    verify_webhook_signature(event_body, headers, [SECRET, OTHER_SECRET])


def test_non_v1_schemes_are_ignored(event_body):
    timestamp = int(time.time())
    good = _sign(event_body, timestamp)
    headers = _headers(
        event_body, timestamp=timestamp, signature=f"v2,AAAA {good}"
    )
    verify_webhook_signature(event_body, headers, SECRET)


def test_wrong_signature_is_rejected(event_body):
    headers = _headers(event_body, signature="v1," + base64.b64encode(b"x" * 32).decode())
    with pytest.raises(WebhookSignatureError, match="does not match"):
        verify_webhook_signature(event_body, headers, SECRET)


def test_tampered_body_is_rejected(event_body):
    headers = _headers(event_body)
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(event_body + b" ", headers, SECRET)


@pytest.mark.parametrize(
    "missing", ["webhook-id", "webhook-timestamp", "webhook-signature"]
)
def test_missing_headers_are_rejected(event_body, missing):
    headers = _headers(event_body)
    headers.pop(missing)
    with pytest.raises(WebhookSignatureError, match="Missing"):
        verify_webhook_signature(event_body, headers, SECRET)


def test_non_integer_timestamp_is_rejected(event_body):
    headers = _headers(event_body)
    headers["webhook-timestamp"] = "not-a-number"
    with pytest.raises(WebhookSignatureError, match="Unix-seconds"):
        verify_webhook_signature(event_body, headers, SECRET)


@pytest.mark.parametrize("skew", [-4000, 4000])
def test_timestamp_outside_tolerance_is_rejected(event_body, skew):
    timestamp = int(time.time()) + skew
    headers = _headers(event_body, timestamp=timestamp)
    with pytest.raises(WebhookSignatureError, match="tolerance"):
        verify_webhook_signature(event_body, headers, SECRET)


def test_tolerance_can_be_disabled(event_body):
    timestamp = int(time.time()) - 4000
    headers = _headers(event_body, timestamp=timestamp)
    verify_webhook_signature(event_body, headers, SECRET, tolerance_seconds=None)


def test_invalid_secret_raises_value_error(event_body):
    with pytest.raises(ValueError, match="base64"):
        verify_webhook_signature(
            event_body, _headers(event_body), "whsec_%%%not-base64%%%"
        )


def test_empty_secret_list_raises_value_error(event_body):
    with pytest.raises(ValueError, match="secret"):
        verify_webhook_signature(event_body, _headers(event_body), [])


def test_construct_event_returns_parsed_envelope(event_body):
    event = construct_event(event_body, _headers(event_body), SECRET)
    assert event["type"] == "organization.signal.detected"
    assert event["id"] == WEBHOOK_ID


def test_construct_event_rejects_non_json_body():
    body = b"not json"
    with pytest.raises(ValueError, match="JSON"):
        construct_event(body, _headers(body), SECRET)


def test_construct_event_rejects_bad_signature(event_body):
    headers = _headers(event_body)
    with pytest.raises(WebhookSignatureError):
        construct_event(event_body + b"x", headers, SECRET)


def test_extract_verification_challenge():
    event = {
        "id": WEBHOOK_ID,
        "type": "endpoint.verification",
        "schema_version": 1,
        "data": {"challenge": "40f2abc"},
    }
    assert extract_verification_challenge(event) == "40f2abc"


def test_extract_verification_challenge_other_types_return_none():
    assert (
        extract_verification_challenge(
            {"type": "organization.signal.detected", "data": {"challenge": "x"}}
        )
        is None
    )


def test_verification_response_headers():
    event = {"type": "endpoint.verification", "data": {"challenge": "40f2abc"}}
    assert verification_response_headers(event) == {
        VERIFICATION_RESPONSE_HEADER: "40f2abc"
    }


def test_verification_response_headers_rejects_other_events():
    with pytest.raises(ValueError, match="verification"):
        verification_response_headers({"type": "endpoint.test", "data": {}})


def test_verification_challenge_roundtrip_with_construct_event():
    body = json.dumps(
        {
            "id": WEBHOOK_ID,
            "type": "endpoint.verification",
            "timestamp": "2026-08-02T12:00:00.000Z",
            "schema_version": 1,
            "data": {"challenge": "40f2abc"},
        }
    ).encode("utf-8")
    event = construct_event(body, _headers(body), SECRET)
    assert verification_response_headers(event) == {
        "webhook-verification": "40f2abc"
    }
