"""Document-level audit contracts, company access, CLI and export coverage."""

import copy
import json
import sys
from unittest.mock import MagicMock

import httpx
import pytest

from handelsregister import (
    AnnualFinancialStatement,
    AuditInfo,
    AuditorInfo,
    AuditorNetwork,
    AuditSignatory,
    AuditSignature,
    Company,
    Handelsregister,
    OrganizationFeature,
)
from handelsregister import cli


@pytest.fixture
def audit_response():
    # Synthetic reports matching the observed FIRM / INDIVIDUAL_AUDITORS
    # shapes, plus nullable and future fields. No report text or credentials.
    audit = {
        "kind": "AUDIT_REPORT",
        "subject": "OWN",
        "audited": True,
        "accounting_framework": "HGB",
        "auditor": {
            "name": "Example Audit GmbH",
            "type": "FIRM",
            "entity_id": None,
            "network": {"key": "EXAMPLE", "name": "Example Network", "future": 1},
            "signatories": [
                {
                    "name": "Müller",
                    "academic_title": "Dr.",
                    "qualification": "WP",
                    "future": 2,
                },
                {"name": "Schmidt", "academic_title": None, "qualification": "WP"},
            ],
            "future": 3,
        },
        "signed": {"place": "Köln", "date": "2025-05-26", "future": 4},
        "future": 5,
    }
    report = {
        "year": 2024,
        "document_type": "Jahresabschluss",
        "document_title": "Annual report 2024",
        "document_date": "2026-01-05",
        "language": "Deutsch",
        "document_md": "# Example report",
        "audit": audit,
        "future_report_field": "preserved",
    }
    consolidated = copy.deepcopy(report)
    consolidated.update(
        document_type="Konzernabschluss", document_title="Group report 2024"
    )
    consolidated["audit"]["accounting_framework"] = "IFRS"
    individual = copy.deepcopy(report)
    individual.update(year=2023, document_title="Annual report 2023")
    individual["audit"]["auditor"].update(
        name=None,
        type="INDIVIDUAL_AUDITORS",
        network=None,
    )
    absent = {
        **report,
        "year": 2022,
        "document_title": "Annual report 2022",
        "audit": None,
    }
    legacy = {k: v for k, v in report.items() if k != "audit"}
    legacy.update(year=2021, document_title="Legacy report 2021")
    reports = [report, consolidated, individual, absent, legacy]
    html = copy.deepcopy(reports)
    for row in html:
        row.pop("document_md")
        row["document_html"] = "<h1>Example report</h1>"
    return {
        "name": "Example company",
        "annual_financial_statements": reports,
        "annual_financial_statements__html": html,
    }


def company_from(data):
    client = MagicMock(spec=Handelsregister)
    client.fetch_organization.return_value = data
    return Company("example", client=client)


def test_typed_report_and_all_nested_models_are_lossless(audit_response):
    before = copy.deepcopy(audit_response)
    raw = audit_response["annual_financial_statements"][0]
    report = company_from(audit_response).annual_financial_statement_entries[0]
    assert isinstance(report, AnnualFinancialStatement)
    assert report.year == 2024
    assert report.document_type == "Jahresabschluss"
    assert report.document_title == "Annual report 2024"
    assert report.document_date == "2026-01-05"
    assert report.language == "Deutsch"
    assert report.document_md == "# Example report"
    assert report.document_html is None
    audit = report.audit
    assert isinstance(audit, AuditInfo)
    assert (audit.kind, audit.subject, audit.audited, audit.accounting_framework) == (
        "AUDIT_REPORT",
        "OWN",
        True,
        "HGB",
    )
    auditor = audit.auditor
    assert isinstance(auditor, AuditorInfo)
    assert auditor.name == "Example Audit GmbH"
    assert auditor.type == "FIRM"
    assert auditor.entity_id is None
    assert isinstance(auditor.network, AuditorNetwork)
    assert (auditor.network.key, auditor.network.name) == ("EXAMPLE", "Example Network")
    assert isinstance(auditor.signatories[0], AuditSignatory)
    assert [
        (s.name, s.academic_title, s.qualification) for s in auditor.signatories
    ] == [
        ("Müller", "Dr.", "WP"),
        ("Schmidt", None, "WP"),
    ]
    assert isinstance(audit.signed, AuditSignature)
    assert (audit.signed.place, audit.signed.date) == ("Köln", "2025-05-26")
    for model, payload in (
        (report, raw),
        (audit, raw["audit"]),
        (auditor, raw["audit"]["auditor"]),
        (auditor.network, raw["audit"]["auditor"]["network"]),
        (auditor.signatories[0], raw["audit"]["auditor"]["signatories"][0]),
        (audit.signed, raw["audit"]["signed"]),
    ):
        assert model.as_dict() is payload
    assert audit_response == before


