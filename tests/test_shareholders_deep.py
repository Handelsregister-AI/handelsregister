"""Contract tests based on the documented deep-shareholder response."""

import copy
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from handelsregister import (
    CapitalInfo,
    Company,
    Handelsregister,
    ORGANIZATION_FEATURES,
    OrganizationFeature,
    ShareholdersDeep,
)
from handelsregister import cli


@pytest.fixture
def deep_response():
    return json.loads(
        (Path(__file__).parent / "data" / "shareholders_deep.json").read_text()
    )


def company_from(data, features=None):
    client = MagicMock(spec=Handelsregister)
    client.fetch_organization.return_value = data
    return Company("company-id", client=client, features=features), client


def test_documented_deep_shareholders_end_to_end(deep_response, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=deep_response)

    real_http_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_http_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    client = Handelsregister(api_key="test")
    company = Company(
        deep_response["entity_id"],
        client=client,
        features=[OrganizationFeature.SHAREHOLDERS_DEEP],
    )
    assert "shareholders_deep" in ORGANIZATION_FEATURES
    assert len(requests) == 1  # No account preflight: the API ignores non-Max requests.
    assert requests[0].url.params["q"] == deep_response["entity_id"]
    assert requests[0].url.params.get_list("feature") == ["shareholders_deep"]
    deep = company.shareholders_deep
    assert isinstance(deep, ShareholdersDeep)
    assert deep
    assert deep.record.date == "2025-03-15"
    assert deep.record.source == "SHAREHOLDER_LIST"
    assert deep.share_capital.value == 50000
    assert deep.share_capital.currency == "EUR"
    assert deep.share_capital.basis == "REPORTED"
    organization, person = deep.entries
    assert organization.holder.name == "Beispielwerk Holding GmbH"
    assert organization.holder.type == "ORGANIZATION"
    assert organization.holder.legal_form == "GmbH"
    assert organization.holder.registration["register_number"] == "12345"
    assert organization.holder.registration_text is None
    assert organization.holder.city == "München"
    assert organization.holder.country == "DEU"
    assert organization.holder.status == "ACTIVE"
    assert organization.role == "SHAREHOLDER"
    assert organization.percentage == 75  # Percent, not 0–1 ratio.
    assert organization.ownership.percentage_basis == "REPORTED"
    assert organization.ownership.nominal_amount.value == 37500
    assert organization.ownership.share_count == 2
    assert organization.ownership.share_ranges[0].from_number == 2
    assert organization.ownership.share_ranges[0].to_number == 2
    assert organization.ownership.share_ranges[0].count == 1
    assert organization.ownership.share_ranges[0].nominal_value.value == 12500
    assert organization.since_basis == "ENTRY_RECORDED"
    assert person.holder.birth_date == "1985-07-14"
    assert person.since == "2019-06-03"
    assert person.since_basis == "EARLIEST_RECORD"
    history = deep.history[0]
    assert history.record.date == "2019-06-03"
    assert history.share_capital.value == 25000
    assert history.entries[0].percentage == 100
    assert deep.changes.compared_to == "2019-06-03"
    assert deep.changes.joined[0].percentage == 75
    assert deep.changes.joined[0].holder.entity_id == organization.holder.entity_id
    assert deep.changes.left == []
    assert deep.changes.changed[0].percentage_before == 100
    assert deep.changes.changed[0].percentage_after == 25
    assert deep.as_dict() == deep_response["shareholders_deep"]
    assert history.as_dict() == deep.raw["history"][0]
    assert organization.as_dict() == deep.raw["entries"][0]
    # Identical calls are cached; the regular feature remains independent.
    assert (
        client.fetch_organization(
            q=company.entity_id, features=["shareholders_deep", "shareholders_deep"]
        )
        == deep_response
    )
    assert len(requests) == 1
    client.fetch_organization(q=company.entity_id, features=["shareholders"])
    assert len(requests) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"shareholders_deep": None},
        {"shareholders_deep": {"entries": [], "changes": None}},
    ],
)
def test_omitted_null_and_empty_deep_results(payload):
    company, _ = company_from(payload)
    assert not company.shareholders_deep
    assert company.shareholders_deep.entries == []
    assert company.shareholders_deep.changes is None
    assert company.data == payload


