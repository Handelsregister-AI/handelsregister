from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from handelsregister import (
    AuthenticationError,
    Handelsregister,
    InvalidResponseError,
    SIGNAL_TOPICS,
    SignalTopic,
    SubscriptionRequiredError,
)


def _mock_response(payload):
    response = MagicMock()
    response.status_code = 200
    response.content = b'{"ok": true}'
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mocked_http_client():
    with patch("httpx.Client") as httpx_client:
        session = MagicMock()
        httpx_client.return_value.__enter__.return_value = session
        yield session


def test_extra_headers_are_added_without_changing_authentication():
    client = Handelsregister(
        api_key="api-key",
        extra_headers={
            "X-Custom-Gateway": "gateway-value",
            "X-Request-Context": "test",
        },
    )
    assert client.headers["x-api-key"] == "api-key"
    assert client.headers["X-Custom-Gateway"] == "gateway-value"
    assert client.extra_headers == {
        "X-Custom-Gateway": "gateway-value",
        "X-Request-Context": "test",
    }


@pytest.mark.parametrize("header", ["Authorization", "x-api-key", "User-Agent"])
def test_extra_headers_cannot_override_sdk_managed_headers(header):
    with pytest.raises(ValueError, match="managed by the SDK"):
        Handelsregister(
            api_key="api-key",
            extra_headers={header: "override"},
        )


@pytest.mark.parametrize(
    "extra_headers",
    [
        [("X-Test", "value")],
        {123: "value"},
        {"": "value"},
        {"Invalid:Header": "value"},
        {"X-Test": ""},
        {"X-Test": "value\r\nInjected: true"},
        {"X-Test": 123},
    ],
)
def test_extra_headers_are_validated(extra_headers):
    with pytest.raises(ValueError, match="extra_headers|header"):
        Handelsregister(api_key="api-key", extra_headers=extra_headers)


@pytest.mark.parametrize(
    ("method_name", "expected_path"),
    [
        ("get_account", "/account"),
        ("get_account_credits", "/account/credits"),
        ("get_account_subscription", "/account/subscription"),
        ("list_api_keys", "/account/api-keys"),
    ],
)
def test_account_read_endpoints(mocked_http_client, method_name, expected_path):
    mocked_http_client.get.return_value = _mock_response({"meta": {}})
    client = Handelsregister(api_key="api-key")

    result = getattr(client, method_name)()

    assert result == {"meta": {}}
    request = mocked_http_client.get.call_args
    assert request.args[0].endswith(expected_path)
    assert request.kwargs["params"] == {}


def test_account_usage_serializes_dates_and_grouping(mocked_http_client):
    mocked_http_client.get.return_value = _mock_response({"totals": {}})
    client = Handelsregister(api_key="api-key")

    client.get_account_usage(
        from_date=date(2026, 7, 1),
        to_date=datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
        group_by="MONTH",
    )

    params = mocked_http_client.get.call_args.kwargs["params"]
    assert params == {
        "from": "2026-07-01",
        "to": "2026-07-30T12:00:00+00:00",
        "group_by": "month",
    }


@pytest.mark.parametrize("group_by", ["week", "", "daily"])
def test_account_usage_rejects_invalid_grouping(group_by):
    client = Handelsregister(api_key="api-key")
    with pytest.raises(ValueError, match="group_by"):
        client.get_account_usage(group_by=group_by)


def test_account_transactions_parameters(mocked_http_client):
    mocked_http_client.get.return_value = _mock_response(
        {"transactions": [], "pagination": {"has_more": False}}
    )
    client = Handelsregister(api_key="api-key")

    client.get_account_usage_transactions(
        from_date="2026-07-01",
        to_date="2026-07-30",
        endpoint="/api/v1/signals",
        per_page=100,
        cursor="opaque",
    )

    params = mocked_http_client.get.call_args.kwargs["params"]
    assert params == {
        "from": "2026-07-01",
        "to": "2026-07-30",
        "endpoint": "/api/v1/signals",
        "per_page": 100,
        "cursor": "opaque",
    }


@pytest.mark.parametrize("per_page", [0, 101, True, 1.5])
def test_account_transactions_validates_page_size(per_page):
    client = Handelsregister(api_key="api-key")
    with pytest.raises(ValueError, match="per_page"):
        client.get_account_usage_transactions(per_page=per_page)


def test_account_transactions_iterator_preserves_filters():
    client = Handelsregister(api_key="api-key")
    client.get_account_usage_transactions = MagicMock(
        side_effect=[
            {
                "transactions": [{"id": "tx-1"}],
                "pagination": {
                    "next_cursor": "cursor-2",
                    "per_page": 1,
                },
            },
            {
                "transactions": [{"id": "tx-2"}],
                "pagination": {
                    "next_cursor": None,
                    "per_page": 1,
                },
            },
        ]
    )

    transactions = list(
        client.iter_account_usage_transactions(
            endpoint="/api/v1/signals",
            per_page=1,
        )
    )

    assert transactions == [{"id": "tx-1"}, {"id": "tx-2"}]
    assert client.get_account_usage_transactions.call_count == 2
    second_call = client.get_account_usage_transactions.call_args_list[1]
    assert second_call.kwargs["cursor"] == "cursor-2"
    assert second_call.kwargs["endpoint"] == "/api/v1/signals"


def test_api_key_management_requires_bearer_token():
    client = Handelsregister(api_key="api-key")
    with pytest.raises(AuthenticationError, match="account:keys"):
        client.create_api_key()
    with pytest.raises(AuthenticationError, match="account:keys"):
        client.revoke_api_key(123)