def test_company_helpers_keep_formats_and_same_year_reports_separate(audit_response):
    company = company_from(audit_response)
    assert company.financial_years == [2024, 2023, 2022, 2021]
    for html in (False, True):
        feature = (
            "annual_financial_statements__html"
            if html
            else "annual_financial_statements"
        )
        entries = company.get_annual_financial_statement_entries_for_year(
            2024, html=html
        )
        assert [entry.document_type for entry in entries] == [
            "Jahresabschluss",
            "Konzernabschluss",
        ]
        assert [entry.audit.accounting_framework for entry in entries] == [
            "HGB",
            "IFRS",
        ]
        assert entries[0].as_dict() is audit_response[feature][0]
        assert (
            company.get_annual_financial_statement_entry_for_year(2024, html).raw
            is entries[0].raw
        )
        assert (
            company.get_annual_financial_statement_for_year(2024, html)
            is entries[0].raw
        )
        assert company.get_annual_financial_statement_entries_for_year(1900, html) == []
        assert company.get_annual_financial_statement_entry_for_year(1900, html) is None
        assert company.get_annual_financial_statement_for_year(1900, html) == {}
    html_report = company.annual_financial_statement_html_entries[0]
    assert html_report.document_md is None
    assert html_report.document_html == "<h1>Example report</h1>"
    assert (
        html_report.audit.as_dict()
        == company.annual_financial_statement_entries[0].audit.as_dict()
    )
    individual = company.get_annual_financial_statement_entry_for_year(
        2023
    ).audit.auditor
    assert individual.type == "INDIVIDUAL_AUDITORS"
    assert individual.name is None and individual.network is None
    assert len(individual.signatories) == 2
    for year in (2022, 2021):
        assert company.get_annual_financial_statement_entry_for_year(year).audit is None


@pytest.mark.parametrize("value", [None, [], "invalid", 0])
def test_missing_and_malformed_optional_payloads(value):
    company = company_from(
        {
            "annual_financial_statements": value,
            "annual_financial_statements__html": value,
        }
    )
    assert company.annual_financial_statement_entries == []
    assert company.annual_financial_statement_html_entries == []
    assert company.financial_years == []
    report = AnnualFinancialStatement.from_payload({"audit": value})
    assert report.audit is None
    audit = AuditInfo.from_payload({"auditor": value, "signed": value})
    assert audit.audited is None and audit.auditor is None and audit.signed is None
    auditor = AuditorInfo.from_payload({"network": value, "signatories": value})
    assert auditor.network is None and auditor.signatories == []


@pytest.mark.parametrize("audited", [True, False, None])
def test_future_values_and_audit_states_are_not_coerced(audited):
    payload = {
        "kind": "FUTURE_KIND",
        "subject": "FUTURE_SUBJECT",
        "audited": audited,
        "accounting_framework": "FUTURE_FRAMEWORK",
        "auditor": {
            "type": "FUTURE_TYPE",
            "entity_id": "auditor-id",
            "signatories": [None, {}],
        },
        "signed": {},
        "extra": {"retained": True},
    }
    audit = AuditInfo.from_payload(payload)
    assert audit.audited is audited
    assert audit.kind == "FUTURE_KIND" and audit.subject == "FUTURE_SUBJECT"
    assert audit.accounting_framework == "FUTURE_FRAMEWORK"
    assert (
        audit.auditor.type == "FUTURE_TYPE" and audit.auditor.entity_id == "auditor-id"
    )
    assert len(audit.auditor.signatories) == 1
    assert audit.signed.date is None
    assert audit.as_dict() == payload
    assert AnnualFinancialStatement.from_payload({"audit": {}}).audit.audited is None