def test_joint_holders_duplicates_unknown_values_and_register_history(deep_response):
    payload = copy.deepcopy(deep_response["shareholders_deep"])
    joint = {
        "holder": {
            "entity_id": None,
            "type": "JOINT",
            "name": None,
            "members": [
                {"type": "PERSON", "name": "Co-owner", "birth_date": None},
                {
                    "type": "ORGANIZATION",
                    "name": None,
                    "registration": {"court": None, "register_number": "A-123"},
                    "registration_text": "Foreign register A-123",
                },
            ],
        },
        "role": "FUTURE_ROLE",
        "since": None,
        "since_basis": None,
        "ownership": {
            "percentage": 0,
            "percentage_basis": "FUTURE_BASIS",
            "share_count": 0,
            "nominal_amount": {"value": 0, "currency": None},
            "share_ranges": [
                {"from": None, "to": None, "count": None, "nominal_value": None}
            ],
        },
        "future_field": {"kept": True},
    }
    payload["entries"] = [joint, joint]
    payload["history"].append(
        {
            "record": {"date": None, "source": "COMMERCIAL_REGISTER"},
            "share_capital": None,
            "entries": [
                {
                    "holder": {"type": "PERSON"},
                    "until": "2020-01-01",
                    "role": "LIMITED_PARTNER",
                }
            ],
        }
    )
    payload["changes"]["left"] = [
        {"holder": {"name": "Former holder"}, "percentage": None}
    ]
    before = copy.deepcopy(payload)
    deep = ShareholdersDeep.from_payload(payload)
    assert len(deep.entries) == 2  # Preserve document rows, never deduplicate.
    entry = deep.entries[0]
    assert entry.holder.entity_id is None
    assert entry.holder.name is None
    assert entry.holder.members[0].name == "Co-owner"
    assert entry.holder.members[1].registration_text == "Foreign register A-123"
    assert not hasattr(entry.holder.members[0], "percentage")
    assert entry.percentage == 0
    assert entry.ownership.nominal_amount.value == 0
    assert entry.ownership.nominal_amount.currency is None
    assert entry.ownership.share_count == 0
    assert entry.ownership.share_ranges[0].from_number is None
    assert entry.ownership.share_ranges[0].nominal_value is None
    assert entry.role == "FUTURE_ROLE"
    assert entry.ownership.percentage_basis == "FUTURE_BASIS"
    assert entry.as_dict()["future_field"] == {"kept": True}
    assert deep.history[-1].record.date is None
    assert deep.history[-1].share_capital is None
    assert deep.history[-1].entries[0].until == "2020-01-01"
    assert deep.changes.left[0].percentage is None
    assert deep.as_dict() == before == payload


def test_regular_shareholder_ratios_and_deep_percentages_coexist(deep_response):
    deep_response["shareholders"] = {
        "entries": [
            {
                "shareholder": {
                    "name": "Owner",
                    "entity_id": "owner-id",
                    "birth_date": "1985-07-14",
                },
                "contribution": {},
                "contribution_ratio": 0.75,
                "role": {"label": "SHAREHOLDER", "en": {"long": "Shareholder"}},
            }
        ]
    }
    company, client = company_from(
        deep_response, features=["shareholders", "shareholders_deep"]
    )
    assert client.fetch_organization.call_args.kwargs["features"] == [
        "shareholders",
        "shareholders_deep",
    ]
    assert company.shareholders.entries[0].percentage == 0.75
    assert company.shareholders.entries[0].role_name == "Shareholder"
    assert company.shareholders.entries[0].role["label"] == "SHAREHOLDER"
    assert company.shareholders.entries[0].entity_id == "owner-id"
    assert company.shareholders.entries[0].birth_date == "1985-07-14"
    assert company.shareholders_deep.entries[0].percentage == 75


def test_optional_fields_unknown_metadata_and_malformed_collections():
    deep = ShareholdersDeep.from_payload(
        {
            "record": {"source": "FUTURE_SOURCE", "date": None, "future": True},
            "share_capital": {"value": 0, "currency": None, "basis": "FUTURE_BASIS"},
            "entries": [None, "not an entry", {"holder": None, "ownership": None}],
            "history": None,
            "changes": {"compared_to": None, "joined": None, "left": [], "changed": []},
        }
    )
    assert deep.record.source == "FUTURE_SOURCE"
    assert deep.record.as_dict()["future"] is True
    assert deep.share_capital.value == 0
    assert deep.share_capital.basis == "FUTURE_BASIS"
    assert len(deep.entries) == 1
    assert deep.entries[0].percentage is None
    assert deep.history == []
    assert deep.changes.joined == []