def test_api_key_create_and_revoke_routes(mocked_http_client):
    mocked_http_client.post.return_value = _mock_response(
        {"api_key": {"id": 124, "key": "secret"}}
    )
    mocked_http_client.delete.return_value = _mock_response({"meta": {}})
    client = Handelsregister(bearer_token="admin-token")

    created = client.create_api_key()
    revoked = client.revoke_api_key("key/id")

    assert created["api_key"]["id"] == 124
    assert revoked == {"meta": {}}
    assert mocked_http_client.post.call_args.args[0].endswith("/account/api-keys")
    assert mocked_http_client.post.call_args.kwargs["json"] == {}
    assert mocked_http_client.delete.call_args.args[0].endswith(
        "/account/api-keys/key%2Fid"
    )


def test_signal_topics_match_documented_catalog():
    assert tuple(topic.value for topic in SignalTopic) == SIGNAL_TOPICS
    assert SIGNAL_TOPICS == (
        "NEW_REGISTRATIONS",
        "MASTER_DATA_CHANGES",
        "CLOSURES",
        "ROLE_HOLDER_CHANGES",
        "CAPITAL_CHANGES",
        "INSOLVENCIES",
        "TRANSFORMATIONS",
    )


def test_list_signals_serializes_filters(mocked_http_client):
    mocked_http_client.get.return_value = _mock_response(
        {"signals": [], "pagination": {"has_more": False}}
    )
    client = Handelsregister(api_key="api-key")

    client.list_signals(
        cursor="opaque",
        topics=[SignalTopic.CAPITAL_CHANGES, "TRANSFORMATIONS"],
        organization_ids=["org-1", "org-2", "org-1"],
        from_date=date(2026, 7, 1),
        to_date="2026-07-30",
    )

    params = mocked_http_client.get.call_args.kwargs["params"]
    assert params == {
        "cursor": "opaque",
        "topics": "CAPITAL_CHANGES,TRANSFORMATIONS",
        "organization_ids": "org-1,org-2",
        "from": "2026-07-01",
        "to": "2026-07-30",
    }


def test_list_signals_accepts_documented_comma_separated_topics(
    mocked_http_client,
):
    mocked_http_client.get.return_value = _mock_response(
        {"signals": [], "pagination": {"has_more": False}}
    )
    client = Handelsregister(api_key="api-key")

    client.list_signals(topics="CAPITAL_CHANGES,TRANSFORMATIONS")

    assert (
        mocked_http_client.get.call_args.kwargs["params"]["topics"]
        == "CAPITAL_CHANGES,TRANSFORMATIONS"
    )


def test_list_signals_rejects_unknown_topic_without_request(mocked_http_client):
    client = Handelsregister(api_key="api-key")
    with pytest.raises(ValueError, match="UNKNOWN"):
        client.list_signals(topics=["UNKNOWN"])
    mocked_http_client.get.assert_not_called()


def test_signal_catalog_and_detail_routes(mocked_http_client):
    mocked_http_client.get.side_effect = [
        _mock_response({"topics": []}),
        _mock_response(
            {
                "signal": {"event": {"id": "signal-1"}},
                "meta": {"request_credit_cost": 20},
            }
        ),
    ]
    client = Handelsregister(api_key="api-key")

    assert client.get_signal_catalog() == {"topics": []}
    assert client.get_signal("signal/id")["signal"]["event"]["id"] == "signal-1"

    calls = mocked_http_client.get.call_args_list
    assert calls[0].args[0].endswith("/signals/catalog")
    assert calls[1].args[0].endswith("/signals/signal%2Fid")


def test_iter_signals_is_lazy_and_preserves_filters():
    client = Handelsregister(api_key="api-key")
    client.list_signals = MagicMock(
        side_effect=[
            {
                "signals": [{"event": {"id": "one"}}],
                "pagination": {
                    "has_more": True,
                    "next_cursor": "cursor-2",
                },
            },
            {
                "signals": [{"event": {"id": "two"}}],
                "pagination": {
                    "has_more": False,
                    "next_cursor": None,
                },
            },
        ]
    )

    iterator = client.iter_signals(
        topics=[SignalTopic.CAPITAL_CHANGES],
        organization_ids=["org-1"],
        max_results=2,
    )
    assert client.list_signals.call_count == 0
    assert [signal["event"]["id"] for signal in iterator] == ["one", "two"]

    assert client.list_signals.call_count == 2
    second_call = client.list_signals.call_args_list[1]
    assert second_call.kwargs["cursor"] == "cursor-2"
    assert second_call.kwargs["topics"] == [SignalTopic.CAPITAL_CHANGES]
    assert second_call.kwargs["organization_ids"] == ["org-1"]


def test_iter_signals_rejects_malformed_and_repeated_cursor_responses():
    client = Handelsregister(api_key="api-key")
    client.list_signals = MagicMock(return_value={"signals": []})
    with pytest.raises(InvalidResponseError, match="pagination"):
        list(client.iter_signals())

    client.list_signals = MagicMock(
        side_effect=[
            {
                "signals": [],
                "pagination": {"has_more": True, "next_cursor": "same"},
            },
            {
                "signals": [],
                "pagination": {"has_more": True, "next_cursor": "same"},
            },
        ]
    )
    with pytest.raises(InvalidResponseError, match="repeated"):
        list(client.iter_signals())


def test_problem_json_plan_required_maps_to_subscription_error():
    client = Handelsregister(api_key="api-key")
    response = httpx.Response(
        403,
        json={
            "type": "https://handelsregister.ai/problems/plan-required",
            "title": "Plan required",
            "code": "PLAN_REQUIRED",
        },
    )

    with pytest.raises(SubscriptionRequiredError) as exc_info:
        client._raise_api_error(response)

    assert exc_info.value.status_code == 403
    assert exc_info.value.payload["code"] == "PLAN_REQUIRED"