def test_request_uses_existing_features_and_forwards_financial_selectors(
    audit_response, monkeypatch
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=audit_response)

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client = Handelsregister(api_key="test")
    company = Company(
        "example",
        client=client,
        features=[
            OrganizationFeature.ANNUAL_FINANCIAL_STATEMENTS,
            OrganizationFeature.ANNUAL_FINANCIAL_STATEMENTS_HTML,
        ],
        financial_years=5,
        financial_statement_type="annual",
    )
    assert company.annual_financial_statement_entries[0].audit.audited is True
    assert len(requests) == 1
    params = requests[0].url.params
    assert params.get_list("feature") == [
        "annual_financial_statements",
        "annual_financial_statements__html",
    ]
    assert params["financial_years"] == "5"
    assert params["financial_statement_type"] == "annual"


@pytest.mark.parametrize("rich", [False, True])
def test_cli_report_only_latest_year_and_deduplication(
    audit_response, monkeypatch, capsys, rich
):
    monkeypatch.setattr(cli, "RICH_AVAILABLE", rich)
    monkeypatch.setenv("COLUMNS", "160")
    cli._display_result(Handelsregister(api_key="test"), audit_response)
    output = capsys.readouterr().out
    assert output.count("Annual report audit 2024:") == 2
    for value in (
        "Example Audit GmbH",
        "Example Network",
        "EXAMPLE",
        "Dr. Müller (WP)",
        "Schmidt (WP)",
        "HGB",
        "IFRS",
        "2025-05-26",
        "2026-01-05",
        "Köln",
    ):
        assert value in output
    assert "2023" not in output
    assert "# Example report" not in output


@pytest.mark.parametrize("rich", [False, True])
@pytest.mark.parametrize("year", [2023, 2022, 2021])
def test_cli_individuals_and_absent_audits(
    audit_response, monkeypatch, capsys, rich, year
):
    monkeypatch.setattr(cli, "RICH_AVAILABLE", rich)
    monkeypatch.setenv("COLUMNS", "160")
    cli._display_result(
        Handelsregister(api_key="test"), audit_response, financial_year=year
    )
    output = capsys.readouterr().out
    assert output.count(f"Annual report audit {year}:") == 1
    assert "Example Audit GmbH" not in output
    assert "Example Network" not in output
    if year == 2023:
        assert "INDIVIDUAL_AUDITORS" in output
        assert "Dr. Müller (WP)" in output
    else:
        assert "Audit information" in output and "Not available" in output
        assert "Audited" not in output


def test_cli_keeps_distinct_documents_and_conflicting_format_metadata(audit_response):
    original = copy.deepcopy(audit_response)
    html = audit_response["annual_financial_statements__html"]
    html[0]["audit"]["subject"] = "OTHER"
    html.append(copy.deepcopy(html[1]))
    reports = cli._annual_reports_for_display(audit_response)
    assert len(reports) == 7  # five MD + changed audit + unmatched extra HTML copy
    assert reports[-2].audit.subject == "OTHER"
    assert reports[-1].document_type == "Konzernabschluss"
    html_only = {
        "annual_financial_statements__html": original[
            "annual_financial_statements__html"
        ]
    }
    assert len(cli._annual_reports_for_display(html_only)) == 5
    assert cli._financial_display(html_only, None)[0] == 2024
    assert cli._audit_display(reports, 1900) == []
    assert cli._annual_reports_for_display({}) == []
    assert (
        cli._annual_reports_for_display({"annual_financial_statements": [None, "bad"]})
        == []
    )


