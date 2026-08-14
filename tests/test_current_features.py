import json
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest

from handelsregister import (
    Company,
    DocumentType,
    ExecutiveFilters,
    FilterCondition,
    Handelsregister,
    InsolvencyStatus,
    InvalidResponseError,
    InsufficientCreditsError,
    MergersAndAcquisitions,
    LifecycleFilters,
    LegalFormLiabilityType,
    LocationCoordinates,
    OrganizationNetwork,
    NotFoundError,
    OrganizationFeature,
    OrganizationStatus,
    OwnershipFilters,
    OwnershipStructure,
    RangeFilter,
    RateLimitError,
    RequestValidationError,
    RequestTimeoutError,
    SEARCH_ORGANIZATIONS_MAX_LIMIT,
    SEARCH_ORGANIZATIONS_MAX_QUERY_LENGTH,
    SearchSort,
    SearchFilters,
    SortOrder,
    ServerError,
    SubscriptionRequiredError,
)
from handelsregister.cli import main as cli_main


def company_from(data):
    client = MagicMock(spec=Handelsregister)
    client.fetch_organization.return_value = data
    return Company("Example GmbH", client=client)


def test_representation_scheme_at_company_and_related_person_level():
    company = company_from(
        {
            "representation_scheme": {
                "current": ["Two directors represent jointly."],
                "history": [
                    {
                        "value": ["A director represents individually."],
                        "effective_from": "2020-01-01",
                        "effective_to": "2024-01-01",
                    }
                ],
            },
            "related_persons": {
                "current": [
                    {
                        "name": "Current Director",
                        "label": "MANAGING_DIRECTOR",
                        "organization_representation_scheme": {
                            "current": ["Two directors represent jointly."],
                            "history": [],
                        },
                        "role_representation_scheme": {
                            "current": ["Authorized to represent individually."],
                            "history": [],
                        },
                    }
                ],
                "past": [
                    {
                        "name": "Past Director",
                        "role_representation_scheme": {
                            "latest": ["Was authorized to represent individually."],
                            "history": [
                                {
                                    "value": ["Was authorized jointly."],
                                    "effective_from": "2018-01-01",
                                    "effective_to": "2019-01-01",
                                }
                            ],
                        },
                    }
                ],
            },
        }
    )

    assert company.representation_scheme.active == [
        "Two directors represent jointly."
    ]
    assert company.representation_scheme.history[0].effective_to == "2024-01-01"

    people = company.related_person_entries
    assert people.current[0].display_name == "Current Director"
    assert people.current[0].role_representation_scheme.current == [
        "Authorized to represent individually."
    ]
    assert people.past[0].role_representation_scheme.active == [
        "Was authorized to represent individually."
    ]
    # Existing dictionary interface remains unchanged.
    assert company.current_related_persons[0]["name"] == "Current Director"


def test_mergers_and_acquisitions_typed_view_is_lossless():
    payload = {
        "transactions": [
            {
                "id": "tx-1",
                "headline": {
                    "en": "Result transfer agreement concluded",
                    "de": "Ergebnisabführungsvertrag geschlossen",
                },
                "type": {
                    "category": "ENTERPRISE_AGREEMENT",
                    "event_type": "GROUP.ENTERPRISE_AGREEMENT",
                },
                "kind": {"label": "RESULT_TRANSFER"},
                "role": {"label": "CONTROLLED"},
                "phase": "REGISTERED",
                "date": "2023-10-11",
                "counterparties": [
                    {
                        "entity_id": "counterparty-1",
                        "name": "Parent AG",
                        "registration": {
                            "court": "Düsseldorf",
                            "register_type": "HRB",
                            "register_number": "123",
                        },
                        "role": {"label": "CONTROLLING"},
                    }
                ],
                "register_entries": [
                    {"registered_at": "2023-10-11", "description": "Registered"}
                ],
            }
        ],
        "succession": None,
        "control": {
            "controlled_by": [
                {
                    "counterparty": {"entity_id": "counterparty-1", "name": "Parent AG"},
                    "via": {"label": "RESULT_TRANSFER"},
                    "loss_absorption_obligation": True,
                    "since": "2023-10-11",
                    "transaction_ids": ["tx-1"],
                }
            ],
            "controls": [],
            "former": [],
        },
        "summary": {
            "total_transactions": 1,
            "by_category": {"ENTERPRISE_AGREEMENT": {"count": 1}},
            "first_date": "2023-10-11",
            "last_date": "2023-10-11",
        },
    }
    company = company_from({"mergers_and_acquisitions": payload})
    info = company.mergers_and_acquisitions

    assert isinstance(info, MergersAndAcquisitions)
    assert info.as_dict() == payload
    assert info.total_transactions == 1
    assert info.transactions[0].category == "ENTERPRISE_AGREEMENT"
    assert info.transactions[0].counterparties[0].name == "Parent AG"
    assert info.control.controlled_by[0].loss_absorption_obligation is True


