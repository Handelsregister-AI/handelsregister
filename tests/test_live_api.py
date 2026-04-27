"""
Comprehensive live API integration tests.

Skipped by default. Run with::

    HANDELSREGISTER_API_KEY=<key> pytest -m live_api -v

Exercises the full SDK surface against the real handelsregister.ai API:

- ``Handelsregister`` client: ``fetch_organization`` (with every major
  feature), ``fetch_person``, ``search_organizations``, ``fetch_document``.
- ``Company`` wrapper: shareholders, UBOs, outbound shareholdings, related
  persons, financial KPIs, balance sheet, P&L, publications.
- ``Person`` wrapper: profile, Handelsregister roles, shareholdings.

Tests share a single, fully-featured ``Company`` fetch via a module-scoped
fixture so we don't burn credits across repeated calls.
"""
import os

import pytest

from handelsregister import (
    Company,
    Handelsregister,
    Person,
    PersonShareholdings,
    ShareholderInfo,
    ShareholdingsInfo,
    UBOInfo,
)


COMPANY_QUERY = "KONUX GmbH München"

ALL_FEATURES = [
    "related_persons",
    "publications",
    "financial_kpi",
    "balance_sheet_accounts",
    "profit_and_loss_account",
    "shareholders",
    "ubos",
    "shareholdings",
]


@pytest.fixture(scope="module")
def live_client():
    """Module-scoped real client so the full_company fixture can reuse it."""
    api_key = os.getenv("HANDELSREGISTER_API_KEY")
    if not api_key:
        pytest.skip("HANDELSREGISTER_API_KEY environment variable not set")
    return Handelsregister(api_key=api_key)


@pytest.fixture(scope="module")
def full_company(live_client):
    """Fetch a single company with every supported feature, once per module."""
    return Company(
        COMPANY_QUERY,
        client=live_client,
        features=ALL_FEATURES,
    )


@pytest.mark.live_api
class TestFetchOrganization:
    def test_basic_fetch(self, live_client):
        result = live_client.fetch_organization(q=COMPANY_QUERY)
        assert isinstance(result, dict)
        assert result.get("name")
        assert "registration" in result
        assert result["registration"].get("register_number")

    def test_fetch_with_all_features(self, full_company):
        assert full_company.name
        assert full_company.entity_id
        # The API is allowed to omit empty-array features (e.g. publications)
        # from the response, so only assert the data-rich features made it
        # through. Per-feature shape is verified in dedicated tests below.
        data = full_company.data
        for feature in (
            "related_persons",
            "financial_kpi",
            "shareholders",
            "ubos",
            "shareholdings",
        ):
            assert feature in data, f"missing feature in response: {feature}"


@pytest.mark.live_api
class TestSearchOrganizations:
    def test_search_returns_results(self, live_client):
        result = live_client.search_organizations(q="KONUX", limit=5)
        assert isinstance(result, dict)
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0

    def test_search_with_filters(self, live_client):
        # postal_code is the documented filter. The endpoint occasionally
        # returns 500s server-side under load; tolerate that here so the
        # SDK-level shape is what we're really checking.
        from handelsregister.exceptions import HandelsregisterError

        try:
            result = live_client.search_organizations(
                q="GmbH", limit=3, filters={"postal_code": "80992"}
            )
        except HandelsregisterError as exc:
            pytest.skip(f"search_organizations with filter unavailable: {exc}")
        assert isinstance(result, dict)
        assert "results" in result


@pytest.mark.live_api
class TestCompanyBasics:
    def test_basic_properties(self, full_company):
        assert "KONUX" in full_company.name
        assert full_company.entity_id
        assert full_company.registration_number
        assert full_company.registration_court
        assert full_company.registration_type
        assert full_company.legal_form_name
        assert full_company.formatted_address
        assert isinstance(full_company.is_active, bool)


@pytest.mark.live_api
class TestRelatedPersons:
    def test_current_related_persons(self, full_company):
        assert len(full_company.current_related_persons) > 0
        first = full_company.current_related_persons[0]
        # API returns label either at the top level or under role
        assert first.get("label") or (first.get("role") or {}).get("label")

    def test_managing_directors(self, full_company):
        directors = full_company.get_related_persons_by_role(
            "MANAGING_DIRECTOR", current_only=True
        )
        assert len(directors) > 0


