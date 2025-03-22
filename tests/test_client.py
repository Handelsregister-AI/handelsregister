import json
import os
import pytest
from unittest.mock import MagicMock, patch

import httpx

from handelsregister import Handelsregister
from handelsregister.exceptions import AuthenticationError, HandelsregisterError, InvalidResponseError


class TestClientInitialization:
    def test_init_with_api_key(self, api_key):
        """Test client initialization with explicit API key."""
        client = Handelsregister(api_key=api_key)
        assert client.api_key == api_key
        assert client.base_url == "https://handelsregister.ai/api/v1"

    def test_init_with_env_var(self):
        """Test client initialization with API key from environment."""
        env_api_key = "env_test_key_67890"
        with patch.dict(os.environ, {"HANDELSREGISTER_API_KEY": env_api_key}):
            client = Handelsregister()
            assert client.api_key == env_api_key

    def test_init_without_api_key(self):
        """Test that initialization fails without API key."""
        with patch.dict(os.environ, {"HANDELSREGISTER_API_KEY": ""}):
            with pytest.raises(AuthenticationError):
                Handelsregister()

    def test_init_with_custom_values(self, api_key):
        """Test initialization with custom timeout and base URL."""
        custom_timeout = 30.0
        custom_base_url = "https://custom.handelsregister.ai/api/v2/"
        
        client = Handelsregister(
            api_key=api_key,
            timeout=custom_timeout,
            base_url=custom_base_url
        )
        
        assert client.timeout == custom_timeout
        assert client.base_url == "https://custom.handelsregister.ai/api/v2"  # Trailing slash stripped


class TestFetchOrganization:
    def test_fetch_organization_basic(self, mock_client, sample_organization_response):
        """Test basic fetch_organization call."""
        client, mock_httpx = mock_client
        
        # Configure mock response
        mock_response = MagicMock()
        mock_response.json.return_value = sample_organization_response
        mock_response.raise_for_status.return_value = None
        
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_httpx.return_value.__enter__.return_value = mock_session
        
        # Call the method
        result = client.fetch_organization(q="OroraTech GmbH")
        
        # Verify results
        assert result == sample_organization_response
        mock_session.get.assert_called_once()
        
        # Check that parameters were passed correctly
        args, kwargs = mock_session.get.call_args
        assert kwargs["params"]["q"] == "OroraTech GmbH"
        assert kwargs["params"]["api_key"] == client.api_key

    def test_fetch_organization_with_features(self, mock_client, sample_organization_response):
        """Test fetch_organization with feature flags."""
        client, mock_httpx = mock_client
        
        # Configure mock response
        mock_response = MagicMock()
        mock_response.json.return_value = sample_organization_response
        mock_response.raise_for_status.return_value = None
        
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_httpx.return_value.__enter__.return_value = mock_session
        
        # Call the method with features
        features = ["related_persons", "publications"]
        result = client.fetch_organization(q="Test GmbH", features=features)
        
        # Verify results
        assert result == sample_organization_response
        
        # Check features were passed correctly
        args, kwargs = mock_session.get.call_args
        assert kwargs["params"]["feature"] == features

    def test_missing_query_parameter(self, mock_client):
        """Test that fetch_organization raises an error without a query."""
        client, _ = mock_client
        
        with pytest.raises(ValueError, match="Parameter 'q' is required"):
            client.fetch_organization(q="")

    def test_authentication_error(self, mock_client):
        """Test handling of authentication errors."""
        client, mock_httpx = mock_client
        
        # Configure mock response for 401 Unauthorized
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=MagicMock(status_code=401)
        )
        
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_httpx.return_value.__enter__.return_value = mock_session
        
        # Call the method and expect AuthenticationError
        with pytest.raises(AuthenticationError):
            client.fetch_organization(q="Test Company")

    def test_non_json_response(self, mock_client):
        """Test handling of invalid JSON responses."""
        client, mock_httpx = mock_client
        
        # Configure mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status.return_value = None
        
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_httpx.return_value.__enter__.return_value = mock_session
        
        # Call the method and expect InvalidResponseError
        with pytest.raises(InvalidResponseError):
            client.fetch_organization(q="Test Company")


class TestHelperMethods:
    def test_build_q_string(self):
        """Test building query strings from item properties."""
        client = Handelsregister(api_key="dummy_key")
        
        # Test with multiple properties
        item = {"company_name": "Test GmbH", "city": "Berlin", "country": "Germany"}
        query_props = {"name": "company_name", "location": "city"}
        q_string = client._build_q_string(item, query_props)
        assert q_string == "Test GmbH Berlin"
        
        # Test with missing properties
        item = {"company_name": "Test GmbH"}
        q_string = client._build_q_string(item, query_props)
        assert q_string == "Test GmbH"
        
        # Test with empty properties
        item = {"company_name": "", "city": ""}
        q_string = client._build_q_string(item, query_props)
        assert q_string == ""

    def test_build_key(self):
        """Test building unique keys for items."""
        client = Handelsregister(api_key="dummy_key")
        
        # Test with defined properties
        item = {"company_name": "Test GmbH", "city": "Berlin", "id": "123"}
        query_props = {"name": "company_name", "location": "city"}
        key = client._build_key(item, query_props)
        assert key == ("Test GmbH", "Berlin")
        
        # Test with empty query properties
        key = client._build_key(item, {})
        assert isinstance(key, int)  # Should be an id(item)

    def test_merge_data(self):
        """Test merging snapshot data with file data."""
        client = Handelsregister(api_key="dummy_key")
        
        # Create sample data
        snapshot_data = [
            {"company_name": "Old GmbH", "city": "Berlin", "_handelsregister_result": {"old": "data"}},
            {"company_name": "Updated GmbH", "city": "Munich", "_handelsregister_result": {"existing": "data"}}
        ]
        
        file_data = [
            {"company_name": "Updated GmbH", "city": "Munich", "new_field": "new_value"},
            {"company_name": "New GmbH", "city": "Hamburg"}
        ]
        
        query_props = {"name": "company_name", "location": "city"}
        
        # Merge the data
        merged = client._merge_data(snapshot_data, file_data, query_props)
        
        # Verify results
        assert len(merged) == 3  # All 3 unique items (Old, Updated, New)
        
        # The old item should be marked as not in file but kept
        old_item = next(item for item in merged if item["company_name"] == "Old GmbH")
        assert old_item["_in_file"] is False
        assert "_handelsregister_result" in old_item
        
        # The updated item should be the new version but keep the old enrichment data
        updated_item = next(item for item in merged if item["company_name"] == "Updated GmbH")
        assert updated_item["_in_file"] is True
        assert "new_field" in updated_item
        assert updated_item["_handelsregister_result"] == {"existing": "data"}
        
        # The new item should be present and marked as in file
        new_item = next(item for item in merged if item["company_name"] == "New GmbH")
        assert new_item["_in_file"] is True
        assert "_handelsregister_result" not in new_item