def test_organization_network_typed_view_is_lossless():
    payload = {
        "depth": 2,
        "nodes": [
            {
                "node_id": "organization-1",
                "entity_id": "organization-1",
                "type": "ORGANIZATION",
                "name": "Example GmbH",
                "depth": 0,
                "is_root": True,
            },
            {
                "node_id": "person-1",
                "entity_id": "person-1",
                "type": "PERSON",
                "name": "Ada Example",
                "depth": 1,
                "is_root": False,
            },
        ],
        "connections": [
            {
                "source": {
                    "node_id": "person-1",
                    "type": "PERSON",
                    "name": "Ada Example",
                },
                "target": {
                    "node_id": "organization-1",
                    "type": "ORGANIZATION",
                    "name": "Example GmbH",
                },
                "connection_type": "ROLE",
                "label": "MANAGING_DIRECTOR",
                "role": {
                    "en": {"long": "Managing Director"},
                    "de": {"long": "Geschäftsführerin"},
                },
                "start_date": "2020-01-01",
                "end_date": None,
                "is_current": True,
                "depth": 1,
            }
        ],
    }
    company = company_from({"network": payload})
    network = company.network

    assert isinstance(network, OrganizationNetwork)
    assert network.as_dict() == payload
    assert network.depth == 2
    assert network.root.name == "Example GmbH"
    assert network.nodes[1].entity_id == "person-1"
    assert network.connections[0].source.node_id == "person-1"
    assert network.connections[0].target.name == "Example GmbH"
    assert network.connections[0].role_name("de") == "Geschäftsführerin"
    assert network.connections[0].is_current is True


def test_current_shareholder_history_and_ubo_person_shape():
    company = company_from(
        {
            "shareholders": {
                "entries": [
                    {
                        "shareholder": {"first_name": "Ada", "last_name": "Lovelace"},
                        "contribution": {"amount": 100, "currency": "EUR"},
                        "contribution_ratio": 0.4,
                    }
                ],
                "total_capital": {"amount": 250, "currency": "EUR"},
                "history": {
                    "current_as_of": "2025-07-04",
                    "past": [
                        {
                            "as_of": "2024-01-01",
                            "data": {
                                "total_capital": {"amount": 200, "currency": "EUR"},
                                "shareholders": [
                                    {
                                        "shareholder": {
                                            "entity_name": "Historical Holding GmbH"
                                        },
                                        "contribution": {
                                            "amount": 50,
                                            "currency": "EUR",
                                        },
                                        "contribution_ratio": 0.25,
                                    }
                                ],
                            },
                        }
                    ],
                },
            },
            "ubos": {
                "beneficial_owners": [
                    {
                        "person": {
                            "entity_id": "person-1",
                            "name": "Ada Lovelace",
                            "birth_date": "1815-12-10",
                        },
                        "ownership_percentage": 40,
                        "paths": [{"percentage": 40, "via": []}],
                    }
                ],
                "unresolved_beneficial_owners": [
                    {
                        "entity_id": "organization-1",
                        "name": "Unknown Holding KG",
                        "reason": "no_further_shareholder_data",
                        "ownership_percentage": 10,
                    }
                ],
            },
        }
    )

    shareholders = company.shareholders
    assert shareholders.current_as_of == "2025-07-04"
    assert shareholders.history[0].entries[0].display_name == "Historical Holding GmbH"

    ubos = company.ubos
    assert ubos.resolved[0].name == "Ada Lovelace"
    assert ubos.resolved[0].entity_id == "person-1"
    assert ubos.resolved[0].percentage == 40
    assert ubos.resolved[0].paths[0]["percentage"] == 40
    assert ubos.unresolved[0].resolved is False
    assert ubos.unresolved[0].reason == "no_further_shareholder_data"


def test_publications_use_documented_history_response_key():
    company = company_from(
        {
            "history": [{"entity_type": "EVENT", "name": {"en": "Change"}}],
            "publications": [{"legacy": True}],
        }
    )
    assert company.publications == company.history