def test_capital_history_keeps_unsigned_reported_change_and_raw_interface():
    payload = {
        "current": {"amount": 20000, "currency": "EUR", "kind": "FUTURE_KIND"},
        "history": [
            {
                "value": {
                    "amount": 20000,
                    "currency": "EUR",
                    "kind": "STAMMKAPITAL",
                    "change_amount": {"amount": 5000, "currency": "EUR"},
                },
                "effective_from": "2026-01-01",
                "effective_to": None,
            }
        ],
    }
    company, _ = company_from({"capital": payload})
    assert company.capital is payload
    capital = company.capital_info
    assert isinstance(capital, CapitalInfo)
    assert capital.current.amount == 20000
    assert capital.current.kind == "FUTURE_KIND"
    assert capital.history[0].effective_to is None
    assert capital.history[0].value.change_amount == {"amount": 5000, "currency": "EUR"}
    assert capital.as_dict() is payload
    assert not CapitalInfo.from_payload({"current": None, "history": []})
    assert not CapitalInfo.from_payload(None)
    legacy, _ = company_from({"capital": "25.000 EUR"})
    assert legacy.capital == "25.000 EUR"
    assert not legacy.capital_info


@pytest.mark.parametrize(
    "feature,typed_property,accounts_key",
    [
        ("financial_kpi", "financial_kpi_entries", None),
        ("balance_sheet_accounts", "balance_sheet_entries", "balance_sheet_accounts"),
        (
            "profit_and_loss_account",
            "profit_and_loss_entries",
            "profit_and_loss_accounts",
        ),
    ],
)
def test_financial_sources_activities_metrics_and_enrichment(
    feature, typed_property, accounts_key
):
    provenance = {
        "statement_type": "Jahresabschluss",
        "period_start": "2023-01-01",
        "period_end": "2023-12-31",
        "exempt_subsidiary": False,
        "parent_organization": None,
        "future_source_field": "retained",
    }
    row = {"year": 2023, "_provenance": provenance}
    if accounts_key:
        row[accounts_key] = [{"name": {"en": "Assets"}, "value": 100, "children": []}]
        row["activity_statements"] = [
            {
                "activity": {
                    "name": {
                        "en": "Electricity distribution",
                        "de": "Elektrizitätsverteilung",
                    }
                },
                accounts_key: [{"name": "Activity accounts", "value": 40}],
                "_provenance": {**provenance, "statement_type": "Tätigkeitsabschluss"},
            }
        ]
    else:
        row.update({"revenue": 100, "future_metric": 0, "equity_ratio": 0.25})
    payload = {feature: [row]}
    company, _ = company_from(payload)
    typed = getattr(company, typed_property)[0]
    assert typed.year == 2023
    assert typed.provenance.statement_type == "Jahresabschluss"
    assert typed.provenance.exempt_subsidiary is False
    assert typed.provenance.parent_organization is None
    assert typed.provenance.as_dict()["future_source_field"] == "retained"
    assert typed.as_dict() is row
    assert getattr(company, feature)[0] is row
    if accounts_key:
        activity = typed.activity_statements[0]
        assert activity.name_text() == "Electricity distribution"
        assert activity.name_text("de") == "Elektrizitätsverteilung"
        assert getattr(activity, accounts_key)[0]["value"] == 40
        assert activity.provenance.statement_type == "Tätigkeitsabschluss"
    else:
        assert typed.metrics == {
            "revenue": 100,
            "future_metric": 0,
            "equity_ratio": 0.25,
        }
    flat = Handelsregister(api_key="test")._flatten_result(payload)
    assert json.loads(flat[feature + "_provenance"]) == [
        {"year": 2023, "_provenance": provenance}
    ]
    assert "_provenance" not in flat[feature]
    if accounts_key:
        assert json.loads(flat[feature + "_activity_statements"]) == [
            {"year": 2023, "activity_statements": row["activity_statements"]}
        ]
    assert payload[feature][0] == row


def test_deep_shareholders_and_capital_survive_enrichment(deep_response):
    deep_response["capital"] = {"current": None, "history": []}
    flat = Handelsregister(api_key="test")._flatten_result(deep_response)
    assert json.loads(flat["shareholders_deep"]) == deep_response["shareholders_deep"]
    assert json.loads(flat["capital"]) == deep_response["capital"]