@pytest.mark.live_api
class TestFinancials:
    def test_financial_years_populated(self, full_company):
        assert full_company.financial_kpi, "expected financial_kpi data for KONUX"
        years = full_company.financial_years
        assert len(years) > 0
        recent = years[0]
        kpi = full_company.get_financial_kpi_for_year(recent)
        assert kpi  # non-empty dict

    def test_balance_sheet_round_trip(self, full_company):
        if not full_company.balance_sheet_accounts:
            pytest.skip("no balance sheet data returned")
        year = full_company.balance_sheet_accounts[0].get("year")
        assert year
        assert full_company.get_balance_sheet_for_year(year)

    def test_profit_and_loss_round_trip(self, full_company):
        if not full_company.profit_and_loss_account:
            pytest.skip("no profit and loss data returned")
        year = full_company.profit_and_loss_account[0].get("year")
        assert year
        assert full_company.get_profit_and_loss_for_year(year)


@pytest.mark.live_api
class TestShareholders:
    def test_shareholders_typed_wrapper(self, full_company):
        info = full_company.shareholders
        assert isinstance(info, ShareholderInfo)
        assert info.entries, "expected at least one shareholder entry"
        first = info.entries[0]
        assert first.display_name
        assert isinstance(first.contribution, dict)
        # raw passthrough
        assert isinstance(info.as_dict(), dict)


@pytest.mark.live_api
class TestUBOs:
    def test_ubos_typed_wrapper(self, full_company):
        info = full_company.ubos
        assert isinstance(info, UBOInfo)
        assert isinstance(info.resolved, list)
        assert isinstance(info.unresolved, list)
        # KONUX is a private GmbH with corporate parents — expect coverage
        # data and at least one resolved or unresolved owner.
        assert info.resolved or info.unresolved, (
            "expected at least one UBO entry for KONUX GmbH"
        )
        # Spot-check that the wrapper surfaces both the name and percentage
        # fields from whichever shape the API returned.
        sample = (info.resolved + info.unresolved)[0]
        assert sample.name
        assert sample.percentage is not None


@pytest.mark.live_api
class TestShareholdings:
    def test_shareholdings_typed_wrapper(self, full_company):
        info = full_company.shareholdings
        assert isinstance(info, ShareholdingsInfo)
        assert isinstance(info.current, list)
        assert isinstance(info.past, list)
        # Outbound shareholdings may be empty for KONUX; verify the shape
        # but don't require entries.


@pytest.mark.live_api
class TestPublications:
    def test_publications_returned(self, full_company):
        assert isinstance(full_company.publications, list)


@pytest.mark.live_api
class TestFetchDocument:
    def test_fetch_ad_pdf(self, full_company):
        pdf = full_company.fetch_document("AD")
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF"), "response is not a PDF"


@pytest.mark.live_api
class TestPerson:
    def test_fetch_person_with_shareholdings(self, full_company, live_client):
        directors = full_company.get_related_persons_by_role(
            "MANAGING_DIRECTOR", current_only=True
        )
        if not directors:
            pytest.skip("no current managing director to query")

        director = directors[0]
        # The related-persons payload may store a name as a dict
        # ({"given": "...", "family": "..."}) or as a flat string.
        name_field = director.get("name")
        if isinstance(name_field, dict):
            given = name_field.get("given") or director.get("given_name")
            family = name_field.get("family") or director.get("family_name")
            person_q = " ".join(filter(None, [given, family])).strip()
        elif isinstance(name_field, str):
            person_q = name_field
        else:
            person_q = director.get("display_name") or ""

        if not person_q or len(person_q) < 2:
            pytest.skip(f"could not derive person query from director: {director!r}")

        person = Person(
            person_q=person_q,
            organization_q=full_company.name,
            client=live_client,
            features=["shareholdings"],
        )
        assert isinstance(person.data, dict)
        # The API should return at least a name (canonical or plain).
        assert person.name or person.canonical_name
        assert isinstance(person.handelsregister_roles, list)
        assert isinstance(person.shareholdings, PersonShareholdings)