def _mock_get_response(mock_httpx, payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    session = MagicMock()
    session.get.return_value = response
    mock_httpx.return_value.__enter__.return_value = session
    return response, session


@patch("handelsregister.client.httpx.Client")
def test_filters_only_search_supports_all_shapes_and_nested_cache(mock_httpx):
    _, session = _mock_get_response(mock_httpx, {"results": [], "total": 0})
    client = Handelsregister(api_key="test", cache_enabled=True)
    filters = SearchFilters(
        legal_form_code="GmbH",
        active=True,
        city="München",
        location_coordinates={"latitude": 48.13, "longitude": 11.58},
        location_max_distance_km=25,
        registration_type=["HRB"],
        company_size_category="medium",
        emp_count=RangeFilter(gte=50, lte=250),
        bs_equity_ratio=RangeFilter(gte=0.2),
        pl_revenue=RangeFilter(gte=1_000_000, lte=5_000_000),
    )

    first = client.search_organizations(
        filters=filters, limit=30, ai_mode="on-default"
    )
    second = client.search_organizations(
        filters=filters, limit=30, ai_mode="on-default"
    )

    assert first == second
    assert session.get.call_count == 1
    params = session.get.call_args.kwargs["params"]
    assert "q" not in params
    assert params["ai_mode"] == "on-default"
    encoded = json.loads(params["filters"])
    assert encoded["financial_filters"]["pl_revenue"] == {
        "gte": 1_000_000,
        "lte": 5_000_000,
    }
    assert encoded["company_size_category"] == "medium"
    assert encoded["location_coordinates"] == {"lat": 48.13, "lon": 11.58}
    assert encoded["active"] is True


@patch("handelsregister.client.httpx.Client")
def test_advanced_search_filters_sorting_and_match_context(mock_httpx):
    _, session = _mock_get_response(mock_httpx, {"results": [], "total": 0})
    client = Handelsregister(api_key="test")
    filters = SearchFilters(
        status=OrganizationStatus.ACTIVE,
        legal_form_liability_type=LegalFormLiabilityType.LIMITED,
        location_coordinates=LocationCoordinates(lat=48.137, lon=11.576),
        location_max_distance_km=25,
        ownership_filters=OwnershipFilters(
            structure=OwnershipStructure.FAMILY,
            owner_managed=True,
            largest_share_ratio=FilterCondition(gte=0.5),
            oldest_owner_birth_date=FilterCondition(lte="1960"),
        ),
        executive_filters=ExecutiveFilters(
            md_oldest_birth_date=FilterCondition(lte="1960")
        ),
        lifecycle_filters=LifecycleFilters(
            insolvency_active=FilterCondition(exists=False),
            insolvency_status=InsolvencyStatus.OPENED,
        ),
    )

    client.search_organizations(
        filters=filters,
        sort=SearchSort.LARGEST_SHARE_RATIO,
        order=SortOrder.DESC,
        match_context=True,
    )

    params = session.get.call_args.kwargs["params"]
    assert params["sort"] == "largest_share_ratio"
    assert params["order"] == "desc"
    assert params["match_context"] == 1
    encoded = json.loads(params["filters"])
    assert encoded["status"] == "ACTIVE"
    assert encoded["legal_form_liability_type"] == "limited"
    assert encoded["location_coordinates"] == {"lat": 48.137, "lon": 11.576}
    assert encoded["ownership_filters"] == {
        "structure": "family",
        "owner_managed": True,
        "largest_share_ratio": {"gte": 0.5},
        "oldest_owner_birth_date": {"lte": "1960"},
    }
    assert encoded["executive_filters"] == {
        "md_oldest_birth_date": {"lte": "1960"}
    }
    assert encoded["lifecycle_filters"] == {
        "insolvency_active": {"exists": False},
        "insolvency_status": "opened",
    }


def test_search_and_realtime_validations():
    client = Handelsregister(api_key="test")
    assert SEARCH_ORGANIZATIONS_MAX_LIMIT == 30
    assert SEARCH_ORGANIZATIONS_MAX_QUERY_LENGTH == 500
    with pytest.raises(ValueError, match="Either parameter"):
        client.search_organizations()
    with pytest.raises(ValueError, match="between 1 and 30"):
        client.search_organizations(q="valid", limit=31)
    with pytest.raises(ValueError, match="requires"):
        client.search_organizations(
            filters={"location_max_distance_km": 10}
        )
    with pytest.raises(ValueError, match="at most 500"):
        client.search_organizations(q="x" * 501)
    with pytest.raises(TypeError, match="legal_form_code"):
        client.search_organizations(filters={"legal_form_code": ["GmbH", "AG"]})
    with pytest.raises(ValueError, match="location_max_distance_km"):
        client.search_organizations(
            filters={"location_coordinates": {"lat": 48.13, "lon": 11.58}}
        )
    with pytest.raises(ValueError, match="Parameter 'sort'"):
        client.search_organizations(q="valid", sort="unknown")
    with pytest.raises(ValueError, match="requires filter"):
        client.search_organizations(q="valid", sort=SearchSort.DISTANCE)
    with pytest.raises(TypeError, match="match_context"):
        client.search_organizations(q="valid", match_context=1)
    with pytest.raises(ValueError, match="unsupported value"):
        client.search_organizations(
            filters={"ownership_filters": {"structure": "unknown"}}
        )
    with pytest.raises(ValueError, match="unsupported operators"):
        client.search_organizations(
            filters={
                "executive_filters": {
                    "md_oldest_birth_date": {"before": "1960"}
                }
            }
        )
    with pytest.raises(ValueError, match="cannot be combined"):
        client.fetch_organization(
            q="Example GmbH",
            features=[OrganizationFeature.RELATED_PERSONS],
            realtime_mode="handelsregister-default",
        )


def test_iter_search_organizations_fetches_100_in_four_pages(monkeypatch):
    client = Handelsregister(api_key="test", cache_enabled=False)
    calls = []

    def fake_search(q=None, skip=0, limit=10, filters=None, ai_mode=None, **kwargs):
        calls.append(
            {
                "q": q,
                "skip": skip,
                "limit": limit,
                "filters": filters,
                "ai_mode": ai_mode,
                "kwargs": kwargs,
            }
        )
        return {
            "results": [
                {"entity_id": f"organization-{index}"}
                for index in range(skip, skip + limit)
            ],
            "total": 250,
        }

    monkeypatch.setattr(client, "search_organizations", fake_search)

    results = list(
        client.iter_search_organizations(
            q="technology",
            page_size=30,
            max_results=100,
            filters={"city": "München"},
            ai_mode="on-default",
            sort=SearchSort.REVENUE,
            order=SortOrder.DESC,
            match_context=True,
            custom="value",
        )
    )

    assert len(results) == 100
    assert [call["skip"] for call in calls] == [0, 30, 60, 90]
    assert [call["limit"] for call in calls] == [30, 30, 30, 10]
    assert all(call["filters"] == {"city": "München"} for call in calls)
    assert all(call["ai_mode"] == "on-default" for call in calls)
    assert all(
        call["kwargs"]
        == {
            "sort": SearchSort.REVENUE,
            "order": SortOrder.DESC,
            "match_context": True,
            "custom": "value",
        }
        for call in calls
    )


def test_iter_search_organizations_is_lazy_and_stops_at_total(monkeypatch):
    client = Handelsregister(api_key="test", cache_enabled=False)
    calls = []

    def fake_search(q=None, skip=0, limit=10, **kwargs):
        calls.append((skip, limit))
        available = max(0, min(limit, 35 - skip))
        return {
            "results": [
                {"entity_id": f"organization-{index}"}
                for index in range(skip, skip + available)
            ],
            "total": 35,
        }

    monkeypatch.setattr(client, "search_organizations", fake_search)
    iterator = client.iter_search_organizations(q="technology", page_size=30)

    assert calls == []
    assert len(list(iterator)) == 35
    assert calls == [(0, 30), (30, 30)]


def test_iter_search_organizations_validates_and_rejects_invalid_responses(
    monkeypatch,
):
    client = Handelsregister(api_key="test", cache_enabled=False)

    with pytest.raises(ValueError, match="page_size.*1 and 30"):
        list(client.iter_search_organizations(q="valid", page_size=31))
    with pytest.raises(ValueError, match="max_results"):
        list(client.iter_search_organizations(q="valid", max_results=-1))
    assert list(client.iter_search_organizations(q="valid", max_results=0)) == []

    monkeypatch.setattr(
        client,
        "search_organizations",
        lambda **kwargs: {"results": "not-a-list", "total": 1},
    )
    with pytest.raises(InvalidResponseError, match="'results' list"):
        list(client.iter_search_organizations(q="valid"))


@patch("handelsregister.client.httpx.Client")
def test_si_document_accepts_xml(mock_httpx, tmp_path):
    response = MagicMock()
    response.headers = {"content-type": "application/xml; charset=utf-8"}
    response.content = b"<?xml version='1.0'?><company/>"
    response.raise_for_status.return_value = None
    session = MagicMock()
    session.get.return_value = response
    mock_httpx.return_value.__enter__.return_value = session

    output = tmp_path / "company.xml"
    client = Handelsregister(api_key="test")
    content = client.fetch_document(
        company_id="company-1",
        document_type=DocumentType.STRUCTURED_INFORMATION,
        output_file=str(output),
    )

    assert content.startswith(b"<?xml")
    assert output.read_bytes() == content
    assert session.get.call_args.kwargs["params"]["document_type"] == "SI"


@pytest.mark.parametrize(
    ("status_code", "payload", "exception_type"),
    [
        (
            402,
            {
                "meta": {
                    "message": "Insufficient credits to perform this operation.",
                    "request_credit_cost": 25,
                    "credits_remaining": 3,
                }
            },
            InsufficientCreditsError,
        ),
        (
            403,
            {
                "error": "subscription_required",
                "meta": {
                    "message": "fetch-person requires an active subscription.",
                    "request_credit_cost": 0,
                },
            },
            SubscriptionRequiredError,
        ),
    ],
)
@patch("handelsregister.client.httpx.Client")
def test_structured_api_errors_preserve_meta(
    mock_httpx, status_code, payload, exception_type
):
    request = httpx.Request("GET", "https://example.test/api")
    error_response = httpx.Response(
        status_code, request=request, json=payload
    )
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=request, response=error_response
    )
    session = MagicMock()
    session.get.return_value = response
    mock_httpx.return_value.__enter__.return_value = session

    client = Handelsregister(api_key="test")
    with pytest.raises(exception_type) as caught:
        client.fetch_organization(q="Example GmbH")
    assert caught.value.status_code == status_code
    assert caught.value.meta["request_credit_cost"] in (0, 25)
    if exception_type is SubscriptionRequiredError:
        assert str(caught.value) == "fetch-person requires an active subscription."


