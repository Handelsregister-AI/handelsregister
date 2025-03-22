import json
import os
from unittest.mock import MagicMock, patch
import pytest

from handelsregister import Handelsregister


class TestEnrichIntegration:
    def test_enrich_basic_flow(self, mock_client, sample_json_file, snapshot_directory, sample_organization_response):
        """Test basic enrichment flow with a JSON file."""
        client, mock_httpx = mock_client
        
        # Configure the mock response
        mock_response = MagicMock()
        mock_response.json.return_value = sample_organization_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        
        # Setup mock session
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_httpx.return_value.__enter__.return_value = mock_session
        
        # Call enrich
        client.enrich(
            file_path=sample_json_file,
            input_type="json",
            query_properties={"name": "company_name", "location": "city"},
            snapshot_dir=snapshot_directory,
            snapshot_steps=1  # Create snapshot after each item
        )
        
        # Verify API was called for each item
        assert mock_session.get.call_count == 3
        
        # Verify snapshots were created
        snapshots = [f for f in os.listdir(snapshot_directory) if f.startswith("snapshot_")]
        assert len(snapshots) > 0
        
        # Load the latest snapshot to verify contents
        latest_snapshot = max(snapshots)
        with open(os.path.join(snapshot_directory, latest_snapshot), 'r') as f:
            snapshot_data = json.load(f)
        
        # Verify all items are in the snapshot
        assert len(snapshot_data) == 3
        
        # Verify each item has the enrichment data
        for item in snapshot_data:
            assert "_handelsregister_result" in item
            assert item["_handelsregister_result"] == sample_organization_response
            assert item["_in_file"] is True

    def test_enrich_with_existing_snapshot(self, mock_client, sample_json_file, snapshot_directory, sample_organization_response):
        """Test enrichment with an existing snapshot."""
        client, mock_httpx = mock_client
        
        # Create a pre-existing snapshot with one item already enriched
        existing_data = [
            {
                "company_name": "OroraTech GmbH", 
                "city": "München", 
                "id": "1",
                "_in_file": True,
                "_handelsregister_result": {"name": "OroraTech GmbH", "existing": "data"}
            }
        ]
        
        os.makedirs(snapshot_directory, exist_ok=True)
        with open(os.path.join(snapshot_directory, "snapshot_20230101_120000.json"), 'w') as f:
            json.dump(existing_data, f)
        
        # Configure the mock for new API calls
        mock_response = MagicMock()
        mock_response.json.return_value = sample_organization_response
        mock_response.raise_for_status.return_value = None
        
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_httpx.return_value.__enter__.return_value = mock_session
        
        # Call enrich
        client.enrich(
            file_path=sample_json_file,
            input_type="json",
            query_properties={"name": "company_name", "location": "city"},
            snapshot_dir=snapshot_directory
        )
        
        # Verify API was called only for the 2 new items (not for OroraTech which was in snapshot)
        assert mock_session.get.call_count == 2
        
        # Load the latest snapshot
        snapshots = [f for f in os.listdir(snapshot_directory) if f.startswith("snapshot_")]
        latest_snapshot = max(snapshots)
        with open(os.path.join(snapshot_directory, latest_snapshot), 'r') as f:
            snapshot_data = json.load(f)
        
        # Verify all 3 items are in the snapshot
        assert len(snapshot_data) == 3
        
        # Verify OroraTech kept its pre-existing enrichment data
        ororatech_item = next(item for item in snapshot_data if item["company_name"] == "OroraTech GmbH")
        assert ororatech_item["_handelsregister_result"]["existing"] == "data"
        
        # Verify the other items got enriched with new data
        example_item = next(item for item in snapshot_data if item["company_name"] == "Example AG")
        assert example_item["_handelsregister_result"] == sample_organization_response

    def test_invalid_input_type(self, mock_client):
        """Test enrich with invalid input_type."""
        client, _ = mock_client
        
        with pytest.raises(ValueError, match="enrich\\(\\) currently only supports 'json' input_type"):
            client.enrich(file_path="test.csv", input_type="csv")

    def test_missing_file_path(self, mock_client):
        """Test enrich with missing file_path."""
        client, _ = mock_client
        
        with pytest.raises(ValueError, match="file_path is required for enrich\\(\\)"):
            client.enrich(input_type="json")


@patch('httpx.Client')
def test_full_client_workflow(mock_httpx_client, api_key, sample_organization_response):
    """Test a full workflow with the client, mocking HTTP calls."""
    # Setup mock response
    mock_response = MagicMock()
    mock_response.json.return_value = sample_organization_response
    mock_response.raise_for_status.return_value = None
    
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_session
    
    # Create client and make API call
    client = Handelsregister(api_key=api_key)
    result = client.fetch_organization(
        q="OroraTech GmbH München",
        features=["related_persons", "publications"],
        ai_search="on-default"
    )
    
    # Verify results
    assert result == sample_organization_response
    
    # Verify parameters were passed correctly
    args, kwargs = mock_session.get.call_args
    assert kwargs["params"]["q"] == "OroraTech GmbH München"
    assert kwargs["params"]["feature"] == ["related_persons", "publications"]
    assert kwargs["params"]["ai_search"] == "on-default"
    assert kwargs["params"]["api_key"] == api_key


@pytest.mark.live_api
def test_real_api_request(real_client):
    """
    Test a real API request to verify the API structure and functionality.
    
    This test is skipped by default. To run it:
    pytest -m live_api test_integration.py
    
    Requires HANDELSREGISTER_API_KEY environment variable to be set.
    """
    # Make a real API request using the real_client fixture
    result = real_client.fetch_organization(q="KONUX GmbH München")
    
    # Verify the response structure
    assert isinstance(result, dict)
    # Check for expected fields based on actual API response structure
    assert "name" in result
    assert "registration" in result
    assert "register_number" in result["registration"]
    
    # Print actual structure for debugging
    print("\nActual API Response Structure:")
    print(json.dumps(result, indent=2))


@pytest.mark.live_api
def test_company_with_real_api(real_client):
    """Test creating a Company object with a real API request."""
    # Import here to avoid circular imports
    from handelsregister import Company
    
    # Create a company object that will make a real API call with features explicitly set
    features = ["related_persons", "financial_kpi"]
    company = Company("KONUX GmbH München", client=real_client, features=features)
    
    # Verify basic properties
    assert company.name, "Company name should not be empty"
    assert company.registration_number, "Registration number should not be empty"
    
    # Verify more detailed information
    assert company.address, "Address should not be empty"
    assert company.legal_form_name, "Legal form should not be empty"
    
    # Check for related persons since we explicitly requested that feature
    assert len(company.current_related_persons) > 0, "Should have current related persons"
