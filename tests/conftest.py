import json
import os
import pytest
import tempfile
from unittest.mock import MagicMock, patch
import pandas as pd

from handelsregister import Handelsregister


@pytest.fixture
def api_key():
    """Return the API key from environment or a dummy key for testing."""
    return os.getenv("HANDELSREGISTER_API_KEY", "test_api_key_12345")


@pytest.fixture
def mock_client(sample_organization_response):
    """
    Create a mocked Handelsregister client.
    
    This client will not make real API calls by default.
    """
    with patch('httpx.Client') as mock_httpx:
        # Use the API key from environment if available
        api_key = os.getenv("HANDELSREGISTER_API_KEY", "test_api_key")
        client = Handelsregister(api_key=api_key)
        
        # Configure the mock response
        mock_response = MagicMock()
        mock_response.json.return_value = sample_organization_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_httpx.return_value.__enter__.return_value = mock_session
        
        return client, mock_httpx


@pytest.fixture
def real_client():
    """
    Create a real client for making actual API calls.
    
    This fixture will be skipped if HANDELSREGISTER_API_KEY is not set.
    """
    api_key = os.getenv("HANDELSREGISTER_API_KEY")
    if not api_key:
        pytest.skip("HANDELSREGISTER_API_KEY environment variable not set")
    
    return Handelsregister(api_key=api_key)


@pytest.fixture
def sample_organization_response():
    """Load the sample API response data."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sdk_dir = os.path.dirname(current_dir)
    sample_file = os.path.join(sdk_dir, "api_response_sample.json")
    
    with open(sample_file, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def sample_json_file(tmp_path):
    """Create a sample JSON file for testing."""
    data = [
        {"company_name": "OroraTech GmbH", "city": "München", "id": "1"},
        {"company_name": "Example AG", "city": "Berlin", "id": "2"},
        {"company_name": "Test GmbH", "city": "Hamburg", "id": "3"}
    ]
    
    file_path = tmp_path / "sample.json"
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
        
    return str(file_path)


@pytest.fixture
def sample_csv_file(tmp_path):
    data = [
        {"company_name": "OroraTech GmbH", "city": "München", "id": "1"},
        {"company_name": "Example AG", "city": "Berlin", "id": "2"},
        {"company_name": "Test GmbH", "city": "Hamburg", "id": "3"}
    ]
    df = pd.DataFrame(data)
    file_path = tmp_path / "sample.csv"
    df.to_csv(file_path, index=False)
    return str(file_path)


@pytest.fixture
def sample_xlsx_file(tmp_path):
    data = [
        {"company_name": "OroraTech GmbH", "city": "München", "id": "1"},
        {"company_name": "Example AG", "city": "Berlin", "id": "2"},
        {"company_name": "Test GmbH", "city": "Hamburg", "id": "3"}
    ]
    df = pd.DataFrame(data)
    file_path = tmp_path / "sample.xlsx"
    df.to_excel(file_path, index=False)
    return str(file_path)


@pytest.fixture
def snapshot_directory(tmp_path):
    """Create a temporary directory for snapshots."""
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    return str(snapshot_dir)