def test_subscription_error_exposes_plan_and_blocked_context():
    error = SubscriptionRequiredError(
        "These filters require an active Pro or Max subscription.",
        status_code=403,
        payload={
            "error": "subscription_required",
            "meta": {
                "required_plans": ["pro", "max"],
                "blocked_filters": ["ownership_filters"],
                "blocked_features": ["network"],
            },
        },
    )

    assert error.code == "subscription_required"
    assert error.required_plans == ["pro", "max"]
    assert error.blocked_filters == ["ownership_filters"]
    assert error.blocked_features == ["network"]


def test_network_feature_preflights_plan_without_billing_base_request(monkeypatch):
    client = Handelsregister(api_key="test", cache_enabled=False)
    request = MagicMock()
    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(
        client,
        "get_account_subscription",
        lambda: {"subscription": None, "meta": {"request_credit_cost": 0}},
    )

    with pytest.raises(SubscriptionRequiredError) as caught:
        client.fetch_organization(
            q="Example GmbH",
            features=[OrganizationFeature.NETWORK],
        )

    request.assert_not_called()
    assert str(caught.value) == (
        "The 'network' feature requires an active Pro or Max subscription."
    )
    assert caught.value.required_plans == ["pro", "max"]
    assert caught.value.blocked_features == ["network"]
    assert caught.value.meta["request_credit_cost"] == 0


