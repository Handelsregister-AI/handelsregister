"""Lossless convenience models for nested handelsregister.ai response data."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    return [item for item in _list(value) if isinstance(item, str)]


def localized_text(value: Any, language: str = "en") -> str:
    """Return a best-effort localized label without discarding the raw value."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    preferred = value.get(language)
    if isinstance(preferred, str):
        return preferred
    if isinstance(preferred, dict):
        return preferred.get("long") or preferred.get("short") or ""
    for candidate in ("en", "de"):
        item = value.get(candidate)
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            text = item.get("long") or item.get("short")
            if text:
                return text
    return value.get("long") or value.get("short") or ""


@dataclass
class RangeFilter:
    """Inclusive ``gte``/``lte`` bounds used by numeric search filters."""

    gte: Optional[float] = None
    lte: Optional[float] = None

    def to_dict(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        if self.gte is not None:
            result["gte"] = self.gte
        if self.lte is not None:
            result["lte"] = self.lte
        return result


@dataclass
class SearchFilters:
    """Typed builder covering every documented organization-search filter."""

    registration_date_from: Optional[str] = None
    registration_date_to: Optional[str] = None
    legal_form_code: Any = None
    industry_code: Any = None
    industry_scheme: Optional[str] = None
    active: Optional[bool] = None

    postal_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    location_coordinates: Any = None
    location_max_distance_km: Optional[float] = None

    registration_type: Any = None
    registration_authority_name: Optional[str] = None
    registration_number: Optional[str] = None

    company_size_category: Optional[str] = None
    emp_count: Any = None

    bs_assets_total: Any = None
    bs_equity_total: Any = None
    bs_liabilities_total: Any = None
    bs_cash_and_equivalents: Any = None
    bs_cash_to_liabilities: Any = None
    bs_equity_ratio: Any = None
    bs_debt_to_assets: Any = None

    pl_revenue: Any = None
    pl_net_income: Any = None
    pl_ebit: Any = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if value is None:
                continue
            if isinstance(value, RangeFilter):
                value = value.to_dict()
            data[key] = value
        return data


@dataclass
class RepresentationSchemeHistoryEntry:
    """One historical representation-scheme value and its effective interval."""

    value: List[str] = field(default_factory=list)
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "RepresentationSchemeHistoryEntry":
        data = _dict(payload)
        return cls(
            value=_strings(data.get("value")),
            effective_from=data.get("effective_from"),
            effective_to=data.get("effective_to"),
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class RepresentationScheme:
    """
    Organization- or role-level representation rules.

    Active records use ``current``. Past related-person records can use
    ``latest`` instead. ``active`` normalizes both shapes.
    """

    current: List[str] = field(default_factory=list)
    latest: List[str] = field(default_factory=list)
    history: List[RepresentationSchemeHistoryEntry] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "RepresentationScheme":
        data = _dict(payload)
        history = [
            RepresentationSchemeHistoryEntry.from_payload(item)
            for item in _list(data.get("history"))
            if isinstance(item, dict)
        ]
        return cls(
            current=_strings(data.get("current")),
            latest=_strings(data.get("latest")),
            history=history,
            raw=data,
        )

    def __bool__(self) -> bool:
        return bool(self.current or self.latest or self.history)

    @property
    def active(self) -> List[str]:
        return self.current or self.latest

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class RelatedPerson:
    """Typed view over one entry in ``related_persons``."""

    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def entity_id(self) -> str:
        return self.raw.get("entity_id", "")

    @property
    def name(self) -> Any:
        return self.raw.get("name", "")

    @property
    def display_name(self) -> str:
        name = self.name
        if isinstance(name, str):
            return name
        if isinstance(name, dict):
            return (
                name.get("canonical_name")
                or " ".join(
                    part
                    for part in (name.get("given"), name.get("family"))
                    if part
                )
            )
        parts = _dict(self.raw.get("name_parts"))
        return (
            parts.get("canonical_name")
            or " ".join(
                part for part in (parts.get("given"), parts.get("family")) if part
            )
        )

    @property
    def label(self) -> str:
        role = _dict(self.raw.get("role"))
        return self.raw.get("label") or role.get("label") or ""

    @property
    def role(self) -> Dict[str, Any]:
        return _dict(self.raw.get("role"))

    @property
    def role_name(self) -> str:
        return localized_text(self.role)

    @property
    def start_date(self) -> Optional[str]:
        return self.raw.get("start_date")

    @property
    def end_date(self) -> Optional[str]:
        return self.raw.get("end_date")

    @property
    def organization_representation_scheme(self) -> RepresentationScheme:
        return RepresentationScheme.from_payload(
            self.raw.get("organization_representation_scheme")
        )

    @property
    def role_representation_scheme(self) -> RepresentationScheme:
        return RepresentationScheme.from_payload(
            self.raw.get("role_representation_scheme")
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class RelatedPersons:
    current: List[RelatedPerson] = field(default_factory=list)
    past: List[RelatedPerson] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "RelatedPersons":
        data = _dict(payload)
        return cls(
            current=[
                RelatedPerson(raw=item)
                for item in _list(data.get("current"))
                if isinstance(item, dict)
            ],
            past=[
                RelatedPerson(raw=item)
                for item in _list(data.get("past"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    @property
    def all(self) -> List[RelatedPerson]:
        return self.current + self.past

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class MACounterparty:
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def entity_id(self) -> str:
        return self.raw.get("entity_id", "")

    @property
    def name(self) -> str:
        return self.raw.get("name", "")

    @property
    def seat(self) -> str:
        return self.raw.get("seat", "")

    @property
    def registration(self) -> Dict[str, Any]:
        return _dict(self.raw.get("registration"))

    @property
    def role(self) -> Dict[str, Any]:
        return _dict(self.raw.get("role"))

    @property
    def role_label(self) -> str:
        return self.role.get("label", "")

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class MATransaction:
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    @property
    def headline(self) -> Dict[str, Any]:
        return _dict(self.raw.get("headline"))

    def headline_text(self, language: str = "en") -> str:
        return localized_text(self.headline, language)

    @property
    def type(self) -> Dict[str, Any]:
        return _dict(self.raw.get("type"))

    @property
    def category(self) -> str:
        return self.type.get("category", "")

    @property
    def event_type(self) -> str:
        return self.type.get("event_type", "")

    @property
    def kind(self) -> Dict[str, Any]:
        return _dict(self.raw.get("kind"))

    @property
    def kind_label(self) -> str:
        return self.kind.get("label", "")

    @property
    def role(self) -> Dict[str, Any]:
        return _dict(self.raw.get("role"))

    @property
    def role_label(self) -> str:
        return self.role.get("label", "")

    @property
    def phase(self) -> str:
        return self.raw.get("phase", "")

    @property
    def date(self) -> Optional[str]:
        return self.raw.get("date")

    @property
    def dates(self) -> Dict[str, Any]:
        return _dict(self.raw.get("dates"))

    @property
    def counterparties(self) -> List[MACounterparty]:
        return [
            MACounterparty(raw=item)
            for item in _list(self.raw.get("counterparties"))
            if isinstance(item, dict)
        ]

    @property
    def description(self) -> str:
        return self.raw.get("description", "")

    @property
    def register_entries(self) -> List[Dict[str, Any]]:
        return [
            item
            for item in _list(self.raw.get("register_entries"))
            if isinstance(item, dict)
        ]

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class MAControlRelationship:
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def counterparty(self) -> MACounterparty:
        return MACounterparty(raw=_dict(self.raw.get("counterparty")))

    @property
    def via(self) -> Dict[str, Any]:
        return _dict(self.raw.get("via"))

    @property
    def loss_absorption_obligation(self) -> Optional[bool]:
        return self.raw.get("loss_absorption_obligation")

    @property
    def since(self) -> Optional[str]:
        return self.raw.get("since")

    @property
    def transaction_ids(self) -> List[str]:
        return [
            value
            for value in _list(self.raw.get("transaction_ids"))
            if isinstance(value, str)
        ]

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class MAControl:
    controlled_by: List[MAControlRelationship] = field(default_factory=list)
    controls: List[MAControlRelationship] = field(default_factory=list)
    former: List[MAControlRelationship] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "MAControl":
        data = _dict(payload)

        def relationships(key: str) -> List[MAControlRelationship]:
            return [
                MAControlRelationship(raw=item)
                for item in _list(data.get(key))
                if isinstance(item, dict)
            ]

        return cls(
            controlled_by=relationships("controlled_by"),
            controls=relationships("controls"),
            former=relationships("former"),
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class MergersAndAcquisitions:
    transactions: List[MATransaction] = field(default_factory=list)
    succession: Any = None
    control: MAControl = field(default_factory=MAControl)
    summary: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "MergersAndAcquisitions":
        data = _dict(payload)
        return cls(
            transactions=[
                MATransaction(raw=item)
                for item in _list(data.get("transactions"))
                if isinstance(item, dict)
            ],
            succession=data.get("succession"),
            control=MAControl.from_payload(data.get("control")),
            summary=_dict(data.get("summary")),
            raw=data,
        )

    def __bool__(self) -> bool:
        return bool(
            self.transactions
            or self.succession
            or self.control.controlled_by
            or self.control.controls
            or self.control.former
        )

    @property
    def total_transactions(self) -> int:
        value = self.summary.get("total_transactions", len(self.transactions))
        try:
            return int(value)
        except (TypeError, ValueError):
            return len(self.transactions)

    @property
    def first_date(self) -> Optional[str]:
        return self.summary.get("first_date")

    @property
    def last_date(self) -> Optional[str]:
        return self.summary.get("last_date")

    @property
    def by_category(self) -> Dict[str, Any]:
        return _dict(self.summary.get("by_category"))

    def as_dict(self) -> Dict[str, Any]:
        return self.raw
