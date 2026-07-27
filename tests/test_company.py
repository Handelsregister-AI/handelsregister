import json
import os
import pytest
from unittest.mock import MagicMock, patch

from handelsregister import Company, Handelsregister, ShareholderInfo, ShareholderEntry
from handelsregister.exceptions import HandelsregisterError


@pytest.fixture
def sample_api_response():
    """Load the sample API response data."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, "data")
    sample_file = os.path.join(data_dir, "api_response_sample.json")
    
    with open(sample_file, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def mock_client(sample_api_response):
    """Create a mocked Handelsregister client."""
    client = MagicMock(spec=Handelsregister)
    client.fetch_organization.return_value = sample_api_response
    return client


@pytest.fixture
def company(mock_client):
    """Create a Company instance with mocked client."""
    return Company("KONUX GmbH", client=mock_client)


class TestCompanyInitialization:
    """Tests for Company initialization."""
    
    def test_init_with_query(self, mock_client):
        """Test initialization with a basic query."""
        company = Company("KONUX GmbH", client=mock_client)
        mock_client.fetch_organization.assert_called_once()
        assert company._query == "KONUX GmbH"
    
    def test_init_with_features(self, mock_client):
        """Test initialization with features."""
        features = ["related_persons", "financial_kpi"]
        Company("KONUX GmbH", client=mock_client, features=features)
        mock_client.fetch_organization.assert_called_once_with(
            q="KONUX GmbH",
            features=features,
            ai_search="off",
            realtime_mode=None,
        )

    def test_init_with_ai_search(self, mock_client):
        """Test initialization with ai_search parameter."""
        Company("KONUX GmbH", client=mock_client, ai_search="on")
        mock_client.fetch_organization.assert_called_once_with(
            q="KONUX GmbH",
            features=[],
            ai_search="on",
            realtime_mode=None,
        )

    def test_init_with_realtime_mode(self, mock_client):
        """Realtime mode is forwarded to fetch_organization."""
        Company(
            "KONUX GmbH", client=mock_client, realtime_mode="handelsregister-default"
        )
        mock_client.fetch_organization.assert_called_once_with(
            q="KONUX GmbH",
            features=[],
            ai_search="off",
            realtime_mode="handelsregister-default",
        )

    def test_init_with_kwargs(self, mock_client):
        """Test initialization with additional kwargs."""
        Company("KONUX GmbH", client=mock_client, some_param="value")
        mock_client.fetch_organization.assert_called_once_with(
            q="KONUX GmbH",
            features=[],
            ai_search="off",
            realtime_mode=None,
            some_param="value"
        )
    
    def test_init_error_handling(self):
        """Test error handling during initialization."""
        mock_client = MagicMock(spec=Handelsregister)
        mock_client.fetch_organization.side_effect = HandelsregisterError("API Error")
        
        with pytest.raises(HandelsregisterError, match="API Error"):
            Company("KONUX GmbH", client=mock_client)
    
    def test_init_creates_client_if_none_provided(self):
        """Test that a client is created if none is provided."""
        with patch('handelsregister.company.Handelsregister') as MockHandelsregister:
            mock_instance = MagicMock()
            MockHandelsregister.return_value = mock_instance
            mock_instance.fetch_organization.return_value = {"name": "KONUX GmbH"}
            
            company = Company("KONUX GmbH")
            
            MockHandelsregister.assert_called_once()
            assert company._client == mock_instance


class TestCompanyBasicProperties:
    """Tests for basic property access."""
    
    def test_data_property(self, company, sample_api_response):
        """Test the data property returns the complete response."""
        assert company.data == sample_api_response
    
    def test_name_property(self, company):
        """Test the name property."""
        assert company.name == "KONUX GmbH"
    
    def test_entity_id_property(self, company):
        """Test the entity_id property."""
        assert company.entity_id == "110fe0da2f84c8d3174ec7bfd1f0f15a"
    
    def test_status_property(self, company):
        """Test the status property."""
        assert company.status == "ACTIVE"
    
    def test_is_active_property(self, company):
        """Test the is_active property."""
        assert company.is_active is True
        
        # Test inactive status
        company._data["status"] = "INACTIVE"
        assert company.is_active is False
    
    def test_purpose_property(self, company):
        """Test the purpose property."""
        assert "Entwicklung und Vertrieb" in company.purpose
        assert "Sensorik und Messtechnik" in company.purpose


class TestCompanyRegistrationProperties:
    """Tests for registration property access."""
    
    def test_registration_property(self, company):
        """Test the registration property."""
        assert "court" in company.registration
        assert "register_type" in company.registration
        assert "register_number" in company.registration
    
    def test_registration_number_property(self, company):
        """Test the registration_number property."""
        assert company.registration_number == "210918"
    
    def test_registration_court_property(self, company):
        """Test the registration_court property."""
        assert company.registration_court == "München"
    
    def test_registration_type_property(self, company):
        """Test the registration_type property."""
        assert company.registration_type == "HRB"
    
    def test_registration_date_property(self, company):
        """Test the registration_date property."""
        assert company.registration_date == "2014-03-24T00:00:00"


class TestCompanyLegalProperties:
    """Tests for legal information property access."""
    
    def test_legal_form_property(self, company):
        """Test the legal_form property."""
        assert company.legal_form == "GmbH"
    
    def test_legal_form_name_property(self, company):
        """Test the legal_form_name property."""
        assert company.legal_form_name == "GmbH"
        
        # Test with a dict legal form
        company._data["legal_form"] = {"name": "GmbH", "code": "some-code"}
        assert company.legal_form_name == "GmbH"


class TestCompanyAddressProperties:
    """Tests for address property access."""
    
    def test_address_property(self, company):
        """Test the address property."""
        assert "street" in company.address
        assert "postal_code" in company.address
        assert "city" in company.address
    
    def test_formatted_address_property(self, company):
        """Test the formatted_address property."""
        expected = "Flößergasse 2, 81369 München, DEU"
        assert company.formatted_address == expected
    
    def test_coordinates_property(self, company):
        """Test the coordinates property."""
        lat, lng = company.coordinates
        assert lat == 48.10646
        assert lng == 11.53716
        
        # Test with missing coordinates
        company._data["address"]["coordinates"] = {}
        assert company.coordinates == (0.0, 0.0)
    
    def test_contact_data_property(self, company):
        """Test the contact_data property."""
        assert "website" in company.contact_data
        assert "phone_number" in company.contact_data
    
    def test_website_property(self, company):
        """Test the website property."""
        assert company.website == "https://www.konux.com/de"
    
    def test_phone_number_property(self, company):
        """Test the phone_number property."""
        assert company.phone_number == "+49 89 18955010"


class TestCompanyBusinessProperties:
    """Tests for business information property access."""
    
    def test_keywords_property(self, company):
        """Test the keywords property."""
        assert "Sensorik" in company.keywords
        assert "Messtechnik" in company.keywords
    
    def test_products_and_services_property(self, company):
        """Test the products_and_services property."""
        assert "KONUX Switch" in company.products_and_services
        assert "KONUX Network" in company.products_and_services
    
    def test_industry_classification_property(self, company):
        """Test the industry_classification property."""
        assert "WZ2008" in company.industry_classification
    
    def test_wz2008_codes_property(self, company):
        """Test the wz2008_codes property."""
        assert len(company.wz2008_codes) > 0
        assert company.wz2008_codes[0]["code"] == "26.51.0"


class TestCompanyRelatedPersonsProperties:
    """Tests for related persons property access and methods."""
    
    def test_related_persons_property(self, company):
        """Test the related_persons property."""
        assert "current" in company.related_persons
        assert "past" in company.related_persons
    
    def test_current_related_persons_property(self, company):
        """Test the current_related_persons property."""
        assert len(company.current_related_persons) > 0
        assert "Johanna Leisch" in [p["name"] for p in company.current_related_persons]
    
    def test_past_related_persons_property(self, company):
        """Test the past_related_persons property."""
        assert len(company.past_related_persons) > 0
        assert "Andreas König" in [p["name"] for p in company.past_related_persons]
    
    def test_all_related_persons_property(self, company):
        """Test the all_related_persons property."""
        assert len(company.all_related_persons) == len(company.current_related_persons) + len(company.past_related_persons)
    
    def test_get_related_persons_by_role(self, company):
        """Test the get_related_persons_by_role method."""
        # Get all managing directors
        managing_directors = company.get_related_persons_by_role("MANAGING_DIRECTOR")
        assert len(managing_directors) > 0
        assert all(p["label"] == "MANAGING_DIRECTOR" for p in managing_directors)
        
        # Get only current managing directors
        current_managing_directors = company.get_related_persons_by_role("MANAGING_DIRECTOR", current_only=True)
        assert len(current_managing_directors) > 0
        assert all(p["label"] == "MANAGING_DIRECTOR" for p in current_managing_directors)
        assert len(current_managing_directors) <= len(managing_directors)


class TestCompanyShareholderProperties:
    """Tests for shareholder information property access."""
    
    def test_shareholders_property_default(self, company):
        """Company without shareholder data returns empty info object."""
        shareholders = company.shareholders
        assert isinstance(shareholders, ShareholderInfo)
        assert bool(shareholders) is False
        assert shareholders.entries == []
        assert shareholders.total_capital is None
    
    def test_shareholder_info_with_data(self, company):
        """Shareholder helper methods expose structured entries."""
        sample_shareholders = {
            "entries": [
                {
                    "contribution": {"amount": 100, "currency": "EUR"},
                    "contribution_ratio": 0.25,
                    "shareholder": {
                        "entity_name": "Sample Holder GmbH",
                        "address": "München"
                    }
                }
            ],
            "total_capital": {"amount": 400, "currency": "EUR"}
        }
        company._data["shareholders"] = sample_shareholders
        shareholders = company.shareholders
        assert isinstance(shareholders, ShareholderInfo)
        assert bool(shareholders) is True
        assert shareholders.total_capital == sample_shareholders["total_capital"]
        assert shareholders.as_dict() == sample_shareholders
        assert len(shareholders.entries) == 1
        
        entry = shareholders.entries[0]
        assert isinstance(entry, ShareholderEntry)
        assert entry.display_name == "Sample Holder GmbH"
        assert entry.contribution_amount == 100
        assert entry.contribution_currency == "EUR"
        assert entry.percentage == 0.25
        assert entry.address == "München"


class TestCompanyUBOsAndShareholdings:
    """Tests for the new UBO and shareholdings helpers on Company."""

    def test_ubos_empty(self, company):
        ubos = company.ubos
        assert bool(ubos) is False
        assert ubos.resolved == []
        assert ubos.unresolved == []

    def test_ubos_populated(self, company):
        company._data["ubos"] = {
            "resolved": [
                {"name": "Max Mustermann", "percentage": 45.5, "type": "natural_person"}
            ],
            "unresolved": [
                {"name": "Holding Inc.", "percentage": 10.0}
            ],
            "coverage": 0.9,
        }
        ubos = company.ubos
        assert bool(ubos) is True
        assert len(ubos.resolved) == 1
        assert ubos.resolved[0].name == "Max Mustermann"
        assert ubos.resolved[0].percentage == 45.5
        assert ubos.coverage == 0.9
        assert len(ubos.all) == 2

    def test_shareholdings_empty(self, company):
        holdings = company.shareholdings
        assert bool(holdings) is False

    def test_shareholdings_populated(self, company):
        company._data["shareholdings"] = {
            "holdings": {
                "current": [
                    {
                        "organization": {"entity_id": "x1", "name": "Sub GmbH"},
                        "ownership": {
                            "percentage": 100.0,
                            "contribution": {"amount": 25000, "currency": "EUR"},
                        },
                        "as_of": "2025-01-01",
                    }
                ]
            },
            "summary": {"total_current": 1},
        }
        holdings = company.shareholdings
        assert bool(holdings) is True
        assert len(holdings.current) == 1
        entry = holdings.current[0]
        assert entry.organization_name == "Sub GmbH"
        assert entry.percentage == 100.0
        assert entry.contribution_amount == 25000
        assert entry.contribution_currency == "EUR"
        assert entry.as_of == "2025-01-01"

    def test_annual_financial_statements(self, company):
        assert company.annual_financial_statements == []
        company._data["annual_financial_statements"] = [
            {"year": 2023, "content": "# Report"}
        ]
        assert company.get_annual_financial_statement_for_year(2023)["year"] == 2023
        assert company.get_annual_financial_statement_for_year(1999) == {}

    def test_news_insolvency_website(self, company):
        assert company.news == []
        assert company.insolvency_publications == []
        assert company.website_content is None
        company._data["news"] = [{"title": "X"}]
        company._data["insolvency_publications"] = [{"case": "IN 1/24"}]
        company._data["website_content"] = "# About"
        assert company.news[0]["title"] == "X"
        assert company.insolvency_publications[0]["case"] == "IN 1/24"
        assert company.website_content == "# About"


class TestCompanyFinancialProperties:
    """Tests for financial information property access and methods."""
    
    def test_financial_kpi_property(self, company):
        """Test the financial_kpi property."""
        assert len(company.financial_kpi) > 0
        assert all("year" in kpi for kpi in company.financial_kpi)
    
    def test_financial_years_property(self, company):
        """Test the financial_years property."""
        years = company.financial_years
        assert len(years) > 0
        assert all(isinstance(year, int) for year in years)
        assert years == sorted(years, reverse=True)  # Check years are sorted newest first
    
    def test_get_financial_kpi_for_year(self, company):
        """Test the get_financial_kpi_for_year method."""
        # Get all KPIs for 2022
        kpi_2022 = company.get_financial_kpi_for_year(2022)
        assert kpi_2022["year"] == 2022
        assert "revenue" in kpi_2022
        assert "employees" in kpi_2022
        
        # Get a specific KPI
        revenue_2022 = company.get_financial_kpi_for_year(2022, "revenue")
        assert revenue_2022 == 1213678.77
        
        # Test with a non-existent year
        assert company.get_financial_kpi_for_year(9999) == {}
        assert company.get_financial_kpi_for_year(9999, "revenue") is None
    
    def test_balance_sheet_accounts_property(self, company):
        """Test the balance_sheet_accounts property."""
        assert len(company.balance_sheet_accounts) > 0
        assert all("year" in bs for bs in company.balance_sheet_accounts)
    
    def test_get_balance_sheet_for_year(self, company):
        """Test the get_balance_sheet_for_year method."""
        # Get balance sheet for 2022
        bs_2022 = company.get_balance_sheet_for_year(2022)
        assert bs_2022["year"] == 2022
        assert "balance_sheet_accounts" in bs_2022
        
        # Test with a non-existent year
        assert company.get_balance_sheet_for_year(9999) == {}
    
    def test_profit_and_loss_account_property(self, company):
        """Test the profit_and_loss_account property."""
        assert len(company.profit_and_loss_account) > 0
    
    def test_get_profit_and_loss_for_year(self, company):
        """Test the get_profit_and_loss_for_year method."""
        # Get profit and loss for 2022
        pl_2022 = company.get_profit_and_loss_for_year(2022)
        assert pl_2022["year"] == 2022
        
        # Test with a non-existent year
        assert company.get_profit_and_loss_for_year(9999) == {}


class TestCompanyHistoryProperties:
    """Tests for history property access and methods."""
    
    def test_history_property(self, company):
        """Test the history property."""
        assert len(company.history) > 0
    
    def test_get_history_by_type(self, company):
        """Test the get_history_by_type method."""
        # Get history events by type
        address_changes = company.get_history_by_type("change of address")
        assert len(address_changes) > 0
        assert all("address" in event["name"]["en"].lower() for event in address_changes)
    
    def test_publications_property(self, company):
        """Test the publications property."""
        # The sample data may not have publications
        assert isinstance(company.publications, list)


class TestCompanyMetaProperties:
    """Tests for meta information property access."""
    
    def test_meta_property(self, company):
        """Test the meta property."""
        assert "request_credit_cost" in company.meta
        assert "credits_remaining" in company.meta
    
    def test_request_credit_cost_property(self, company):
        """Test the request_credit_cost property."""
        assert company.request_credit_cost == 35


class TestCompanySpecialMethods:
    """Tests for special methods."""
    
    def test_repr_method(self, company):
        """Test the __repr__ method."""
        expected = "Company(name='KONUX GmbH', registration_number='210918')"
        assert repr(company) == expected
    
    def test_str_method(self, company):
        """Test the __str__ method."""
        expected = "KONUX GmbH (210918)"
        assert str(company) == expected
        
        # Test without registration number
        company._data["registration"]["register_number"] = ""
        assert str(company) == "KONUX GmbH"


class TestCompanyWithMissingData:
    """Tests for handling missing data."""
    
    def test_with_missing_data(self):
        """Test behavior with missing data."""
        mock_client = MagicMock(spec=Handelsregister)
        mock_client.fetch_organization.return_value = {}
        
        company = Company("Empty Company", client=mock_client)
        
        # Basic properties should return empty values
        assert company.name == ""
        assert company.entity_id == ""
        assert company.registration_number == ""
        
        # Nested properties should handle missing data
        assert company.address == {}
        assert company.formatted_address == ""
        assert company.coordinates == (0.0, 0.0)
        
        # Lists should be empty
        assert company.keywords == []
        assert company.financial_kpi == []
        assert company.balance_sheet_accounts == []
        
        # Helper methods should handle missing data
        assert company.get_financial_kpi_for_year(2022) == {}
        assert company.get_financial_kpi_for_year(2022, "revenue") is None
        assert company.get_balance_sheet_for_year(2022) == {}
        assert company.get_related_persons_by_role("MANAGING_DIRECTOR") == []


@pytest.mark.live_api
class TestCompanyWithRealAPI:
    """Tests using real API calls. These are skipped by default."""
    
    def test_fetch_real_company(self, real_client):
        """Test fetching a real company using the API."""
        company = Company(
            "KONUX GmbH", 
            client=real_client, 
            features=["related_persons", "financial_kpi"]
        )
        
        # Basic information
        assert company.name == "KONUX GmbH"
        assert company.registration_number == "210918"
        assert company.is_active is True
        
        # Related persons
        assert len(company.current_related_persons) > 0
        
        # Financial information if available
        if company.financial_kpi:
            assert len(company.financial_years) > 0
            # Get the most recent year
            recent_year = company.financial_years[0]
            # Verify we can access the data for that year
            kpi_data = company.get_financial_kpi_for_year(recent_year)
            assert kpi_data is not None


class TestCompanyDocumentFetching:
    """Tests for document fetching functionality."""
    
    def test_fetch_document_basic(self, company):
        """Test basic document fetching."""
        # Mock the client's fetch_document method
        company._client.fetch_document.return_value = b"PDF content"
        
        # Fetch a document
        result = company.fetch_document("shareholders_list")
        
        # Verify the call
        company._client.fetch_document.assert_called_once_with(
            company_id=company.entity_id,
            document_type="shareholders_list",
            output_file=None
        )
        assert result == b"PDF content"
    
    def test_fetch_document_with_output_file(self, company):
        """Test document fetching with output file."""
        # Mock the client's fetch_document method
        company._client.fetch_document.return_value = b"PDF content"
        
        # Fetch a document with output file
        result = company.fetch_document("AD", output_file="test.pdf")
        
        # Verify the call
        company._client.fetch_document.assert_called_once_with(
            company_id=company.entity_id,
            document_type="AD",
            output_file="test.pdf"
        )
        assert result == b"PDF content"
    
    def test_fetch_document_without_entity_id(self, mock_client):
        """Test document fetching when entity_id is missing."""
        # Create a response without entity_id
        response_without_id = {"name": "Test Company", "status": "ACTIVE"}
        mock_client.fetch_organization.return_value = response_without_id
        
        company = Company("Test Company", client=mock_client)
        
        # Attempting to fetch document should raise ValueError
        with pytest.raises(ValueError, match="Cannot fetch document: entity_id is not available"):
            company.fetch_document("CD")
    
    def test_fetch_document_error_propagation(self, company):
        """Test that errors from client are properly propagated."""
        # Mock the client to raise an error
        company._client.fetch_document.side_effect = HandelsregisterError("Document not found")
        
        # The error should be propagated
        with pytest.raises(HandelsregisterError, match="Document not found"):
            company.fetch_document("shareholders_list")