def test_network_feature_allows_entitled_plan(monkeypatch):
    client = Handelsregister(api_key="test", cache_enabled=False)
    request = MagicMock(return_value={"network": {"nodes": [], "connections": []}})
    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(
        client,
        "get_account_subscription",
        lambda: {"subscription": {"plan": "max", "status": "active"}},
    )

    result = client.fetch_organization(
        q="Example GmbH",
        features=[OrganizationFeature.NETWORK],
    )

    assert "network" in result
    request.assert_called_once()


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (400, RequestValidationError),
        (422, RequestValidationError),
        (404, NotFoundError),
        (408, RequestTimeoutError),
        (429, RateLimitError),
        (500, ServerError),
    ],
)
@patch("handelsregister.client.httpx.Client")
def test_other_documented_errors_are_mapped_without_4xx_retries(
    mock_httpx, status_code, exception_type
):
    request = httpx.Request("GET", "https://example.test/api")
    error_response = httpx.Response(
        status_code,
        request=request,
        json={
            "detail": [{"msg": "Documented failure"}],
            "meta": {"request_credit_cost": 0},
        },
    )
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=request, response=error_response
    )
    session = MagicMock()
    session.get.return_value = response
    mock_httpx.return_value.__enter__.return_value = session

    client = Handelsregister(api_key="test")
    with pytest.raises(exception_type):
        client._request("fetch-organization", {"q": "Example"}, max_retries=1)
    assert session.get.call_count == 1