@pytest.mark.parametrize("output_type", ["json", "csv", "xlsx"])
def test_enrichment_files_retain_deep_data_and_financial_metadata(
    deep_response, tmp_path, monkeypatch, output_type
):
    import pandas as pd

    deep_response["balance_sheet_accounts"] = [
        {
            "year": 2023,
            "balance_sheet_accounts": [],
            "_provenance": {"statement_type": "Jahresabschluss"},
            "activity_statements": [
                {
                    "activity": {"name": {"en": "Electricity distribution"}},
                    "balance_sheet_accounts": [],
                    "_provenance": {"statement_type": "Tätigkeitsabschluss"},
                }
            ],
        }
    ]
    deep_response["capital"] = {
        "current": {"amount": 50000, "currency": "EUR", "kind": "STAMMKAPITAL"},
        "history": [],
    }
    requests = []
    client = Handelsregister(api_key="test")

    def fetch(**kwargs):
        requests.append(kwargs)
        return deep_response

    monkeypatch.setattr(client, "fetch_organization", fetch)
    source = tmp_path / "companies.json"
    source.write_text(json.dumps([{"entity_id": deep_response["entity_id"]}]))
    output = tmp_path / ("enriched." + output_type)
    client.enrich(
        file_path=str(source),
        input_type="json",
        output_file=str(output),
        output_type=output_type,
        query_properties={"id": "entity_id"},
        params={"features": [OrganizationFeature.SHAREHOLDERS_DEEP]},
    )
    assert requests[0]["features"] == [OrganizationFeature.SHAREHOLDERS_DEEP]
    if output_type == "json":
        assert (
            json.loads(output.read_text())[0]["_handelsregister_result"]
            == deep_response
        )
    else:
        frame = pd.read_csv(output) if output_type == "csv" else pd.read_excel(output)
        assert (
            json.loads(frame.iloc[0]["hr_shareholders_deep"])
            == deep_response["shareholders_deep"]
        )
        assert json.loads(frame.iloc[0]["hr_capital"]) == deep_response["capital"]
        assert json.loads(frame.iloc[0]["hr_balance_sheet_accounts_provenance"])[0][
            "_provenance"
        ] == {"statement_type": "Jahresabschluss"}
        assert (
            json.loads(frame.iloc[0]["hr_balance_sheet_accounts_activity_statements"])[
                0
            ]["activity_statements"]
            == deep_response["balance_sheet_accounts"][0]["activity_statements"]
        )


@pytest.mark.parametrize("rich", [True, False])
def test_cli_deep_shareholder_feature_and_text(
    deep_response, monkeypatch, capsys, rich
):
    calls = []

    def fetch(self, **kwargs):
        calls.append(kwargs)
        return deep_response

    monkeypatch.setattr(Handelsregister, "fetch_organization", fetch)
    monkeypatch.setattr(cli, "RICH_AVAILABLE", rich)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "test")
    monkeypatch.setenv("COLUMNS", "220")
    monkeypatch.setattr(
        sys, "argv", ["prog", "fetch", "company-id", "--feature", "shareholders_deep"]
    )
    cli.main()
    output = capsys.readouterr().out
    assert calls[0]["features"] == ["shareholders_deep"]
    assert "Deep Shareholders" in output
    assert "75%" in output
    assert "Max Mustermann" in output
    assert "EARLIEST_RECORD" in output


def test_cli_json_retains_complete_deep_response(deep_response, monkeypatch, capsys):
    monkeypatch.setattr(
        Handelsregister, "fetch_organization", lambda self, **kwargs: deep_response
    )
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "test")
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "fetch", "json", "company-id", "--feature", "shareholders_deep"],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out) == deep_response


def test_cli_financial_metadata_is_displayed_as_sources_and_activities(
    monkeypatch, capsys
):
    payload = {
        "name": "Energy company",
        "capital": {
            "current": {"amount": 50000, "currency": "EUR", "kind": "STAMMKAPITAL"}
        },
        "financial_kpi": [
            {
                "year": 2023,
                "revenue": 100,
                "equity_ratio": 0.25,
                "cash_to_assets": 0.05,
                "interest_coverage": 2.5,
                "_provenance": {"statement_type": "Jahresabschluss"},
            }
        ],
        "balance_sheet_accounts": [
            {
                "year": 2023,
                "balance_sheet_accounts": [],
                "activity_statements": [
                    {
                        "activity": {"name": {"en": "Electricity distribution"}},
                        "balance_sheet_accounts": [],
                    }
                ],
            }
        ],
    }
    monkeypatch.setenv("COLUMNS", "150")
    cli._display_result(Handelsregister(api_key="test"), payload)
    output = capsys.readouterr().out
    assert "STAMMKAPITAL" in output
    assert "Jahresabschluss" in output
    assert "Electricity distribution" in output
    assert "{'statement_type'" not in output
    assert "0.25 €" not in output
    assert "0.05 €" not in output
    assert "2.50 €" not in output
    assert "100.00 €" in output
