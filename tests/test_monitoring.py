"""Tests for the monitoring & webhook management client methods."""

import inspect
import re
from unittest.mock import MagicMock, patch

import httpx
import pytest

from handelsregister import (
    Handelsregister,
    IdempotencyConflictError,
    IdempotencyKeyRequiredError,
    ServerError,
    ServiceUnavailableError,
)

MON_ID = "mon_" + "a" * 26
WEP_ID = "wep_" + "b" * 26
DEL_ID = "del_" + "c" * 26

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _mock_response(payload=None, status_code=200, headers=None, content=b"{}"):
    response = MagicMock()
    response.status_code = status_code
    response.content = content
    response.headers = headers or {}
    response.json.return_value = payload if payload is not None else {}
    # httpx raises for redirects too when they are not followed
    if status_code >= 300:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=response
        )
    else:
        response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mocked_http_client():
    with patch("httpx.Client") as httpx_client:
        session = MagicMock()
        httpx_client.return_value.__enter__.return_value = session
        yield session


@pytest.fixture
def client():
    return Handelsregister(api_key="api-key")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method_name", "args", "expected_path", "expected_params"),
    [
        ("get_monitoring_pricing", (), "/account/monitoring/pricing", {}),
        (
            "get_monitoring_pricing",
            (7,),
            "/account/monitoring/pricing",
            {"poll_interval_days": 7},
        ),
        ("list_monitors", (), "/account/monitors", {}),
        ("get_monitor", (MON_ID,), f"/account/monitors/{MON_ID}", {}),
        ("list_webhook_endpoints", (), "/account/webhook-endpoints", {}),
        ("list_webhook_deliveries", (), "/account/webhook-deliveries", {}),
        (
            "list_webhook_deliveries",
            (WEP_ID,),
            "/account/webhook-deliveries",
            {"endpoint": WEP_ID},
        ),
        ("list_webhook_events", (), "/account/webhook-events", {}),
    ],
)
def test_read_endpoints(
    mocked_http_client, client, method_name, args, expected_path, expected_params
):
    mocked_http_client.get.return_value = _mock_response({"meta": {}})

    result = getattr(client, method_name)(*args)

    assert result == {"meta": {}}
    request = mocked_http_client.get.call_args
    assert request.args[0].endswith(expected_path)
    assert request.kwargs["params"] == expected_params


# ---------------------------------------------------------------------------
# Mutations: paths, verbs, bodies, idempotency headers
# ---------------------------------------------------------------------------


def _last_mutation(mocked_http_client):
    request = mocked_http_client.request.call_args
    method, url = request.args[0], request.args[1]
    return method, url, request.kwargs


