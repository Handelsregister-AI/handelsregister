"""Lossless convenience models for nested handelsregister.ai response data."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Mapping, Optional, Union


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    return [item for item in _list(value) if isinstance(item, str)]


def _filter_value(value: Any) -> Any:
    """Serialize nested filter builders and enums without losing raw values."""
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {key: _filter_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_filter_value(item) for item in value]
    return value


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
class CapitalValue:
    """Registered capital with an open-ended kind and optional reported change.

    ``change_amount`` is unsigned and is not necessarily the difference from
    the preceding capital value. It must not be interpreted as a signed delta.
    """

    amount: Optional[Union[int, float]] = None
    currency: Optional[str] = None
    kind: Optional[str] = None
    change_amount: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "CapitalValue":
        data = _dict(payload)
        return cls(
            amount=data.get("amount"),
            currency=data.get("currency"),
            kind=data.get("kind"),
            change_amount=(
                data["change_amount"]
                if isinstance(data.get("change_amount"), dict)
                else None
            ),
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class CapitalHistoryEntry:
    value: Optional[CapitalValue] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "CapitalHistoryEntry":
        data = _dict(payload)
        return cls(
            value=(
                CapitalValue.from_payload(data["value"])
                if isinstance(data.get("value"), dict)
                else None
            ),
            effective_from=data.get("effective_from"),
            effective_to=data.get("effective_to"),
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class CapitalInfo:
    """Current registered capital and its history, included in the base lookup."""

    current: Optional[CapitalValue] = None
    history: List[CapitalHistoryEntry] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "CapitalInfo":
        data = _dict(payload)
        return cls(
            current=(
                CapitalValue.from_payload(data["current"])
                if isinstance(data.get("current"), dict)
                else None
            ),
            history=[
                CapitalHistoryEntry.from_payload(item)
                for item in _list(data.get("history"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    def __bool__(self) -> bool:
        return self.current is not None or bool(self.history)

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class FinancialProvenance:
    """All-tier source metadata for financial years and activity statements."""

    statement_type: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    exempt_subsidiary: Optional[bool] = None
    parent_organization: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "FinancialProvenance":
        data = _dict(payload)
        return cls(
            statement_type=data.get("statement_type"),
            period_start=data.get("period_start"),
            period_end=data.get("period_end"),
            exempt_subsidiary=data.get("exempt_subsidiary"),
            parent_organization=(
                data["parent_organization"]
                if isinstance(data.get("parent_organization"), dict)
                else None
            ),
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw

    def __bool__(self) -> bool:
        return bool(self.raw)


@dataclass
class FinancialAccount:
    """One account in a financial tree, preserving labels and unknown fields."""

    name: Any = field(default_factory=dict)
    value: Any = None
    children: List["FinancialAccount"] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "FinancialAccount":
        data = _dict(payload)
        return cls(
            name=data.get("name", {}),
            value=data.get("value"),
            children=cls.from_accounts(data.get("children")),
            raw=data,
        )

    @classmethod
    def from_accounts(cls, payload: Any) -> List["FinancialAccount"]:
        """Read documented lists and older dictionary account layouts."""
        if isinstance(payload, dict):
            if "name" in payload:
                return [cls.from_payload(payload)]
            return [
                cls.from_payload({"name": name, "value": value})
                for name, value in payload.items()
            ]
        return [
            cls.from_payload(item) for item in _list(payload) if isinstance(item, dict)
        ]

    def name_text(self, language: str = "en") -> str:
        return (
            localized_text(self.name, language)
            or _dict(self.name).get("in_report")
            or ""
        )

    def walk(self) -> Iterator["FinancialAccount"]:
        """Yield this node and all its descendants in report order."""
        yield self
        for child in self.children:
            yield from child.walk()

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ActivityStatement:
    """Max-plan accounts for one regulated activity (§ 6b EnWG)."""

    activity: Dict[str, Any] = field(default_factory=dict)
    balance_sheet_accounts: Any = field(default_factory=list)
    profit_and_loss_accounts: Any = field(default_factory=list)
    provenance: FinancialProvenance = field(default_factory=FinancialProvenance)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ActivityStatement":
        data = _dict(payload)
        return cls(
            activity=_dict(data.get("activity")),
            balance_sheet_accounts=data.get("balance_sheet_accounts", []),
            profit_and_loss_accounts=data.get("profit_and_loss_accounts", []),
            provenance=FinancialProvenance.from_payload(data.get("_provenance")),
            raw=data,
        )

    def name_text(self, language: str = "en") -> str:
        return (
            localized_text(self.activity.get("name"), language)
            or self.name_in_report
            or ""
        )

    @property
    def name_in_report(self) -> Optional[str]:
        """Original report label, which can differ between balance sheet and P&L."""
        name = self.activity.get("name")
        return (
            name.get("in_report")
            if isinstance(name, dict)
            else name
            if isinstance(name, str)
            else None
        )

    @property
    def balance_sheet_entries(self) -> List[FinancialAccount]:
        return FinancialAccount.from_accounts(self.balance_sheet_accounts)

    @property
    def profit_and_loss_entries(self) -> List[FinancialAccount]:
        return FinancialAccount.from_accounts(self.profit_and_loss_accounts)

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class FinancialStatement:
    """Lossless financial year with metrics, accounts, and source metadata.

    The API's plan-dependent metrics remain available in ``metrics`` without
    imposing a closed set of metric names.
    """

    year: Optional[int] = None
    balance_sheet_accounts: Any = field(default_factory=list)
    profit_and_loss_accounts: Any = field(default_factory=list)
    provenance: FinancialProvenance = field(default_factory=FinancialProvenance)
    activity_statements: List[ActivityStatement] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "FinancialStatement":
        data = _dict(payload)
        return cls(
            year=data.get("year"),
            balance_sheet_accounts=data.get("balance_sheet_accounts", []),
            profit_and_loss_accounts=data.get("profit_and_loss_accounts", []),
            provenance=FinancialProvenance.from_payload(data.get("_provenance")),
            activity_statements=[
                ActivityStatement.from_payload(item)
                for item in _list(data.get("activity_statements"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            key: value
            for key, value in self.raw.items()
            if not key.startswith("_")
            and key
            not in {
                "year",
                "balance_sheet_accounts",
                "profit_and_loss_accounts",
                "activity_statements",
            }
        }

    @property
    def balance_sheet_entries(self) -> List[FinancialAccount]:
        return FinancialAccount.from_accounts(self.balance_sheet_accounts)

    @property
    def profit_and_loss_entries(self) -> List[FinancialAccount]:
        return FinancialAccount.from_accounts(self.profit_and_loss_accounts)

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


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
class FilterCondition:
    """Advanced search condition supporting comparison and existence operators."""

    gte: Any = None
    lte: Any = None
    gt: Any = None
    lt: Any = None
    eq: Any = None
    exists: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if value is not None:
                result[key] = _filter_value(value)
        return result


@dataclass
class LocationCoordinates:
    """WGS84 center point for an organization radius search."""

    lat: float
    lon: float

    def to_dict(self) -> Dict[str, float]:
        return {"lat": self.lat, "lon": self.lon}


@dataclass
class OwnershipFilters:
    """Pro/Max ownership and succession filters."""

    structure: Any = None
    owner_managed: Any = None
    likely_family_owned: Any = None
    largest_share_ratio: Any = None
    oldest_owner_birth_date: Any = None
    youngest_owner_birth_date: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            key: _filter_value(value)
            for key, value in self.__dict__.items()
            if value is not None
        }


@dataclass
class ExecutiveFilters:
    """Pro/Max active managing-director age filters."""

    md_oldest_birth_date: Any = None
    md_youngest_birth_date: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            key: _filter_value(value)
            for key, value in self.__dict__.items()
            if value is not None
        }


@dataclass
class LifecycleFilters:
    """Pro/Max insolvency lifecycle filters."""

    insolvency_active: Any = None
    insolvency_status: Any = None
    insolvency_opened_date: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            key: _filter_value(value)
            for key, value in self.__dict__.items()
            if value is not None
        }


@dataclass
class SearchFilters:
    """Typed builder covering every documented organization-search filter."""

    registration_date_from: Optional[str] = None
    registration_date_to: Optional[str] = None
    legal_form_code: Any = None
    industry_code: Any = None
    industry_scheme: Optional[str] = None
    active: Optional[bool] = None
    status: Any = None
    legal_form_liability_type: Any = None

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

    ownership_filters: Any = None
    executive_filters: Any = None
    lifecycle_filters: Any = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if value is None:
                continue
            data[key] = _filter_value(value)
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


@dataclass
class NetworkNodeReference:
    """Compact node reference embedded in a network connection."""

    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        return self.raw.get("node_id", "")

    @property
    def type(self) -> str:
        return self.raw.get("type", "")

    @property
    def name(self) -> str:
        return self.raw.get("name", "")

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class NetworkNode(NetworkNodeReference):
    """One organization or person in an organization relationship graph."""

    @property
    def entity_id(self) -> str:
        return self.raw.get("entity_id", "")

    @property
    def depth(self) -> int:
        value = self.raw.get("depth", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @property
    def is_root(self) -> bool:
        return self.raw.get("is_root") is True


@dataclass
class NetworkConnection:
    """A typed, lossless relationship between two network nodes."""

    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def source(self) -> NetworkNodeReference:
        return NetworkNodeReference(raw=_dict(self.raw.get("source")))

    @property
    def target(self) -> NetworkNodeReference:
        return NetworkNodeReference(raw=_dict(self.raw.get("target")))

    @property
    def connection_type(self) -> str:
        return self.raw.get("connection_type", "")

    @property
    def label(self) -> str:
        return self.raw.get("label", "")

    @property
    def role(self) -> Dict[str, Any]:
        return _dict(self.raw.get("role"))

    def role_name(self, language: str = "en") -> str:
        return localized_text(self.role, language)

    @property
    def start_date(self) -> Optional[str]:
        return self.raw.get("start_date")

    @property
    def end_date(self) -> Optional[str]:
        return self.raw.get("end_date")

    @property
    def is_current(self) -> Optional[bool]:
        return self.raw.get("is_current")

    @property
    def depth(self) -> int:
        value = self.raw.get("depth", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class OrganizationNetwork:
    """Relationship graph returned by the ``network`` organization feature."""

    depth: int = 0
    nodes: List[NetworkNode] = field(default_factory=list)
    connections: List[NetworkConnection] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "OrganizationNetwork":
        data = _dict(payload)
        depth = data.get("depth", 0)
        try:
            depth = int(depth)
        except (TypeError, ValueError):
            depth = 0
        return cls(
            depth=depth,
            nodes=[
                NetworkNode(raw=item)
                for item in _list(data.get("nodes"))
                if isinstance(item, dict)
            ],
            connections=[
                NetworkConnection(raw=item)
                for item in _list(data.get("connections"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    def __bool__(self) -> bool:
        return bool(self.nodes or self.connections)

    @property
    def root(self) -> Optional[NetworkNode]:
        for node in self.nodes:
            if node.is_root:
                return node
        return None

    def as_dict(self) -> Dict[str, Any]:
        return self.raw
