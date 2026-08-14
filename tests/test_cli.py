import sys
import json

import pytest

from handelsregister.cli import main as cli_main, DEFAULT_FEATURES
from handelsregister.client import Handelsregister
from handelsregister.exceptions import SubscriptionRequiredError


def test_fetch_json(capsys, sample_organization_response, monkeypatch):
    def fake_fetch(self, q, features=None, ai_search=None, realtime_mode=None):
        return sample_organization_response

    monkeypatch.setattr(Handelsregister, "fetch_organization", fake_fetch)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["prog", "fetch", "json", "KONUX GmbH"])
    cli_main()
    out = capsys.readouterr().out
    assert json.loads(out) == sample_organization_response


def test_fetch_text(capsys, sample_organization_response, monkeypatch):
    def fake_fetch(self, q, features=None, ai_search=None, realtime_mode=None):
        return sample_organization_response

    monkeypatch.setattr(Handelsregister, "fetch_organization", fake_fetch)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["prog", "fetch", "KONUX GmbH"])
    cli_main()
    out = capsys.readouterr().out.strip()
    assert "KONUX GmbH" in out
    assert "Status: ACTIVE" in out


def test_fetch_defaults(monkeypatch, sample_organization_response):
    called = {}

    def fake_fetch(self, q, features=None, ai_search=None, realtime_mode=None):
        called['features'] = features
        called['ai_search'] = ai_search
        return sample_organization_response

    monkeypatch.setattr(Handelsregister, "fetch_organization", fake_fetch)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["prog", "fetch", "ACME GmbH"])
    cli_main()

    assert called['features'] == DEFAULT_FEATURES
    assert called['ai_search'] == "on-default"


def test_search_help_documents_30_result_maximum(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "search", "--help"])

    try:
        cli_main()
    except SystemExit as exc:
        assert exc.code == 0

    assert "maximum: 30" in capsys.readouterr().out


def test_search_cli_forwards_sort_order_and_match_context(capsys, monkeypatch):
    called = {}

    def fake_search(self, **kwargs):
        called.update(kwargs)
        return {"results": [], "total": 0, "meta": {}}

    monkeypatch.setattr(Handelsregister, "search_organizations", fake_search)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "search",
            "BMW",
            "--sort",
            "revenue",
            "--order",
            "desc",
            "--match-context",
            "--json",
        ],
    )

    cli_main()

    assert json.loads(capsys.readouterr().out)["total"] == 0
    assert called["sort"] == "revenue"
    assert called["order"] == "desc"
    assert called["match_context"] is True


def test_cli_prints_actionable_plan_error_without_traceback(capsys, monkeypatch):
    def fake_search(self, **kwargs):
        raise SubscriptionRequiredError(
            "These filters require an active Pro or Max subscription.",
            status_code=403,
            payload={
                "error": "subscription_required",
                "meta": {
                    "required_plans": ["pro", "max"],
                    "blocked_filters": ["ownership_filters"],
                    "request_credit_cost": 0,
                },
            },
        )

    monkeypatch.setattr(Handelsregister, "search_organizations", fake_search)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "search",
            "--filters",
            '{"ownership_filters":{"owner_managed":true}}',
        ],
    )

    with pytest.raises(SystemExit) as caught:
        cli_main()

    captured = capsys.readouterr()
    assert caught.value.code == 1
    assert captured.out == ""
    assert "Plan required:" in captured.err
    assert "Pro, Max" in captured.err
    assert "ownership_filters" in captured.err
    assert "subscription_required" not in captured.err
    assert "Traceback" not in captured.err


def test_monitors_list_json(capsys, monkeypatch):
    payload = {"monitors": [{"id": "mon_" + "a" * 26, "status": "active"}], "meta": {}}

    monkeypatch.setattr(Handelsregister, "list_monitors", lambda self: payload)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["prog", "monitors", "list", "--json"])
    cli_main()
    assert json.loads(capsys.readouterr().out) == payload


def test_monitors_create_passes_arguments(capsys, monkeypatch):
    called = {}

    def fake_create(
        self,
        entity_id,
        poll_interval_days,
        endpoint_ids,
        label=None,
        idempotency_key=None,
    ):
        called.update(
            entity_id=entity_id,
            poll_interval_days=poll_interval_days,
            endpoint_ids=endpoint_ids,
            label=label,
            idempotency_key=idempotency_key,
        )
        return {"monitor": {"id": "mon_" + "a" * 26}}

    monkeypatch.setattr(Handelsregister, "create_monitor", fake_create)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    wep = "wep_" + "b" * 26
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog", "monitors", "create",
            "--entity-id", "abc123",
            "--interval", "7",
            "--endpoint", wep,
            "--label", "BMW AG",
            "--idempotency-key", "cli-create-1",
        ],
    )
    cli_main()
    assert called == {
        "entity_id": "abc123",
        "poll_interval_days": 7,
        "endpoint_ids": [wep],
        "label": "BMW AG",
        "idempotency_key": "cli-create-1",
    }
    assert json.loads(capsys.readouterr().out)["monitor"]["id"].startswith("mon_")


def test_webhooks_create_parses_headers(capsys, monkeypatch):
    called = {}

    def fake_create(self, name, url, headers=None, idempotency_key=None):
        called.update(name=name, url=url, headers=headers)
        return {"endpoint": {"id": "wep_" + "b" * 26}, "signing_secret": "whsec_x"}

    monkeypatch.setattr(Handelsregister, "create_webhook_endpoint", fake_create)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog", "webhooks", "create",
            "--name", "Receiver",
            "--url", "https://hooks.example.com/x",
            "--header", "x-tenant=customer-42",
        ],
    )
    cli_main()
    assert called == {
        "name": "Receiver",
        "url": "https://hooks.example.com/x",
        "headers": {"x-tenant": "customer-42"},
    }
    assert "whsec_x" in capsys.readouterr().out


def test_webhooks_deliveries_filter(capsys, monkeypatch):
    called = {}

    def fake_list(self, endpoint_id=None):
        called["endpoint_id"] = endpoint_id
        return {"deliveries": [], "total": 0}

    monkeypatch.setattr(Handelsregister, "list_webhook_deliveries", fake_list)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    wep = "wep_" + "b" * 26
    monkeypatch.setattr(
        sys, "argv", ["prog", "webhooks", "deliveries", "--endpoint", wep]
    )
    cli_main()
    assert called["endpoint_id"] == wep
