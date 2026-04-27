from unittest.mock import MagicMock

import pytest

from handelsregister import Person, Handelsregister
from handelsregister.exceptions import HandelsregisterError


SAMPLE_PERSON_RESPONSE = {
    "entity_id": "f1e2d3c4b5a69788a7b6c5d4e3f2a1b0",
    "name": "Max Mustermann",
    "birth_date": "1985-07-14",
    "name_parts": {
        "given": "Max",
        "family": "Mustermann",
        "canonical_name": "Mustermann, Max",
        "previous_names": None,
    },
    "location": {"home": {"city": "München"}},
    "bio": "Max Mustermann ist Mitgründer und Geschäftsführer.",
    "expertise": ["Produktentwicklung", "KI"],
    "contact": {"emails": [{"address": "info@example.de"}], "phones": []},
    "profiles": {
        "linkedin": "https://linkedin.com/in/max-mustermann",
        "github": "https://github.com/max-mustermann",
        "other": [],
    },
    "affiliations": [
        {"organization": "Beispielwerk Analytics GmbH", "relation": "Geschäftsführer"}
    ],
    "handelsregister_roles": [
        {
            "entity_id": "b4a3c2d1e5f697887a6b5c4d3e2f1a0b",
            "name": "Beispielwerk Analytics GmbH",
            "label": "MANAGING_DIRECTOR",
            "role": {"en": "Managing Director", "de": "Geschäftsführer"},
            "start_date": "2019-06-03",
            "end_date": None,
        }
    ],
    "shareholdings": {
        "holdings": {
            "current": [
                {
                    "organization": {
                        "entity_id": "b4a3c2d1e5f697887a6b5c4d3e2f1a0b",
                        "name": "Beispielwerk Analytics GmbH",
                    },
                    "ownership": {
                        "percentage": 25.0,
                        "contribution": {"amount": 12500, "currency": "EUR"},
                    },
                    "as_of": "2025-03-15",
                }
            ]
        },
        "summary": {"total_current": 1},
    },
    "meta": {"request_credit_cost": 20},
}


@pytest.fixture
def mock_client():
    client = MagicMock(spec=Handelsregister)
    client.fetch_person.return_value = SAMPLE_PERSON_RESPONSE
    return client


@pytest.fixture
def person(mock_client):
    return Person(
        "Max Mustermann", "Beispielwerk Analytics GmbH", client=mock_client
    )


def test_person_basic_properties(person):
    assert person.entity_id == SAMPLE_PERSON_RESPONSE["entity_id"]
    assert person.name == "Max Mustermann"
    assert person.birth_date == "1985-07-14"
    assert person.home_city == "München"
    assert person.given_name == "Max"
    assert person.family_name == "Mustermann"
    assert person.canonical_name == "Mustermann, Max"
    assert "KI" in person.expertise
    assert person.linkedin.endswith("max-mustermann")


def test_person_roles(person):
    roles = person.handelsregister_roles
    assert len(roles) == 1
    assert person.current_handelsregister_roles == roles
    assert len(person.get_handelsregister_roles_by_label("MANAGING_DIRECTOR")) == 1


def test_person_shareholdings(person):
    shareholdings = person.shareholdings
    assert bool(shareholdings) is True
    assert len(shareholdings.current) == 1
    assert shareholdings.total_current == 1

    entry = shareholdings.current[0]
    assert entry.organization_name == "Beispielwerk Analytics GmbH"
    assert entry.percentage == 25.0
    assert entry.contribution_amount == 12500
    assert entry.contribution_currency == "EUR"
    assert entry.as_of == "2025-03-15"


def test_person_features_forwarded(mock_client):
    Person(
        "Max Mustermann",
        "Beispielwerk Analytics GmbH",
        client=mock_client,
        features=["shareholdings"],
    )
    mock_client.fetch_person.assert_called_once_with(
        person_q="Max Mustermann",
        organization_q="Beispielwerk Analytics GmbH",
        features=["shareholdings"],
    )


def test_person_fetch_error_propagates():
    mock_client = MagicMock(spec=Handelsregister)
    mock_client.fetch_person.side_effect = HandelsregisterError("boom")
    with pytest.raises(HandelsregisterError, match="boom"):
        Person("Max Mustermann", "Beispielwerk Analytics GmbH", client=mock_client)
