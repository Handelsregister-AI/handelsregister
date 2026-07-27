#!/usr/bin/env python3
"""
Example script demonstrating basic usage of the Handelsregister client.

This script shows how to:
1. Initialize the client with your API key
2. Make basic organization queries
3. Request additional features/data

To run:
python client_example.py
"""
import os
from handelsregister import Handelsregister

# Set your API key (or use environment variable HANDELSREGISTER_API_KEY)
API_KEY = os.getenv("HANDELSREGISTER_API_KEY", "your_api_key_here")

def main():
    # Initialize the client
    client = Handelsregister(api_key=API_KEY)
    print("🔑 Initialized Handelsregister client")
    
    # Basic company lookup
    print("\n🔍 Basic company lookup")
    company_data = client.fetch_organization(q="KONUX GmbH München")
    
    # Print basic company information
    print(f"  Company: {company_data.get('name')}")
    print(f"  Status: {company_data.get('status')}")
    print(f"  Registration: {company_data.get('registration', {}).get('register_number', '')}")
    
    # Advanced lookup with specific features
    print("\n🔍 Advanced lookup with financial data and related persons")
    company_data = client.fetch_organization(
        q="Konux GmbH aus München",
        features=[
            "financial_kpi",           # Include financial KPIs
            "related_persons",         # Include management/related persons
            "balance_sheet_accounts",  # Include balance sheets
            "mergers_and_acquisitions", # Include M&A and control relationships
        ],
        ai_search="off"                # Disable AI-based search
    )
    
    # Print financial data if available
    financial_data = company_data.get("financial_kpi", [])
    if financial_data:
        print("\n💰 Financial Data:")
        for year_data in financial_data:
            year = year_data.get("year")
            revenue = year_data.get("revenue")
            employees = year_data.get("employees")
            print(f"  Year {year}: Revenue: {revenue}, Employees: {employees}")
    
    # Print current management if available
    related_persons = company_data.get("related_persons", {}).get("current", [])
    if related_persons:
        print("\n👥 Current Management:")
        for person in related_persons:
            role = person.get("role", {}).get("en", {}).get("long", "")
            print(f"  {person.get('name')} - {role}")

    representation = company_data.get("representation_scheme") or {}
    for rule in representation.get("current", []):
        print(f"  Representation: {rule}")

    ma_data = company_data.get("mergers_and_acquisitions") or {}
    for transaction in ma_data.get("transactions", []):
        headline = transaction.get("headline", {}).get("en", "")
        print(f"  M&A: {transaction.get('date')} — {headline}")
    
    print("\n✅ Example completed")

if __name__ == "__main__":
    main()
