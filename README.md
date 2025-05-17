# 🔍 Handelsregister Python SDK

[![PyPI version](https://img.shields.io/pypi/v/handelsregister.svg)](https://pypi.org/project/handelsregister/)
[![Python Versions](https://img.shields.io/pypi/pyversions/handelsregister.svg)](https://pypi.org/project/handelsregister/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modern Python client for accessing the [Handelsregister.ai](https://handelsregister.ai) API. This SDK provides convenient access to German company registry data with comprehensive information about companies, their management, financial data, and more.

## ✨ Features

- 🔎 **Easy Search**: Find companies using name, location and more
- 📊 **Financial Data**: Access balance sheets, financial KPIs and P&L statements
- 👥 **Management Information**: Details on current and past management positions
- 📃 **Company Details**: Comprehensive legal entity information
- 📚 **Batch Processing**: Enrich large datasets with company data 
- 🔄 **Resilient Design**: Built-in retries, error handling, and snapshot capabilities

## 📦 Installation

```bash
pip install handelsregister
```

## 🔑 Authentication

You'll need an API key from [Handelsregister.ai](https://handelsregister.ai). You can pass it explicitly or set it as an environment variable:

```bash
export HANDELSREGISTER_API_KEY=your_api_key_here
```

## 🚀 Quick Start

### Basic Usage

```python
from handelsregister import Handelsregister

# Create client (API key from environment variable or pass explicitly)
client = Handelsregister(api_key="your_api_key_here")

# Fetch company information
company_data = client.fetch_organization(q="Konux GmbH München")

# Access company data
print(f"Company: {company_data['name']}")
print(f"Registration: {company_data['registration']['register_number']}")
print(f"Status: {company_data['status']}")
```

### Object-Oriented Interface

For a more convenient, object-oriented access to company data:

```python
from handelsregister import Company

# Create company object with desired features
company = Company(
    "BMW AG München",
    features=[
        "related_persons",         # Get management information
        "financial_kpi",           # Get financial KPIs
        "balance_sheet_accounts",  # Get balance sheet data
    ]
)

# Access basic information
print(f"Name: {company.name}")
print(f"Registration: {company.registration_number}")
print(f"Status: {'Active' if company.is_active else 'Inactive'}")
print(f"Address: {company.formatted_address}")

# Get management information
for person in company.current_related_persons:
    print(f"Manager: {person['name']} - {person['role']['en']['long']}")

# Get financial data for the most recent year
years = company.financial_years
if years:
    recent_year = years[0]
    revenue = company.get_financial_kpi_for_year(recent_year, "revenue")
    employees = company.get_financial_kpi_for_year(recent_year, "employees")
    print(f"Revenue ({recent_year}): {revenue}")
    print(f"Employees ({recent_year}): {employees}")
```

## 📊 Data Enrichment

The SDK allows you to enrich datasets with company information:

```python
from handelsregister import Handelsregister
import json

# Sample data in a JSON file
data = [
    {"company_name": "BMW AG", "city": "München"},
    {"company_name": "Konux GmbH", "city": "München"},
    {"company_name": "OroraTech GmbH", "city": "Walldorf"}
]

# Save to a file
with open("companies.json", "w") as f:
    json.dump(data, f)

# Create client
client = Handelsregister()

# Enrich the data
client.enrich(
    file_path="companies.json",
    input_type="json",
    query_properties={
        "name": "company_name",    # Map field 'company_name' to query parameter 'name'
        "location": "city"         # Map field 'city' to query parameter 'location'
    },
    snapshot_dir="snapshots",      # Store intermediate results
    params={
        "features": ["related_persons", "financial_kpi"],
        "ai_search": "off"
    }
)
```

## 🖥️ Command Line Interface

You can also use a small CLI after installing the package:

```bash
$ handelsregister-cli search "KONUX GmbH München"
{
  "name": "KONUX GmbH",
  "registration": {"register_number": "210918"},
  "status": "ACTIVE"
}

$ handelsregister-cli enrich companies.csv --input csv \
    --query-properties name=company_name location=city \
    --snapshot-dir snapshots
```

## 📋 Available Features

The API supports several feature flags that you can include in your requests:

| Feature Flag | Description |
|--------------|-------------|
| `related_persons` | Management and executive information |
| `financial_kpi` | Financial key performance indicators |
| `balance_sheet_accounts` | Balance sheet data |
| `profit_and_loss_account` | Profit and loss statement data |
| `publications` | Official publications |

## 🔍 Company Properties

The `Company` class provides convenient access to all company information:

```python
# Basic information
company.name
company.entity_id
company.status
company.is_active
company.purpose

# Registration info
company.registration_number
company.registration_court
company.registration_type
company.registration_date

# Contact and address
company.address
company.formatted_address
company.coordinates
company.website
company.phone_number

# Financial data
company.financial_kpi
company.financial_years
company.balance_sheet_accounts
company.profit_and_loss_account

# Management
company.current_related_persons
company.past_related_persons
company.get_related_persons_by_role("MANAGING_DIRECTOR")

# Method helpers
company.get_financial_kpi_for_year(2022)
company.get_balance_sheet_for_year(2022)
company.get_profit_and_loss_for_year(2022)
```

## 📜 License

This SDK is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