def test_create_monitor_sends_body_and_idempotency_key(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response(
        {"monitor": {"id": MON_ID}}, headers={"idempotency-status": "created"}
    )

    result = client.create_monitor(
        entity_id="cc78cf0b230aeae35c6df7ba31989bb9",
        poll_interval_days=7,
        endpoint_ids=[WEP_ID, WEP_ID],
        label="BMW AG",
    )

    assert result == {"monitor": {"id": MON_ID}}
    method, url, kwargs = _last_mutation(mocked_http_client)
    assert method == "POST"
    assert url.endswith("/account/monitors")
    assert kwargs["json"] == {
        "entity_id": "cc78cf0b230aeae35c6df7ba31989bb9",
        "poll_interval_days": 7,
        "endpoint_ids": [WEP_ID],
        "label": "BMW AG",
    }
    key = kwargs["headers"]["Idempotency-Key"]
    assert IDEMPOTENCY_KEY_PATTERN.fullmatch(key)
    assert client.last_idempotency_status == "created"


def test_create_monitor_accepts_single_endpoint_string(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response({})

    client.create_monitor(
        entity_id="abc",
        poll_interval_days=1,
        endpoint_ids=WEP_ID,
    )

    _, _, kwargs = _last_mutation(mocked_http_client)
    assert kwargs["json"]["endpoint_ids"] == [WEP_ID]
    assert "label" not in kwargs["json"]


@pytest.mark.parametrize(
    "method_name", ["create_monitor", "update_monitor", "resume_monitor"]
)
def test_monitor_mutations_do_not_expose_pricing_policy_version(method_name):
    parameters = inspect.signature(getattr(Handelsregister, method_name)).parameters
    assert "pricing_policy_version" not in parameters


def test_explicit_idempotency_key_is_used(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response({})

    client.pause_monitor(MON_ID, idempotency_key="pause-01J7MZ1VN8N6FZQ2")

    _, _, kwargs = _last_mutation(mocked_http_client)
    assert kwargs["headers"]["Idempotency-Key"] == "pause-01J7MZ1VN8N6FZQ2"


@pytest.mark.parametrize(
    "bad_key",
    ["", "-starts-with-dash", "contains space", "ä-umlaut", "x" * 129, 42],
)
def test_invalid_idempotency_key_is_rejected(client, bad_key):
    with pytest.raises(ValueError, match="idempotency_key"):
        client.pause_monitor(MON_ID, idempotency_key=bad_key)


@pytest.mark.parametrize(
    ("method_name", "args", "expected_method", "expected_suffix"),
    [
        ("update_monitor", (MON_ID, 7), "PATCH", f"/account/monitors/{MON_ID}"),
        ("pause_monitor", (MON_ID,), "POST", f"/account/monitors/{MON_ID}/pause"),
        ("resume_monitor", (MON_ID,), "POST", f"/account/monitors/{MON_ID}/resume"),
        ("archive_monitor", (MON_ID,), "DELETE", f"/account/monitors/{MON_ID}"),
        (
            "verify_webhook_endpoint",
            (WEP_ID,),
            "POST",
            f"/account/webhook-endpoints/{WEP_ID}/verify",
        ),
        (
            "rotate_webhook_endpoint_secret",
            (WEP_ID,),
            "POST",
            f"/account/webhook-endpoints/{WEP_ID}/rotate-secret",
        ),
        (
            "test_webhook_endpoint",
            (WEP_ID,),
            "POST",
            f"/account/webhook-endpoints/{WEP_ID}/test",
        ),
        (
            "enable_webhook_endpoint",
            (WEP_ID,),
            "POST",
            f"/account/webhook-endpoints/{WEP_ID}/enable",
        ),
        (
            "disable_webhook_endpoint",
            (WEP_ID,),
            "POST",
            f"/account/webhook-endpoints/{WEP_ID}/disable",
        ),
        (
            "archive_webhook_endpoint",
            (WEP_ID,),
            "DELETE",
            f"/account/webhook-endpoints/{WEP_ID}",
        ),
        (
            "retry_webhook_delivery",
            (DEL_ID,),
            "POST",
            f"/account/webhook-deliveries/{DEL_ID}/retry",
        ),
    ],
)
def test_mutation_routes(
    mocked_http_client, client, method_name, args, expected_method, expected_suffix
):
    mocked_http_client.request.return_value = _mock_response({"ok": True})

    result = getattr(client, method_name)(*args)

    assert result == {"ok": True}
    method, url, kwargs = _last_mutation(mocked_http_client)
    assert method == expected_method
    assert url.endswith(expected_suffix)
    assert "Idempotency-Key" in kwargs["headers"]


def test_update_monitor_body(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response({})

    client.update_monitor(MON_ID, poll_interval_days=14)

    _, _, kwargs = _last_mutation(mocked_http_client)
    assert kwargs["json"] == {"poll_interval_days": 14}


def test_resume_monitor_has_no_request_body(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response({})

    client.resume_monitor(MON_ID)
    assert _last_mutation(mocked_http_client)[2]["json"] is None


def test_create_webhook_endpoint_with_custom_headers(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response(
        {"endpoint": {"id": WEP_ID}, "signing_secret": "whsec_x"}, status_code=201
    )

    result = client.create_webhook_endpoint(
        name="Production receiver",
        url="https://hooks.example.com/handelsregister",
        headers={"x-tenant": "customer-42"},
    )

    assert result["signing_secret"] == "whsec_x"
    method, url, kwargs = _last_mutation(mocked_http_client)
    assert method == "POST"
    assert url.endswith("/account/webhook-endpoints")
    assert kwargs["json"] == {
        "name": "Production receiver",
        "url": "https://hooks.example.com/handelsregister",
        "headers": {"x-tenant": "customer-42"},
    }


# ---------------------------------------------------------------------------
# Client-side validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method_name", "args", "match"),
    [
        ("get_monitor", ("bad",), "monitor_id"),
        ("get_monitor", (WEP_ID,), "monitor_id"),
        ("pause_monitor", ("mon_short",), "monitor_id"),
        ("verify_webhook_endpoint", (MON_ID,), "endpoint_id"),
        ("retry_webhook_delivery", (WEP_ID,), "delivery_id"),
        ("list_webhook_deliveries", ("nope",), "endpoint_id"),
        ("get_monitoring_pricing", (0,), "poll_interval_days"),
        ("get_monitoring_pricing", (31,), "poll_interval_days"),
        ("get_monitoring_pricing", (True,), "poll_interval_days"),
    ],
)
def test_public_id_and_interval_validation(client, method_name, args, match):
    with pytest.raises(ValueError, match=match):
        getattr(client, method_name)(*args)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (dict(entity_id="has spaces"), "entity_id"),
        (dict(entity_id=""), "entity_id"),
        (dict(poll_interval_days=0), "poll_interval_days"),
        (dict(poll_interval_days="7"), "poll_interval_days"),
        (dict(endpoint_ids=[]), "endpoint_ids"),
        (dict(endpoint_ids=["bad"]), "endpoint_ids"),
        (dict(label="x" * 201), "label"),
    ],
)
def test_create_monitor_validation(client, kwargs, match):
    defaults = dict(
        entity_id="abc",
        poll_interval_days=7,
        endpoint_ids=[WEP_ID],
    )
    defaults.update(kwargs)
    with pytest.raises(ValueError, match=match):
        client.create_monitor(**defaults)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (dict(name=""), "name"),
        (dict(name="x" * 121), "name"),
        (dict(url=""), "url"),
        (dict(headers={"x": 1}), "headers"),
        (dict(headers=[("a", "b")]), "headers"),
    ],
)
def test_create_webhook_endpoint_validation(client, kwargs, match):
    defaults = dict(name="Receiver", url="https://hooks.example.com/x")
    defaults.update(kwargs)
    with pytest.raises(ValueError, match=match):
        client.create_webhook_endpoint(**defaults)


# ---------------------------------------------------------------------------
# Error mapping & retry semantics
# ---------------------------------------------------------------------------


def test_409_idempotency_conflict_raises_and_never_retries(
    mocked_http_client, client
):
    mocked_http_client.request.return_value = _mock_response(
        {"error": "idempotency_conflict"}, status_code=409
    )

    with pytest.raises(IdempotencyConflictError):
        client.create_monitor(
            entity_id="abc",
            poll_interval_days=7,
            endpoint_ids=[WEP_ID],
        )

    assert mocked_http_client.request.call_count == 1


def test_428_missing_key_raises_dedicated_error(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response(
        {"error": "idempotency_key_required"}, status_code=428
    )

    with pytest.raises(IdempotencyKeyRequiredError):
        client.pause_monitor(MON_ID)


def test_503_kill_switch_is_retried_with_same_key(mocked_http_client, client):
    unavailable = _mock_response(
        {"error": "temporarily_unavailable"}, status_code=503
    )
    success = _mock_response({"ok": True})
    mocked_http_client.request.side_effect = [unavailable, success]

    result = client.pause_monitor(MON_ID)

    assert result == {"ok": True}
    assert mocked_http_client.request.call_count == 2
    first_key = mocked_http_client.request.call_args_list[0].kwargs["headers"][
        "Idempotency-Key"
    ]
    second_key = mocked_http_client.request.call_args_list[1].kwargs["headers"][
        "Idempotency-Key"
    ]
    assert first_key == second_key


def test_503_kill_switch_raises_service_unavailable_after_retries(
    mocked_http_client, client
):
    mocked_http_client.request.return_value = _mock_response(
        {"error": "temporarily_unavailable"}, status_code=503
    )

    with pytest.raises(ServiceUnavailableError):
        client.pause_monitor(MON_ID)

    assert mocked_http_client.request.call_count == 3


def test_verify_5xx_is_not_retried(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response(
        {"error": "internal"}, status_code=500
    )

    with pytest.raises(ServerError):
        client.verify_webhook_endpoint(WEP_ID)

    assert mocked_http_client.request.call_count == 1


def test_verify_kill_switch_503_is_still_retried(mocked_http_client, client):
    unavailable = _mock_response(
        {"error": "temporarily_unavailable"}, status_code=503
    )
    success = _mock_response({"verified": True, "endpoint": {}})
    mocked_http_client.request.side_effect = [unavailable, success]

    result = client.verify_webhook_endpoint(WEP_ID)

    assert result["verified"] is True
    assert mocked_http_client.request.call_count == 2


def test_verify_422_challenge_failure_returns_payload(mocked_http_client, client):
    payload = {"verified": False, "endpoint": {"id": WEP_ID}, "meta": {}}
    mocked_http_client.request.return_value = _mock_response(
        payload, status_code=422
    )

    result = client.verify_webhook_endpoint(WEP_ID)

    assert result == payload
    assert mocked_http_client.request.call_count == 1


def test_generic_422_still_raises(mocked_http_client, client):
    from handelsregister import RequestValidationError

    mocked_http_client.request.return_value = _mock_response(
        {"message": "The given data was invalid."}, status_code=422
    )

    with pytest.raises(RequestValidationError):
        client.create_monitor(
            entity_id="abc",
            poll_interval_days=7,
            endpoint_ids=[WEP_ID],
        )


def test_db_mutation_5xx_is_retried_with_same_key(mocked_http_client, client):
    error = _mock_response({"error": "server"}, status_code=502)
    success = _mock_response({"ok": True})
    mocked_http_client.request.side_effect = [error, success]

    result = client.archive_monitor(MON_ID)

    assert result == {"ok": True}
    keys = {
        call.kwargs["headers"]["Idempotency-Key"]
        for call in mocked_http_client.request.call_args_list
    }
    assert len(keys) == 1


def test_replayed_idempotency_status_is_captured(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response(
        {"ok": True}, headers={"idempotency-status": "replayed"}
    )

    client.pause_monitor(MON_ID)

    assert client.last_idempotency_status == "replayed"


def test_mutation_keeps_authentication_headers(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response({})

    client.pause_monitor(MON_ID)

    headers = _last_mutation(mocked_http_client)[2]["headers"]
    assert headers["x-api-key"] == "api-key"


def test_json_requests_send_accept_header(mocked_http_client, client):
    mocked_http_client.get.return_value = _mock_response({"meta": {}})
    client.list_monitors()
    headers = mocked_http_client.get.call_args.kwargs["headers"]
    assert headers["Accept"] == "application/json"


def test_mutations_send_accept_header(mocked_http_client, client):
    mocked_http_client.request.return_value = _mock_response({})
    client.pause_monitor(MON_ID)
    headers = _last_mutation(mocked_http_client)[2]["headers"]
    assert headers["Accept"] == "application/json"


def test_binary_requests_do_not_force_accept_header(mocked_http_client, client):
    response = _mock_response(content=b"%PDF-1.4")
    mocked_http_client.get.return_value = response
    client._request("fetch-document", params={}, expect_json=False)
    headers = mocked_http_client.get.call_args.kwargs["headers"]
    assert "Accept" not in headers


def test_unexpected_redirect_has_clear_message(mocked_http_client, client):
    from handelsregister import APIError

    redirect = _mock_response(
        payload=None, status_code=302, headers={"location": "https://x/login"}
    )
    redirect.json.side_effect = ValueError("no json")
    mocked_http_client.request.return_value = redirect

    with pytest.raises(APIError, match="redirect"):
        client.pause_monitor(MON_ID)


def test_base_url_env_fallback(monkeypatch):
    monkeypatch.setenv("HANDELSREGISTER_BASE_URL", "https://dev.example.com/api/v1/")
    assert (
        Handelsregister(api_key="k").base_url == "https://dev.example.com/api/v1"
    )
    # An explicit base_url always wins over the environment.
    assert (
        Handelsregister(api_key="k", base_url="https://x.example/v1/").base_url
        == "https://x.example/v1"
    )


def test_extra_headers_env_fallback(monkeypatch):
    monkeypatch.setenv(
        "HANDELSREGISTER_EXTRA_HEADERS",
        '{"X-Gateway-Client-Id": "cid", "X-Gateway-Client-Secret": "sec"}',
    )
    client = Handelsregister(api_key="k")
    assert client.headers["X-Gateway-Client-Id"] == "cid"
    # Explicit extra_headers win over the environment.
    client = Handelsregister(api_key="k", extra_headers={"X-Other": "v"})
    assert "X-Gateway-Client-Id" not in client.headers


@pytest.mark.parametrize("value", ["not json", "[1,2]", '"string"'])
def test_extra_headers_env_must_be_json_object(monkeypatch, value):
    monkeypatch.setenv("HANDELSREGISTER_EXTRA_HEADERS", value)
    with pytest.raises(ValueError, match="HANDELSREGISTER_EXTRA_HEADERS"):
        Handelsregister(api_key="k")
