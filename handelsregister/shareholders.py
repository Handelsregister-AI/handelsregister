"""Lossless models for the Max-only ``shareholders_deep`` feature.

Percentages are on a 0–100 scale. Entries represent document rows, so the same
holder can occur more than once. Joint ownership belongs to the community;
its percentage must not be assigned to the individual members.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .models import _dict, _list


@dataclass
class ShareholderAmount:
    """A nominal amount or share capital, using the API's ``value`` key."""

    value: Optional[Union[int, float]] = None
    currency: Optional[str] = None
    basis: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareholderAmount":
        data = _dict(payload)
        return cls(data.get("value"), data.get("currency"), data.get("basis"), data)

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholderRecord:
    """Source document and date; register records can have a null date."""

    date: Optional[str] = None
    source: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareholderRecord":
        data = _dict(payload)
        return cls(data.get("date"), data.get("source"), data)

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholderHolder:
    """An organization, person, joint community, or compact change reference.

    Unknown enum strings and null fields are preserved. ``members`` are the
    co-owners of a JOINT holder, without inferred individual percentages.
    """

    entity_id: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    legal_form: Optional[str] = None
    status: Optional[str] = None
    registration: Optional[Dict[str, Any]] = None
    registration_text: Optional[str] = None
    birth_date: Optional[str] = None
    members: List["ShareholderHolder"] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareholderHolder":
        data = _dict(payload)
        return cls(
            entity_id=data.get("entity_id"),
            type=data.get("type"),
            name=data.get("name"),
            city=data.get("city"),
            country=data.get("country"),
            legal_form=data.get("legal_form"),
            status=data.get("status"),
            registration=(
                data["registration"]
                if isinstance(data.get("registration"), dict)
                else None
            ),
            registration_text=data.get("registration_text"),
            birth_date=data.get("birth_date"),
            members=[
                cls.from_payload(item)
                for item in _list(data.get("members"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareRange:
    """Consecutive share numbers with the same nominal value per share."""

    from_number: Optional[int] = None
    to_number: Optional[int] = None
    count: Optional[int] = None
    nominal_value: Optional[ShareholderAmount] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareRange":
        data = _dict(payload)
        return cls(
            from_number=data.get("from"),
            to_number=data.get("to"),
            count=data.get("count"),
            nominal_value=(
                ShareholderAmount.from_payload(data["nominal_value"])
                if isinstance(data.get("nominal_value"), dict)
                else None
            ),
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholderOwnership:
    """Direct capital ownership, including the individual share ranges."""

    percentage: Optional[float] = None
    percentage_basis: Optional[str] = None
    nominal_amount: Optional[ShareholderAmount] = None
    share_count: Optional[int] = None
    share_ranges: List[ShareRange] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareholderOwnership":
        data = _dict(payload)
        return cls(
            percentage=data.get("percentage"),
            percentage_basis=data.get("percentage_basis"),
            nominal_amount=(
                ShareholderAmount.from_payload(data["nominal_amount"])
                if isinstance(data.get("nominal_amount"), dict)
                else None
            ),
            share_count=data.get("share_count"),
            share_ranges=[
                ShareRange.from_payload(item)
                for item in _list(data.get("share_ranges"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class DeepShareholderEntry:
    """One document row, with ownership and continuously recorded tenure."""

    holder: ShareholderHolder = field(default_factory=ShareholderHolder)
    role: Optional[str] = None
    ownership: ShareholderOwnership = field(default_factory=ShareholderOwnership)
    since: Optional[str] = None
    since_basis: Optional[str] = None
    until: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "DeepShareholderEntry":
        data = _dict(payload)
        return cls(
            holder=ShareholderHolder.from_payload(data.get("holder")),
            role=data.get("role"),
            ownership=ShareholderOwnership.from_payload(data.get("ownership")),
            since=data.get("since"),
            since_basis=data.get("since_basis"),
            until=data.get("until"),
            raw=data,
        )

    @property
    def display_name(self) -> str:
        return self.holder.name or "Unknown shareholder"

    @property
    def percentage(self) -> Optional[float]:
        """Direct capital ownership as a percentage (0–100)."""
        return self.ownership.percentage

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class DeepShareholderHistorySnapshot:
    """A previous document, preserving printed names and row order."""

    record: ShareholderRecord = field(default_factory=ShareholderRecord)
    share_capital: Optional[ShareholderAmount] = None
    entries: List[DeepShareholderEntry] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "DeepShareholderHistorySnapshot":
        data = _dict(payload)
        return cls(
            record=ShareholderRecord.from_payload(data.get("record")),
            share_capital=(
                ShareholderAmount.from_payload(data["share_capital"])
                if isinstance(data.get("share_capital"), dict)
                else None
            ),
            entries=[
                DeepShareholderEntry.from_payload(item)
                for item in _list(data.get("entries"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholderChange:
    """A joined/left holder or a change in their aggregate percentage."""

    holder: ShareholderHolder = field(default_factory=ShareholderHolder)
    percentage: Optional[float] = None
    percentage_before: Optional[float] = None
    percentage_after: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareholderChange":
        data = _dict(payload)
        return cls(
            holder=ShareholderHolder.from_payload(data.get("holder")),
            percentage=data.get("percentage"),
            percentage_before=data.get("percentage_before"),
            percentage_after=data.get("percentage_after"),
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholderChanges:
    """Changes against the previous list, aggregated by holder by the API."""

    compared_to: Optional[str] = None
    joined: List[ShareholderChange] = field(default_factory=list)
    left: List[ShareholderChange] = field(default_factory=list)
    changed: List[ShareholderChange] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareholderChanges":
        data = _dict(payload)
        return cls(
            compared_to=data.get("compared_to"),
            joined=[
                ShareholderChange.from_payload(item)
                for item in _list(data.get("joined"))
                if isinstance(item, dict)
            ],
            left=[
                ShareholderChange.from_payload(item)
                for item in _list(data.get("left"))
                if isinstance(item, dict)
            ],
            changed=[
                ShareholderChange.from_payload(item)
                for item in _list(data.get("changed"))
                if isinstance(item, dict)
            ],
            raw=data,
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholdersDeep:
    """Current deep shareholders, earlier documents, and latest changes.

    Missing or null feature blocks produce an empty view. The original
    distinction remains available through ``Company.data``. The service omits
    this feature for plans other than Max; no client-side plan check is added.
    """

    record: ShareholderRecord = field(default_factory=ShareholderRecord)
    share_capital: Optional[ShareholderAmount] = None
    entries: List[DeepShareholderEntry] = field(default_factory=list)
    history: List[DeepShareholderHistorySnapshot] = field(default_factory=list)
    changes: Optional[ShareholderChanges] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ShareholdersDeep":
        data = _dict(payload)
        snapshot = DeepShareholderHistorySnapshot.from_payload(data)
        return cls(
            record=snapshot.record,
            share_capital=snapshot.share_capital,
            entries=snapshot.entries,
            history=[
                DeepShareholderHistorySnapshot.from_payload(item)
                for item in _list(data.get("history"))
                if isinstance(item, dict)
            ],
            changes=(
                ShareholderChanges.from_payload(data["changes"])
                if isinstance(data.get("changes"), dict)
                else None
            ),
            raw=data,
        )

    def __bool__(self) -> bool:
        return bool(self.entries)

    def as_dict(self) -> Dict[str, Any]:
        return self.raw
