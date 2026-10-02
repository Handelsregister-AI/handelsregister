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
    ExecutiveFilters,
    FilterCondition,
    Handelsregister,
    LifecycleFilters,
    MergersAndAcquisitions,
    ORGANIZATION_FEATURES,
    OrganizationFeature,
    OrganizationNetwork,
    OrganizationStatus,
    OwnershipFilters,
    OwnershipStructure,
    Person,
    PersonShareholdings,
    RangeFilter,
    SEARCH_ORGANIZATIONS_MAX_LIMIT,
    SearchFilters,
    SearchSort,
    ShareholderInfo,
    ShareholdersDeep,
    ShareholdingsInfo,
    UBOInfo,
)


COMPANY_QUERY = "KONUX GmbH München"
COMPANY_ENTITY_ID = "110fe0da2f84c8d3174ec7bfd1f0f15a"

ALL_FEATURES = [
    feature for feature in ORGANIZATION_FEATURES if feature not in {"network", "shareholders_deep"}
]


@pytest.fixture(scope="module")
def live_client():
    """Module-scoped real client so the full_company fixture can reuse it."""
    api_key = os.getenv("HANDELSREGISTER_API_KEY") or os.getenv(
        "HANDELSREGISTER_API_KEY_THROW_AWAY"
    )
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
        ai_search="on-default",
    )


@pytest.mark.live_api
class TestFetchOrganization:
    def test_activity_financials(self, live_client):
        """Opt-in energy-company lookup; at most 11 credits, Max for activities."""
        if os.getenv("HANDELSREGISTER_RUN_ACTIVITY_FINANCIALS_TESTS") != "1":
            pytest.skip("Set HANDELSREGISTER_RUN_ACTIVITY_FINANCIALS_TESTS=1 for energy-company financials")
        company = Company("Stadtwerke Bad Pyrmont GmbH", client=live_client, features=[
            OrganizationFeature.BALANCE_SHEET_ACCOUNTS, OrganizationFeature.PROFIT_AND_LOSS_ACCOUNT,
        ])
        statements = company.balance_sheet_entries + company.profit_and_loss_entries
        assert statements
        for statement in statements:
            assert statement.provenance.statement_type
            for activity in statement.activity_statements:
                assert activity.name_text()
                assert activity.provenance.statement_type
                roots = activity.balance_sheet_entries + activity.profit_and_loss_entries
                assert roots
                assert all(root.as_dict() == root.raw for root in roots)

    def test_deep_shareholders(self, live_client):
        """Opt-in Max contract check, up to 85 credits for one fetch."""
        if os.getenv("HANDELSREGISTER_RUN_DEEP_SHAREHOLDERS_TESTS") != "1":
            pytest.skip("Set HANDELSREGISTER_RUN_DEEP_SHAREHOLDERS_TESTS=1 for the Max feature")
        company = Company(COMPANY_ENTITY_ID, client=live_client, features=[OrganizationFeature.SHAREHOLDERS_DEEP])
        deep = company.shareholders_deep
        assert isinstance(deep, ShareholdersDeep)
        if "shareholders_deep" not in company.data:
            pytest.skip("The API omitted shareholders_deep; a Max plan is required")
        if company.data["shareholders_deep"] is None:
            assert not deep
            return
        assert deep.as_dict() == company.data["shareholders_deep"]
        for entry in deep.entries:
            assert entry.holder.type
            if entry.percentage is not None:
                assert 0 <= entry.percentage <= 100

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

    def test_network_feature(self, live_client):
        target_page = live_client.search_organizations(q="BMW", limit=1)
        assert target_page["results"]
        company = Company(
            target_page["results"][0]["entity_id"],
            client=live_client,
            features=[OrganizationFeature.NETWORK],
        )
        if "network" not in company.data:
            pytest.skip("network data or the required Pro/Max plan is unavailable")
        network = company.network
        assert isinstance(network, OrganizationNetwork)
        assert network.depth >= 1
        assert network.root is not None
        assert network.nodes
        assert network.connections
        assert network.connections[0].source.node_id
        assert network.connections[0].target.node_id


