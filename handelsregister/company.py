import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, Tuple, TypeVar, Generic, Callable
from datetime import datetime

from .client import Handelsregister
from .exceptions import HandelsregisterError

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class UBOEntry:
    """A single ultimate beneficial owner entry."""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw.get("name") or self.raw.get("display_name") or ""

    @property
    def percentage(self) -> Optional[float]:
        """Ownership percentage as returned by the API (0-100)."""
        value = self.raw.get("percentage")
        if value is None:
            value = self.raw.get("ownership_percentage")
        if value is None:
            ownership = self.raw.get("ownership") or {}
            if isinstance(ownership, dict):
                value = ownership.get("percentage")
        return value

    @property
    def type(self) -> str:
        return self.raw.get("type", "")

    @property
    def resolved(self) -> Optional[bool]:
        return self.raw.get("resolved")


@dataclass
class UBOInfo:
    """
    Structured ultimate beneficial owners block.

    Mirrors the ``ubos`` feature response, which typically contains resolved
    and unresolved owners plus coverage metadata.
    """
    resolved: List[UBOEntry] = field(default_factory=list)
    unresolved: List[UBOEntry] = field(default_factory=list)
    coverage: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.resolved or self.unresolved)

    @property
    def all(self) -> List[UBOEntry]:
        return self.resolved + self.unresolved

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholdingEntry:
    """A single shareholding (investment) that the company holds in another entity."""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def organization(self) -> Dict[str, Any]:
        value = self.raw.get("organization") or {}
        return value if isinstance(value, dict) else {}

    @property
    def organization_name(self) -> str:
        return self.organization.get("name", "")

    @property
    def organization_entity_id(self) -> str:
        return self.organization.get("entity_id", "")

    @property
    def ownership(self) -> Dict[str, Any]:
        value = self.raw.get("ownership") or {}
        return value if isinstance(value, dict) else {}

    @property
    def percentage(self) -> Optional[float]:
        return self.ownership.get("percentage")

    @property
    def contribution_amount(self) -> Optional[Union[int, float]]:
        contribution = self.ownership.get("contribution") or {}
        return contribution.get("amount") if isinstance(contribution, dict) else None

    @property
    def contribution_currency(self) -> str:
        contribution = self.ownership.get("contribution") or {}
        return contribution.get("currency", "") if isinstance(contribution, dict) else ""

    @property
    def as_of(self) -> Optional[str]:
        return self.raw.get("as_of")


@dataclass
class ShareholdingsInfo:
    """Container for a company's outbound shareholdings."""
    current: List[ShareholdingEntry] = field(default_factory=list)
    past: List[ShareholdingEntry] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.current or self.past)

    @property
    def all(self) -> List[ShareholdingEntry]:
        return self.current + self.past

    def as_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class ShareholderEntry:
    """
    Structured representation of a single shareholder entry returned by the API.
    """
    shareholder: Dict[str, Any]
    contribution: Dict[str, Any]
    contribution_ratio: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def display_name(self) -> str:
        """Return a best-effort human readable name."""
        entity_name = self.shareholder.get("entity_name")
        if entity_name:
            return entity_name
        
        first_name = self.shareholder.get("first_name")
        last_name = self.shareholder.get("last_name")
        if first_name or last_name:
            return " ".join(filter(None, [first_name, last_name])).strip()
        
        return self.shareholder.get("name") or "Unknown shareholder"
    
    @property
    def address(self) -> str:
        """Return the registered address of the shareholder if available."""
        return self.shareholder.get("address", "")
    
    @property
    def contribution_amount(self) -> Optional[Union[int, float]]:
        """Return the contributed capital amount."""
        return self.contribution.get("amount")
    
    @property
    def contribution_currency(self) -> str:
        """Return the contributed capital currency."""
        return self.contribution.get("currency", "")
    
    @property
    def percentage(self) -> Optional[float]:
        """Return the ownership share expressed as a ratio (0-1)."""
        return self.contribution_ratio


@dataclass
class ShareholderInfo:
    """
    Container for shareholder information including total capital and individual entries.
    """
    entries: List[ShareholderEntry] = field(default_factory=list)
    total_capital: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    
    def __bool__(self) -> bool:
        return bool(self.entries or self.total_capital)
    
    @property
    def total_capital_amount(self) -> Optional[Union[int, float]]:
        """Return the total capital amount if provided."""
        if isinstance(self.total_capital, dict):
            return self.total_capital.get("amount")
        return None
    
    @property
    def total_capital_currency(self) -> str:
        """Return the total capital currency if provided."""
        if isinstance(self.total_capital, dict):
            return self.total_capital.get("currency", "")
        return ""
    
    def as_dict(self) -> Dict[str, Any]:
        """Expose the original API payload."""
        return self.raw


