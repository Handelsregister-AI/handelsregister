import json
import os
import pytest
from unittest.mock import MagicMock, patch

from handelsregister import Company, Handelsregister
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
        company = Company("KONUX GmbH", client=mock_client, features=features)
        mock_client.fetch_organization.assert_called_once_with(
            q="KONUX GmbH",
            features=features,
            ai_search="off"
        )
    
    def test_init_with_ai_search(self, mock_client):
        """Test initialization with ai_search parameter."""
        company = Company("KONUX GmbH", client=mock_client, ai_search="on")
        mock_client.fetch_organization.assert_called_once_with(
            q="KONUX GmbH", 
            features=[], 
            ai_search="on"
        )
    
    def test_init_with_kwargs(self, mock_client):
        """Test initialization with additional kwargs."""
        company = Company("KONUX GmbH", client=mock_client, some_param="value")
        mock_client.fetch_organization.assert_called_once_with(
            q="KONUX GmbH",
            features=[],
            ai_search="off",
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
