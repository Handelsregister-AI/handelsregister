import logging
from typing import Dict, Any, Optional, List, Union, Tuple, TypeVar, Generic, Callable
from datetime import datetime

from .client import Handelsregister
from .exceptions import HandelsregisterError

logger = logging.getLogger(__name__)

T = TypeVar('T')

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
        :param ai_search: Whether to use AI-based search, defaults to "off".
        :param kwargs: Additional parameters to pass to fetch_organization.
        :raises HandelsregisterError: If there was an error fetching the company data.
        """
        self._query = query
        self._client = client or Handelsregister()
        self._features = features or []
        self._ai_search = ai_search
        
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
        date = self.registration.get("registered_at", "")
        if not date:
            # If not available, try the top-level registration_date field
            date = self._data.get("registration_date", "")
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
        
        country = addr.get("country", "")
        if country:
            components.append(country)
        
        return ", ".join(components)
    
    @property
    def coordinates(self) -> Tuple[float, float]:
        """Get the latitude and longitude coordinates for the company address."""
        coords = self.address.get("coordinates", {})
        lat = coords.get("latitude")
        lng = coords.get("longitude")
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
        return self._data.get("industry_classification", {})
    
    @property
    def wz2008_codes(self) -> List[Dict[str, str]]:
        """Get the WZ2008 industry classification codes."""
        return self.industry_classification.get("WZ2008", [])
    
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
            
        return [p for p in persons if p.get("label") == role_label]
    
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
        return [
            event for event in self.history 
            if event.get("name", {}).get("en", "").lower() == event_type.lower()
        ]
    
    @property
    def publications(self) -> List[Dict[str, Any]]:
        """Get the company publications list."""
        return self._data.get("publications", [])
    
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