class Company:
    """
    A class representing a company from the Handelsregister.ai API.
    
    Provides convenient access to company information through attributes.
    
    Usage:
        from handelsregister import Company
        
        company = Company("OroraTech GmbH aus München")
        print(company.name)  # Access the company name
        print(company.entity_id)  # Access the entity ID
        print(company.registration_number)  # Access the registration number
        
        # Access financial KPIs for a specific year
        revenue_2022 = company.get_financial_kpi_for_year(2022, "revenue")
        
        # Access all financial years available
        financial_years = company.financial_years
        
        # Get balance sheet data for a specific year
        balance_sheet_2022 = company.get_balance_sheet_for_year(2022)
        
        # Get current managing directors
        managing_directors = company.get_related_persons_by_role("MANAGING_DIRECTOR", current_only=True)
    """
    
    def __init__(
        self,
        query: str,
        client: Optional[Handelsregister] = None,
        features: Optional[List[str]] = None,
        ai_search: Optional[str] = "off",  # Changed from "on-default" to "off"
        realtime_mode: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize a Company instance by fetching data from Handelsregister.ai.

        :param query: A search query for the company (e.g. "OroraTech GmbH aus München").
        :param client: An optional Handelsregister client instance. If None, a new client is created.
        :param features: A list of desired feature flags to include in the request.
                         Commonly used features include:
                         - "related_persons"
                         - "publications"
                         - "financial_kpi"
                         - "balance_sheet_accounts"
                         - "profit_and_loss_account"
                         - "annual_financial_statements"
                         - "annual_financial_statements__html"
                         - "insolvency_publications"
                         - "news"
                         - "website_content"
                         - "shareholders"
                         - "ubos"
                         - "shareholdings"
        :param ai_search: Whether to use AI-based search, defaults to "off".
        :param realtime_mode: Pass ``"handelsregister-default"`` to force a live
                              Handelsregister lookup (+10 credits).
        :param kwargs: Additional parameters to pass to fetch_organization.
        :raises HandelsregisterError: If there was an error fetching the company data.
        """
        self._query = query
        self._client = client or Handelsregister()
        self._features = features or []
        self._ai_search = ai_search
        self._realtime_mode = realtime_mode

        # Fetch company data
        self._data = self._fetch_company_data(query, **kwargs)

    def _fetch_company_data(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch company data from the Handelsregister.ai API.

        :param query: The search query for the company.
        :param kwargs: Additional parameters to pass to fetch_organization.
        :return: The company data as a dictionary.
        :raises HandelsregisterError: If there was an error fetching the company data.
        """
        try:
            return self._client.fetch_organization(
                q=query,
                features=self._features,
                ai_search=self._ai_search,
                realtime_mode=self._realtime_mode,
                **kwargs
            )
        except HandelsregisterError as e:
            logger.error(f"Error fetching company data for query '{query}': {e}")
            raise
    
    # --------------------------------
    # Basic company information
    # --------------------------------
    
    @property
    def data(self) -> Dict[str, Any]:
        """Get the complete company data dictionary."""
        return self._data
    
    @property
    def name(self) -> str:
        """Get the company name."""
        return self._data.get("name", "")
    
    @property
    def entity_id(self) -> str:
        """Get the entity ID."""
        return self._data.get("entity_id", "")
    
    @property
    def status(self) -> str:
        """Get the company status (e.g., 'ACTIVE')."""
        return self._data.get("status", "")
    
    @property
    def is_active(self) -> bool:
        """Check if the company is active."""
        return self._data.get("status", "").upper() == "ACTIVE"
    
    @property
    def purpose(self) -> str:
        """Get the company purpose."""
        return self._data.get("purpose", "")
    
    # --------------------------------
    # Registration information
    # --------------------------------
    
    @property
    def registration(self) -> Dict[str, Any]:
        """Get the full registration information dictionary."""
        return self._data.get("registration", {})
    
    @property
    def registration_number(self) -> str:
        """Get the registration number."""
        return self.registration.get("register_number", "")
    
    @property
    def registration_court(self) -> str:
        """Get the registration court."""
        return self.registration.get("court", "")
    
    @property
    def registration_type(self) -> str:
        """Get the registration type (e.g., 'HRB')."""
        return self.registration.get("register_type", "")
    
    @property
    def registration_date(self) -> str:
        """Get the registration date."""
        # First try the registration date from the registration dict
        date = (
            self.registration.get("registered_at")
            or self.registration.get("register_date")
            or self._data.get("registration_date")
            or self._data.get("register_date", "")
        )
        return date
    
    # --------------------------------
    # Legal information
    # --------------------------------
    
    @property
    def legal_form(self) -> Dict[str, Any]:
        """Get the legal form dictionary."""
        return self._data.get("legal_form", {})
    
    @property
    def legal_form_name(self) -> str:
        """Get the legal form name."""
        if isinstance(self.legal_form, dict):
            return self.legal_form.get("name", "")
        return str(self.legal_form)
    
    @property
    def capital(self) -> Union[str, Dict[str, Any]]:
        """Get the company capital information."""
        return self._data.get("capital", "")
    
    # --------------------------------
    # Address and contact information
    # --------------------------------
    
    @property
    def address(self) -> Dict[str, Any]:
        """Get the company address dictionary."""
        return self._data.get("address", {})
    
    @property
    def formatted_address(self) -> str:
        """Get a formatted string representation of the company address."""
        addr = self.address
        components = []
        
        street = addr.get("street", "")
        house_number = addr.get("house_number", "")
        if street and house_number:
            components.append(f"{street} {house_number}")
        elif street:
            components.append(street)
        
        postal_code = addr.get("postal_code", "")
        city = addr.get("city", "")
        if postal_code and city:
            components.append(f"{postal_code} {city}")
        elif city:
            components.append(city)
        
        country = addr.get("country", addr.get("country_code", ""))
        if country:
            components.append(country)
        
        return ", ".join(components)
    
    @property
    def coordinates(self) -> Tuple[float, float]:
        """Get the latitude and longitude coordinates for the company address."""
        coords = self.address.get("coordinates", {})
        lat = coords.get("latitude", coords.get("lat"))
        lng = coords.get("longitude", coords.get("lng"))
        if lat is not None and lng is not None:
            return (lat, lng)
        return (0.0, 0.0)
    
    @property
    def contact_data(self) -> Dict[str, Any]:
        """Get the contact information dictionary."""
        return self._data.get("contact_data", {})
    
    @property
    def website(self) -> str:
        """Get the company website."""
        return self.contact_data.get("website", "")
    
    @property
    def phone_number(self) -> str:
        """Get the company phone number."""
        return self.contact_data.get("phone_number", "")
    
    @property
    def email(self) -> str:
        """Get the company email address."""
        return self.contact_data.get("email", "")
    
    # --------------------------------
    # Business information
    # --------------------------------
    
    @property
    def keywords(self) -> List[str]:
        """Get the company keywords."""
        return self._data.get("keywords", [])
    
    @property
    def products_and_services(self) -> List[str]:
        """Get the company's products and services."""
        return self._data.get("products_and_services", [])
    
    @property
    def industry_classification(self) -> Dict[str, List[Dict[str, str]]]:
        """Get the industry classification dictionary."""
        ic = self._data.get("industry_classification", {})
        if isinstance(ic, list):
            # Older API versions returned the codes separately
            return {"WZ2008": self._data.get("wz2008_codes", ic)}
        return ic
    
    @property
    def wz2008_codes(self) -> List[Dict[str, str]]:
        """Get the WZ2008 industry classification codes."""
        ic = self.industry_classification
        if isinstance(ic, dict):
            return ic.get("WZ2008", [])
        return self._data.get("wz2008_codes", [])
    
    # --------------------------------
    # Related persons (management, etc.)
    # --------------------------------
    
    @property
    def related_persons(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get the related persons dictionary with 'current' and 'past' keys."""
        return self._data.get("related_persons", {"current": [], "past": []})
    
    @property
    def current_related_persons(self) -> List[Dict[str, Any]]:
        """Get the list of current related persons."""
        return self.related_persons.get("current", [])
    
    @property
    def past_related_persons(self) -> List[Dict[str, Any]]:
        """Get the list of past related persons."""
        return self.related_persons.get("past", [])
    
    @property
    def all_related_persons(self) -> List[Dict[str, Any]]:
        """Get a combined list of all related persons (current and past)."""
        return self.current_related_persons + self.past_related_persons
    
    def get_related_persons_by_role(self, role_label: str, current_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get related persons filtered by their role.
        
        :param role_label: The role to filter by (e.g., 'MANAGING_DIRECTOR', 'PROCURA').
        :param current_only: If True, only include current persons.
        :return: A list of related persons with the specified role.
        """
        if current_only:
            persons = self.current_related_persons
        else:
            persons = self.all_related_persons
            
        result = []
        for p in persons:
            label = p.get("label") or p.get("role", {}).get("label")
            if label == role_label:
                if "label" not in p and label is not None:
                    p = {**p, "label": label}
                result.append(p)
        return result
    
    # --------------------------------
    # Shareholder information
    # --------------------------------
    
    @property
    def shareholders(self) -> ShareholderInfo:
        """Get shareholder information with structured helper objects."""
        data = self._data.get("shareholders") or {}
        entries: List[ShareholderEntry] = []
        for entry in data.get("entries", []):
            if not isinstance(entry, dict):
                continue
            entries.append(
                ShareholderEntry(
                    shareholder=entry.get("shareholder", {}),
                    contribution=entry.get("contribution", {}),
                    contribution_ratio=entry.get("contribution_ratio"),
                    raw=entry
                )
            )
        total_capital = data.get("total_capital")
        return ShareholderInfo(entries=entries, total_capital=total_capital, raw=data)

    # --------------------------------
    # Ultimate beneficial owners (UBOs)
    # --------------------------------

    @property
    def ubos(self) -> UBOInfo:
        """Return structured ultimate beneficial owner (UBO) information."""
        data = self._data.get("ubos")
        if not isinstance(data, dict):
            return UBOInfo(raw={})

        resolved_raw = (
            data.get("resolved")
            or data.get("owners")
            or data.get("beneficial_owners")
            or []
        )
        unresolved_raw = (
            data.get("unresolved")
            or data.get("unresolved_beneficial_owners")
            or []
        )

        resolved = [UBOEntry(raw=entry) for entry in resolved_raw if isinstance(entry, dict)]
        unresolved = [UBOEntry(raw=entry) for entry in unresolved_raw if isinstance(entry, dict)]

        coverage = data.get("coverage")
        if coverage is None and isinstance(data.get("summary"), dict):
            coverage = data["summary"].get("coverage")

        return UBOInfo(
            resolved=resolved,
            unresolved=unresolved,
            coverage=coverage,
            raw=data,
        )

    # --------------------------------
    # Outbound shareholdings
    # --------------------------------

    @property
    def shareholdings(self) -> ShareholdingsInfo:
        """Return the company's own shareholdings in other organizations."""
        data = self._data.get("shareholdings") or {}
        holdings = data.get("holdings") if isinstance(data.get("holdings"), dict) else data

        current_raw = []
        past_raw = []
        if isinstance(holdings, dict):
            current_raw = holdings.get("current", []) or []
            past_raw = holdings.get("past", []) or []

        current = [ShareholdingEntry(raw=entry) for entry in current_raw if isinstance(entry, dict)]
        past = [ShareholdingEntry(raw=entry) for entry in past_raw if isinstance(entry, dict)]

        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        return ShareholdingsInfo(
            current=current,
            past=past,
            summary=summary,
            raw=data if isinstance(data, dict) else {},
        )

    # --------------------------------
    # Annual financial statements
    # --------------------------------

    @property
    def annual_financial_statements(self) -> List[Dict[str, Any]]:
        """Return full annual reports (Markdown) with metadata."""
        value = self._data.get("annual_financial_statements") or []
        return list(value) if isinstance(value, list) else []

    @property
    def annual_financial_statements_html(self) -> List[Dict[str, Any]]:
        """Return full annual reports (HTML) with metadata."""
        value = self._data.get("annual_financial_statements__html") or []
        return list(value) if isinstance(value, list) else []

    def get_annual_financial_statement_for_year(
        self, year: int, html: bool = False
    ) -> Dict[str, Any]:
        """
        Return an annual financial statement for the given year.

        :param year: Report year.
        :param html: When True, return the HTML variant instead of Markdown.
        """
        statements = self.annual_financial_statements_html if html else self.annual_financial_statements
        for item in statements:
            if item.get("year") == year:
                return item
        return {}

    # --------------------------------
    # Insolvency, news, website
    # --------------------------------

    @property
    def insolvency_publications(self) -> List[Dict[str, Any]]:
        """Insolvency court publications."""
        value = self._data.get("insolvency_publications") or []
        return list(value) if isinstance(value, list) else []

    @property
    def news(self) -> List[Dict[str, Any]]:
        """News articles about the company."""
        value = self._data.get("news") or []
        return list(value) if isinstance(value, list) else []

    @property
    def website_content(self) -> Any:
        """Company website content as structured Markdown (AI mode)."""
        return self._data.get("website_content")

    # --------------------------------
    # Financial information
    # --------------------------------
    
    @property
    def financial_kpi(self) -> List[Dict[str, Any]]:
        """Get the list of financial KPIs by year."""
        return self._data.get("financial_kpi", [])
    
    @property
    def financial_years(self) -> List[int]:
        """Get a list of years for which financial data is available, sorted newest first."""
        years = []
        
        # Add years from financial KPIs
        years.extend([item.get("year") for item in self.financial_kpi if item.get("year")])
        
        # Add years from balance sheets
        years.extend([item.get("year") for item in self.balance_sheet_accounts if item.get("year")])
        
        # Add years from profit and loss accounts
        years.extend([item.get("year") for item in self.profit_and_loss_account if item.get("year")])
        
        # Remove duplicates and sort descending
        return sorted(list(set(years)), reverse=True)
    
    def get_financial_kpi_for_year(self, year: int, key: Optional[str] = None) -> Union[Dict[str, Any], Any]:
        """
        Get financial KPI data for a specific year.
        
        :param year: The year to get data for.
        :param key: Optional specific KPI to retrieve (e.g., 'revenue', 'employees').
        :return: The KPI data for the year, or a specific value if key is provided.
        """
        for item in self.financial_kpi:
            if item.get("year") == year:
                if key:
                    return item.get(key)
                return item
        return {} if key is None else None
    
    @property
    def balance_sheet_accounts(self) -> List[Dict[str, Any]]:
        """Get the list of balance sheet accounts by year."""
        return self._data.get("balance_sheet_accounts", [])
    
    def get_balance_sheet_for_year(self, year: int) -> Dict[str, Any]:
        """
        Get balance sheet data for a specific year.
        
        :param year: The year to get data for.
        :return: The balance sheet data for the year.
        """
        for item in self.balance_sheet_accounts:
            if item.get("year") == year:
                return item
        return {}
    
    @property
    def profit_and_loss_account(self) -> List[Dict[str, Any]]:
        """Get the list of profit and loss accounts by year."""
        return self._data.get("profit_and_loss_account", [])
    
    def get_profit_and_loss_for_year(self, year: int) -> Dict[str, Any]:
        """
        Get profit and loss data for a specific year.
        
        :param year: The year to get data for.
        :return: The profit and loss data for the year.
        """
        for item in self.profit_and_loss_account:
            if item.get("year") == year:
                return item
        return {}
    
    # --------------------------------
    # History and events
    # --------------------------------
    
    @property
    def history(self) -> List[Dict[str, Any]]:
        """Get the company history/events list."""
        return self._data.get("history", [])
    
    def get_history_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """
        Get history events filtered by type.
        
        :param event_type: The type of events to filter by.
        :return: A list of history events of the specified type.
        """
        event_type_lower = event_type.lower()
        return [
            event
            for event in self.history
            if event.get("name", {}).get("en", "").lower().startswith(event_type_lower)
        ]
    
    @property
    def publications(self) -> List[Dict[str, Any]]:
        """Get the company publications list."""
        return self._data.get("publications", [])
    
    # --------------------------------
    # Document fetching
    # --------------------------------
    
    def fetch_document(
        self,
        document_type: str,
        output_file: Optional[str] = None,
    ) -> bytes:
        """
        Fetch official PDF documents for this company.
        
        :param document_type: Type of document to fetch. Valid values:
                              - "shareholders_list": Gesellschafterliste document
                              - "AD": Current excerpts (Aktuelle Daten)
                              - "CD": Historical excerpts (Chronologische Daten)
        :param output_file: Optional path to save the PDF file. If not provided,
                            returns the PDF content as bytes.
        :return: PDF content as bytes (if output_file is not provided).
        :raises HandelsregisterError: For any request or response failures.
        :raises ValueError: If entity_id is not available or for invalid parameters.
        """
        if not self.entity_id:
            raise ValueError(
                "Cannot fetch document: entity_id is not available for this company. "
                "Make sure the company data was fetched successfully."
            )
        
        return self._client.fetch_document(
            company_id=self.entity_id,
            document_type=document_type,
            output_file=output_file
        )
    
    # --------------------------------
    # Meta information
    # --------------------------------
    
    @property
    def meta(self) -> Dict[str, Any]:
        """Get the meta information about the API request."""
        return self._data.get("meta", {})
    
    @property
    def request_credit_cost(self) -> int:
        """Get the credit cost of the API request."""
        return int(self.meta.get("request_credit_cost", 0))
    
    # --------------------------------
    # Special methods
    # --------------------------------
    
    def __repr__(self) -> str:
        """String representation of the Company instance."""
        reg_num = f", registration_number='{self.registration_number}'" if self.registration_number else ""
        return f"Company(name='{self.name}'{reg_num})"
    
    def __str__(self) -> str:
        """String representation of the Company instance."""
        if self.registration_number:
            return f"{self.name} ({self.registration_number})"
        return self.name