@pytest.mark.parametrize("rich", [False, True])
def test_cli_json_is_complete_and_year_selection_is_local(
    audit_response, monkeypatch, capsys, rich
):
    requests = []

    def fetch(self, **kwargs):
        requests.append(kwargs)
        return audit_response

    monkeypatch.setattr(Handelsregister, "fetch_organization", fetch)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "test")
    monkeypatch.setattr(cli, "RICH_AVAILABLE", rich)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "fetch",
            "json",
            "example",
            "--feature",
            "annual_financial_statements",
            "--financial-year",
            "2023",
            "--ai-search",
            "off",
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out) == audit_response
    assert requests == [
        {
            "q": "example",
            "features": ["annual_financial_statements"],
            "ai_search": "off",
            "realtime_mode": None,
        }
    ]


@pytest.mark.parametrize("output_type", ["json", "csv", "xlsx"])
def test_export_retains_reports_and_compact_audits(
    audit_response, tmp_path, monkeypatch, output_type
):
    import pandas as pd

    # Exercise Excel's overflow path for full reports while audits stay compact.
    audit_response["annual_financial_statements"][0]["document_md"] = (
        "Report text " * 4000
    )
    audit_response["annual_financial_statements__html"][0]["document_html"] = (
        "<p>Report text</p>" * 4000
    )
    before = copy.deepcopy(audit_response)
    client = Handelsregister(api_key="test")
    monkeypatch.setattr(client, "fetch_organization", lambda **kwargs: audit_response)
    source = tmp_path / "companies.json"
    source.write_text(json.dumps([{"name": "Example"}]))
    target = tmp_path / ("output." + output_type)
    client.enrich(
        file_path=str(source),
        input_type="json",
        output_file=str(target),
        output_type=output_type,
        query_properties={"name": "name"},
        params={
            "features": [
                "annual_financial_statements",
                "annual_financial_statements__html",
            ]
        },
    )
    assert audit_response == before
    if output_type == "json":
        assert (
            json.loads(target.read_text())[0]["_handelsregister_result"]
            == audit_response
        )
        return
    sheets = pd.read_excel(target, sheet_name=None) if output_type == "xlsx" else None
    frame = sheets["Sheet1"] if sheets else pd.read_csv(target)
    for feature in ("annual_financial_statements", "annual_financial_statements__html"):
        column = "hr_" + feature
        reports = json.loads(frame.iloc[0][column])
        if sheets:
            reference = reports["_handelsregister_excel_overflow"]
            chunks = sheets[reference["sheet"]]
            chunks = chunks[
                (chunks["row"] == reference["row"]) & (chunks["column"] == column)
            ].sort_values("part")
            assert len(chunks) == reference["chunks"]
            reports = json.loads("".join(chunks["value"]))
        assert reports == audit_response[feature]
        metadata = json.loads(frame.iloc[0][column + "_audit"])
        assert len(metadata) == 4  # null is explicit; legacy omission stays absent
        assert [row["year"] for row in metadata] == [2024, 2024, 2023, 2022]
        assert metadata[0]["document_type"] == "Jahresabschluss"
        assert metadata[1]["document_type"] == "Konzernabschluss"
        assert metadata[0]["future_report_field"] == "preserved"
        assert metadata[-1]["audit"] is None
        for row, source_row in zip(metadata, audit_response[feature]):
            assert row["audit"] == source_row["audit"]
            assert row["document_date"] == source_row["document_date"]
            assert "document_md" not in row and "document_html" not in row


def test_legacy_export_has_no_added_audit_column():
    data = {"annual_financial_statements": [{"year": 2020, "document_md": "legacy"}]}
    flat = Handelsregister(api_key="test")._flatten_result(data)
    assert "annual_financial_statements_audit" not in flat
    assert (
        json.loads(flat["annual_financial_statements"])
        == data["annual_financial_statements"]
    )