@pytest.mark.live_api
class TestSearchOrganizations:
    def test_search_returns_results(self, live_client):
        result = live_client.search_organizations(q="KONUX", limit=5)
        assert isinstance(result, dict)
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0

    def test_search_honors_30_result_page_maximum(self, live_client):
        result = live_client.search_organizations(
            q="GmbH",
            limit=SEARCH_ORGANIZATIONS_MAX_LIMIT,
        )
        assert 0 < len(result["results"]) <= SEARCH_ORGANIZATIONS_MAX_LIMIT
        assert result["total"] >= len(result["results"])

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

    def test_filters_only_search_with_financial_range(self, live_client):
        result = live_client.search_organizations(
            limit=3,
            filters=SearchFilters(
                city="München",
                legal_form_code="GmbH",
                pl_revenue=RangeFilter(gte=1_000_000),
            ),
        )
        assert isinstance(result, dict)
        assert isinstance(result.get("results"), list)

    def test_advanced_filters_sort_and_match_context(self, live_client):
        result = live_client.search_organizations(
            limit=3,
            filters=SearchFilters(
                state="Bayern",
                ownership_filters=OwnershipFilters(
                    structure=[
                        OwnershipStructure.FAMILY,
                        OwnershipStructure.PARTNERS,
                    ],
                    owner_managed=True,
                    oldest_owner_birth_date=FilterCondition(lte="1960"),
                ),
            ),
            sort=SearchSort.LARGEST_SHARE_RATIO,
            order="desc",
            match_context=True,
        )
        assert result["results"]
        assert any(
            isinstance(item.get("_match_context"), dict)
            and item["_match_context"]
            for item in result["results"]
        )

    def test_executive_filter_match_context(self, live_client):
        result = live_client.search_organizations(
            limit=3,
            filters=SearchFilters(
                executive_filters=ExecutiveFilters(
                    md_oldest_birth_date=FilterCondition(lte="1960")
                )
            ),
            match_context=True,
        )
        assert result["results"]
        assert any(
            "executive" in (item.get("_match_context") or {})
            for item in result["results"]
        )

    def test_lifecycle_exists_condition(self, live_client):
        result = live_client.search_organizations(
            limit=3,
            filters=SearchFilters(
                lifecycle_filters=LifecycleFilters(
                    insolvency_active=FilterCondition(exists=False)
                )
            ),
            match_context=True,
        )
        assert isinstance(result.get("results"), list)

    def test_status_liability_and_legacy_geo_input(self, live_client):
        result = live_client.search_organizations(
            limit=3,
            filters=SearchFilters(
                status=OrganizationStatus.ACTIVE,
                legal_form_liability_type="limited",
                location_coordinates={
                    "latitude": 48.137,
                    "longitude": 11.576,
                },
                location_max_distance_km=25,
            ),
            sort=SearchSort.DISTANCE,
            order="asc",
        )
        assert result["results"]
        assert all(
            item.get("status_normalized") == "ACTIVE"
            for item in result["results"]
        )

    def test_registration_date_sort_order(self, live_client):
        result = live_client.search_organizations(
            q="GmbH",
            limit=10,
            sort=SearchSort.REGISTRATION_DATE,
            order="desc",
        )
        dates = [
            item["registration_date"]
            for item in result["results"]
            if item.get("registration_date")
        ]
        assert len(dates) >= 2
        assert dates == sorted(dates, reverse=True)

    def test_advanced_filter_iterator_preserves_options(self, live_client):
        results = list(
            live_client.iter_search_organizations(
                filters=SearchFilters(
                    ownership_filters=OwnershipFilters(owner_managed=True)
                ),
                page_size=20,
                max_results=21,
                sort=SearchSort.LARGEST_SHARE_RATIO,
                order="desc",
                match_context=True,
            )
        )
        assert len(results) == 21
        assert all(isinstance(item.get("_match_context"), dict) for item in results)


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
        assert isinstance(full_company.representation_scheme.current, list)
        assert isinstance(full_company.representation_scheme.history, list)


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

    def test_representation_schemes(self, full_company):
        entries = full_company.related_person_entries
        assert entries.current
        first = entries.current[0]
        assert isinstance(first.organization_representation_scheme.history, list)
        assert isinstance(first.role_representation_scheme.history, list)


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
class TestMergersAndAcquisitions:
    def test_typed_wrapper(self, full_company):
        info = full_company.mergers_and_acquisitions
        assert isinstance(info, MergersAndAcquisitions)
        assert isinstance(info.transactions, list)
        assert isinstance(info.summary, dict)

    def test_known_company_has_transactions(self, live_client):
        data = live_client.fetch_organization(
            q="Teltec AG",
            features=["mergers_and_acquisitions"],
        )
        info = MergersAndAcquisitions.from_payload(
            data.get("mergers_and_acquisitions")
        )
        assert info.transactions
        assert info.transactions[0].id
        assert info.transactions[0].counterparties


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

    def test_fetch_si_xml(self, live_client):
        xml = live_client.fetch_document(COMPANY_ENTITY_ID, "SI")
        assert isinstance(xml, bytes)
        assert xml.lstrip().startswith(b"<"), "response is not XML"


@pytest.mark.live_api
class TestPerson:
    def test_fetch_person_with_shareholdings(self, live_client):
        person = Person(
            person_q="Johanna Leisch",
            organization_q="KONUX GmbH",
            client=live_client,
            features=["shareholdings"],
        )
        assert isinstance(person.data, dict)
        # The API should return at least a name (canonical or plain).
        assert person.name or person.canonical_name
        assert isinstance(person.handelsregister_roles, list)
        assert isinstance(person.shareholdings, PersonShareholdings)