@patch("handelsregister.client.time.sleep")
@patch("handelsregister.client.httpx.Client")
def test_408_is_retried_as_transient(mock_httpx, mock_sleep):
    request = httpx.Request("GET", "https://example.test/api")
    timeout_response = httpx.Response(408, request=request)
    first = MagicMock()
    first.raise_for_status.side_effect = httpx.HTTPStatusError(
        "timeout", request=request, response=timeout_response
    )
    second = MagicMock()
    second.raise_for_status.return_value = None
    second.json.return_value = {"ok": True}

    session = MagicMock()
    session.get.side_effect = [first, second]
    mock_httpx.return_value.__enter__.return_value = session

    client = Handelsregister(api_key="test")
    assert client._request("fetch-person", {}, max_retries=2) == {"ok": True}
    assert session.get.call_count == 2
    mock_sleep.assert_called_once()


@patch("handelsregister.client.httpx.Client")
def test_token_list_and_revoke_all(mock_httpx):
    list_response = MagicMock()
    list_response.raise_for_status.return_value = None
    list_response.json.return_value = {"tokens": [{"id": 1}]}
    delete_response = MagicMock()
    delete_response.raise_for_status.return_value = None
    delete_response.content = b""

    session = MagicMock()
    session.get.return_value = list_response
    session.delete.return_value = delete_response
    mock_httpx.return_value.__enter__.return_value = session

    client = Handelsregister(api_key="test")
    assert client.list_tokens()["tokens"][0]["id"] == 1
    assert client.revoke_all_tokens() == {}
    assert session.delete.call_args.args[0].endswith("/auth/tokens")


def test_cli_filters_only_search(monkeypatch, capsys):
    captured = {}

    def fake_search(
        self, q=None, skip=0, limit=10, filters=None, ai_mode=None, **kwargs
    ):
        captured.update(
            q=q, skip=skip, limit=limit, filters=filters, ai_mode=ai_mode
        )
        return {"results": [], "total": 0}

    monkeypatch.setattr(Handelsregister, "search_organizations", fake_search)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "handelsregister",
            "search",
            "--filters",
            '{"city":"München","pl_revenue":{"gte":1000000}}',
            "--filter",
            "active=true",
            "--ai-mode",
            "on-default",
            "--json",
        ],
    )
    cli_main()
    assert json.loads(capsys.readouterr().out)["total"] == 0
    assert captured["q"] is None
    assert captured["filters"]["active"] is True
    assert captured["filters"]["pl_revenue"]["gte"] == 1_000_000
    assert captured["ai_mode"] == "on-default"


def test_cli_accepts_si_document(monkeypatch, tmp_path):
    captured = {}

    def fake_fetch_organization(self, q, ai_search=None, **kwargs):
        return {"entity_id": "company-1", "name": "Example GmbH"}

    def fake_fetch_document(self, company_id, document_type, output_file=None):
        captured.update(
            company_id=company_id,
            document_type=document_type,
            output_file=output_file,
        )
        return b"<company/>"

    output = tmp_path / "company.xml"
    monkeypatch.setattr(
        Handelsregister, "fetch_organization", fake_fetch_organization
    )
    monkeypatch.setattr(Handelsregister, "fetch_document", fake_fetch_document)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "handelsregister",
            "document",
            "Example GmbH",
            "--type",
            "SI",
            "--output",
            str(output),
        ],
    )
    cli_main()
    assert captured["document_type"] == "SI"
    assert captured["output_file"] == str(output)


def test_enrichment_flattening_preserves_new_nested_features():
    client = Handelsregister(api_key="test")
    flattened = client._flatten_result(
        {
            "name": "Example GmbH",
            "representation_scheme": {"current": ["Rule"]},
            "mergers_and_acquisitions": {
                "transactions": [{"id": "tx-1"}],
                "summary": {"total_transactions": 1},
            },
        }
    )
    assert json.loads(flattened["representation_scheme"])["current"] == ["Rule"]
    assert (
        json.loads(flattened["mergers_and_acquisitions"])["transactions"][0]["id"]
        == "tx-1"
    )
