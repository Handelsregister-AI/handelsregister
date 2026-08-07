"""
Receiver-side helpers for handelsregister.ai monitoring webhooks.

Verifies the ``webhook-signature`` header documented for outbound webhooks:

    signed_content = webhook-id + "." + webhook-timestamp + "." + exact_raw_body
    expected = base64(HMAC-SHA256(base64_decode(secret after "whsec_"), signed_content))
    webhook-signature = "v1," + expected

The header may carry several space-separated ``v1,<base64>`` candidates
(current and predecessor secret during the seven-day rotation grace); the
delivery is authentic when any candidate matches any known secret.

Usage in a receiver::

    from handelsregister.webhooks import construct_event, verification_response_headers

    event = construct_event(raw_body, request_headers, secret)
    if event["type"] == "endpoint.verification":
        return Response(status=204, headers=verification_response_headers(event))
    seen_before = not dedupe_store.add(event["id"])  # deduplicate webhook-id
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from .exceptions import WebhookSignatureError

__all__ = [
    "DEFAULT_TOLERANCE_SECONDS",
    "VERIFICATION_RESPONSE_HEADER",
    "construct_event",
    "extract_verification_challenge",
    "verification_response_headers",
    "verify_webhook_signature",
]

#: Header a receiver must echo (with the challenge value) to pass verification.
VERIFICATION_RESPONSE_HEADER = "webhook-verification"

#: Default allowed clock skew between the ``webhook-timestamp`` header and now.
DEFAULT_TOLERANCE_SECONDS = 300

_SECRET_PREFIX = "whsec_"  # noqa: S105 - public format prefix, not a credential


def _decode_secret(secret: str) -> bytes:
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError("Webhook secret must be a non-empty string.")
    material = secret.strip()
    if material.startswith(_SECRET_PREFIX):
        material = material[len(_SECRET_PREFIX):]
    try:
        return base64.b64decode(material, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "Webhook secret is not valid base64. Pass the full 'whsec_...' "
            "value returned when the endpoint was created or rotated."
        ) from exc


def _normalize_secrets(secret: Union[str, Iterable[str]]) -> List[bytes]:
    if isinstance(secret, str):
        values: Iterable[str] = [secret]
    else:
        values = list(secret)
        if not values:
            raise ValueError("At least one webhook secret is required.")
    return [_decode_secret(value) for value in values]


def _header_lookup(headers: Mapping[str, Any], name: str) -> Optional[str]:
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name:
            return str(value)
    return None


def _payload_bytes(payload: Union[str, bytes, bytearray]) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise ValueError(
        "Webhook payload must be the exact raw request body as bytes or str."
    )


def verify_webhook_signature(
    payload: Union[str, bytes, bytearray],
    headers: Mapping[str, Any],
    secret: Union[str, Iterable[str]],
    tolerance_seconds: Optional[int] = DEFAULT_TOLERANCE_SECONDS,
) -> None:
    """
    Verify an incoming webhook request; raise :class:`WebhookSignatureError`
    if it is not authentic.

    Always verify the exact raw request bytes before parsing them.

    :param payload: Exact raw request body (bytes preferred).
    :param headers: Request headers (matched case-insensitively); must
                    contain ``webhook-id``, ``webhook-timestamp`` and
                    ``webhook-signature``.
    :param secret: The endpoint's ``whsec_`` signing secret, or several
                   (e.g. current and previous during rotation).
    :param tolerance_seconds: Maximum allowed clock skew for the timestamp
                              header; pass ``None`` to skip the check.
    """
    body = _payload_bytes(payload)
    secrets = _normalize_secrets(secret)

    webhook_id = _header_lookup(headers, "webhook-id")
    webhook_timestamp = _header_lookup(headers, "webhook-timestamp")
    webhook_signature = _header_lookup(headers, "webhook-signature")
    if not webhook_id or not webhook_timestamp or not webhook_signature:
        raise WebhookSignatureError(
            "Missing webhook-id, webhook-timestamp or webhook-signature header."
        )

    try:
        timestamp = int(str(webhook_timestamp).strip())
    except (TypeError, ValueError):
        raise WebhookSignatureError(
            "Header 'webhook-timestamp' is not a Unix-seconds integer."
        ) from None
    if tolerance_seconds is not None:
        skew = abs(time.time() - timestamp)
        if skew > tolerance_seconds:
            raise WebhookSignatureError(
                f"Webhook timestamp is outside the allowed tolerance of "
                f"{tolerance_seconds} seconds (skew: {skew:.0f}s)."
            )

    signed_content = (
        webhook_id.encode("utf-8") + b"." + str(timestamp).encode("utf-8") + b"." + body
    )
    expected = [
        base64.b64encode(
            hmac.new(key, signed_content, hashlib.sha256).digest()
        ).decode("ascii")
        for key in secrets
    ]

    for candidate in webhook_signature.split(" "):
        candidate = candidate.strip()
        if not candidate.startswith("v1,"):
            continue
        candidate_value = candidate[len("v1,"):]
        for expected_value in expected:
            if hmac.compare_digest(candidate_value, expected_value):
                return

    raise WebhookSignatureError("Webhook signature does not match any known secret.")


def construct_event(
    payload: Union[str, bytes, bytearray],
    headers: Mapping[str, Any],
    secret: Union[str, Iterable[str]],
    tolerance_seconds: Optional[int] = DEFAULT_TOLERANCE_SECONDS,
) -> Dict[str, Any]:
    """
    Verify an incoming webhook request and return the parsed event envelope
    (``{id, event_id?, type, timestamp, schema_version, data}``).

    Raises :class:`WebhookSignatureError` when verification fails and
    :class:`ValueError` when the verified body is not a JSON object.

    Deduplicate on ``event["id"]`` (the ``webhook-id``): delivery is
    at-least-once with no cross-event ordering guarantee.
    """
    verify_webhook_signature(
        payload, headers, secret, tolerance_seconds=tolerance_seconds
    )
    try:
        event = json.loads(_payload_bytes(payload).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Verified webhook body is not valid JSON: {exc}") from exc
    if not isinstance(event, dict):
        raise ValueError("Verified webhook body is not a JSON object.")
    return event


def extract_verification_challenge(event: Mapping[str, Any]) -> Optional[str]:
    """
    Return the challenge string of an ``endpoint.verification`` event, or
    ``None`` for any other event type.
    """
    if event.get("type") != "endpoint.verification":
        return None
    data = event.get("data")
    if isinstance(data, Mapping):
        challenge = data.get("challenge")
        if isinstance(challenge, str) and challenge:
            return challenge
    return None


def verification_response_headers(event: Mapping[str, Any]) -> Dict[str, str]:
    """
    Return the response headers a receiver must send (with any 2xx status)
    to answer an ``endpoint.verification`` challenge.

    Raises :class:`ValueError` if the event is not a verification challenge.
    """
    challenge = extract_verification_challenge(event)
    if challenge is None:
        raise ValueError("Event is not an 'endpoint.verification' challenge.")
    return {VERIFICATION_RESPONSE_HEADER: challenge}
