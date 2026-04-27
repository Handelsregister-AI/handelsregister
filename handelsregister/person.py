import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union

from .client import Handelsregister
from .exceptions import HandelsregisterError

logger = logging.getLogger(__name__)


@dataclass
class ShareholdingEntry:
    """A single shareholding entry as returned by the API."""
    organization: Dict[str, Any] = field(default_factory=dict)
    ownership: Dict[str, Any] = field(default_factory=dict)
    as_of: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def organization_name(self) -> str:
        return self.organization.get("name", "")

    @property
    def organization_entity_id(self) -> str:
        return self.organization.get("entity_id", "")

    @property
    def percentage(self) -> Optional[float]:
        """Ownership percentage (0-100 as returned by the API)."""
        return self.ownership.get("percentage")

    @property
    def contribution_amount(self) -> Optional[Union[int, float]]:
        contribution = self.ownership.get("contribution") or {}
        return contribution.get("amount") if isinstance(contribution, dict) else None

    @property
    def contribution_currency(self) -> str:
        contribution = self.ownership.get("contribution") or {}
        return contribution.get("currency", "") if isinstance(contribution, dict) else ""


@dataclass
class PersonShareholdings:
    """Container for a person's current/past shareholdings."""
    current: List[ShareholdingEntry] = field(default_factory=list)
    past: List[ShareholdingEntry] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.current or self.past)

    @property
    def total_current(self) -> Optional[int]:
        value = self.summary.get("total_current")
        return int(value) if isinstance(value, (int, float)) else value

    @property
    def all(self) -> List[ShareholdingEntry]:
        return self.current + self.past


class Person:
    """
    A class representing a person profile from the Handelsregister.ai API.

    Usage:
        from handelsregister import Person

        person = Person("Max Mustermann", "Beispielwerk Analytics GmbH")
        print(person.name)
        print(person.bio)
        for role in person.handelsregister_roles:
            print(role)
    """

    def __init__(
        self,
        person_q: str,
        organization_q: str,
        client: Optional[Handelsregister] = None,
        features: Optional[List[str]] = None,
        **kwargs,
    ):
        """
        Initialize a ``Person`` by fetching a profile from the API.

        :param person_q: Full name of the person (min. 2 characters).
        :param organization_q: Disambiguating organization context
                               (min. 2 characters).
        :param client: Optional preconfigured ``Handelsregister`` client.
        :param features: Optional feature list (currently only ``"shareholdings"``).
        :param kwargs: Additional query parameters passed through to the API.
        :raises HandelsregisterError: If the API call fails.
        """
        self._person_q = person_q
        self._organization_q = organization_q
        self._client = client or Handelsregister()
        self._features = features or []

        self._data = self._fetch_person_data(**kwargs)

    def _fetch_person_data(self, **kwargs) -> Dict[str, Any]:
        try:
            return self._client.fetch_person(
                person_q=self._person_q,
                organization_q=self._organization_q,
                features=self._features,
                **kwargs,
            )
        except HandelsregisterError as e:
            logger.error(
                "Error fetching person for person_q='%s', organization_q='%s': %s",
                self._person_q, self._organization_q, e,
            )
            raise

    # --------------------------------
    # Basic information
    # --------------------------------

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    @property
    def entity_id(self) -> str:
        return self._data.get("entity_id", "")

    @property
    def name(self) -> str:
        return self._data.get("name", "")

    @property
    def birth_date(self) -> str:
        return self._data.get("birth_date", "")

    @property
    def name_parts(self) -> Dict[str, Any]:
        return self._data.get("name_parts", {})

    @property
    def given_name(self) -> str:
        return self.name_parts.get("given", "")

    @property
    def family_name(self) -> str:
        return self.name_parts.get("family", "")

    @property
    def canonical_name(self) -> str:
        return self.name_parts.get("canonical_name", "")

    @property
    def previous_names(self) -> List[str]:
        value = self.name_parts.get("previous_names")
        return value if isinstance(value, list) else []

    @property
    def location(self) -> Dict[str, Any]:
        return self._data.get("location", {})

    @property
    def home_city(self) -> str:
        home = self.location.get("home") or {}
        if isinstance(home, dict):
            return home.get("city", "")
        return ""

    @property
    def bio(self) -> str:
        return self._data.get("bio", "")

    @property
    def expertise(self) -> List[str]:
        value = self._data.get("expertise") or []
        return list(value) if isinstance(value, list) else []

    # --------------------------------
    # Contact & profiles
    # --------------------------------

    @property
    def contact(self) -> Dict[str, Any]:
        return self._data.get("contact", {})

    @property
    def emails(self) -> List[Dict[str, Any]]:
        value = self.contact.get("emails") or []
        return list(value) if isinstance(value, list) else []

    @property
    def phones(self) -> List[Dict[str, Any]]:
        value = self.contact.get("phones") or []
        return list(value) if isinstance(value, list) else []

    @property
    def profiles(self) -> Dict[str, Any]:
        return self._data.get("profiles", {})

    @property
    def linkedin(self) -> str:
        return self.profiles.get("linkedin", "") or ""

    @property
    def github(self) -> str:
        return self.profiles.get("github", "") or ""

    # --------------------------------
    # Roles & affiliations
    # --------------------------------

    @property
    def handelsregister_roles(self) -> List[Dict[str, Any]]:
        value = self._data.get("handelsregister_roles") or []
        return list(value) if isinstance(value, list) else []

    def get_handelsregister_roles_by_label(self, label: str) -> List[Dict[str, Any]]:
        """Return Handelsregister roles whose ``label`` equals the given value."""
        return [r for r in self.handelsregister_roles if r.get("label") == label]

    @property
    def current_handelsregister_roles(self) -> List[Dict[str, Any]]:
        """Return roles that have no ``end_date`` set."""
        return [r for r in self.handelsregister_roles if not r.get("end_date")]

    @property
    def affiliations(self) -> List[Dict[str, Any]]:
        value = self._data.get("affiliations") or []
        return list(value) if isinstance(value, list) else []

    # --------------------------------
    # Shareholdings
    # --------------------------------

    @property
    def shareholdings(self) -> PersonShareholdings:
        """Return structured shareholdings information."""
        raw = self._data.get("shareholdings") or {}
        holdings = raw.get("holdings") or {}
        current = [
            self._build_shareholding_entry(entry)
            for entry in holdings.get("current", [])
            if isinstance(entry, dict)
        ]
        past = [
            self._build_shareholding_entry(entry)
            for entry in holdings.get("past", [])
            if isinstance(entry, dict)
        ]
        summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
        return PersonShareholdings(current=current, past=past, summary=summary, raw=raw)

    @staticmethod
    def _build_shareholding_entry(entry: Dict[str, Any]) -> ShareholdingEntry:
        return ShareholdingEntry(
            organization=entry.get("organization") or {},
            ownership=entry.get("ownership") or {},
            as_of=entry.get("as_of"),
            raw=entry,
        )

    # --------------------------------
    # Meta
    # --------------------------------

    @property
    def meta(self) -> Dict[str, Any]:
        return self._data.get("meta", {})

    @property
    def request_credit_cost(self) -> int:
        return int(self.meta.get("request_credit_cost", 0))

    # --------------------------------
    # Special methods
    # --------------------------------

    def __repr__(self) -> str:
        return f"Person(name='{self.name}', organization_q='{self._organization_q}')"

    def __str__(self) -> str:
        return self.canonical_name or self.name or self._person_q
