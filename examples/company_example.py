#!/usr/bin/env python3
"""
Example script demonstrating the Company class for object-oriented access.

This script shows how to:
1. Create a Company object to access company data
2. Access various properties through the object interface
3. Use convenience methods for accessing financial data and related persons

To run:
python company_example.py
"""
import os
from pprint import pprint
from handelsregister import Company

# Set your API key (or use environment variable HANDELSREGISTER_API_KEY)
API_KEY = os.getenv("HANDELSREGISTER_API_KEY", "your_api_key_here")

def main():
    # Create a Company object with the features we want
    print("🔍 Looking up company information...")
    company = Company(
        "KONUX GmbH München",
        features=[
            "related_persons",         # Get management information
            "financial_kpi",           # Get financial key performance indicators
            "balance_sheet_accounts",  # Get balance sheet data
            "profit_and_loss_account", # Get profit and loss data
        ],
        ai_search="off"                # Disable AI-based search
    )
    
    # Basic information
    print("\n📋 Basic Information:")
    print(f"  Name: {company.name}")
    print(f"  Registration: {company.registration_number} ({company.registration_court})")
    print(f"  Status: {'Active' if company.is_active else 'Inactive'}")
    print(f"  Legal Form: {company.legal_form_name}")
    print(f"  Address: {company.formatted_address}")
    print(f"  Website: {company.website}")
    
    # Management information
    print("\n👥 Current Management:")
    for person in company.current_related_persons:
        role = person.get("role", {}).get("en", {}).get("long", "Unknown Role")
        name = person.get("name", "Unknown")
        start_date = person.get("start_date", "Unknown")
        print(f"  {name} - {role} (since {start_date})")
    
    # Financial information
    print("\n💰 Financial Information:")
    
    # Get all available financial years
    years = company.financial_years
    if years:
        print(f"  Available financial data for years: {', '.join(map(str, years))}")
        
        # Get the most recent year's data
        latest_year = years[0]
        revenue = company.get_financial_kpi_for_year(latest_year, "revenue")
        employees = company.get_financial_kpi_for_year(latest_year, "employees")
        
        print(f"  Latest year ({latest_year}):")
        print(f"    Revenue: {revenue}")
        print(f"    Employees: {employees}")
        
        # Balance sheet example
        balance_sheet = company.get_balance_sheet_for_year(latest_year)
        if balance_sheet:
            print(f"  Balance Sheet ({latest_year}):")
            accounts = balance_sheet.get("balance_sheet_accounts", [])
            if accounts and len(accounts) > 0:
                assets = accounts[0]
                print(f"    Total Assets: {assets.get('value')}")
    else:
        print("  No financial data available")
    
    # Industry information
    print("\n🏭 Industry Information:")
    if company.wz2008_codes:
        for code in company.wz2008_codes:
            print(f"  {code.get('code')} - {code.get('label')}")
    
    # Products and Services
    if company.products_and_services:
        print("\n📦 Products and Services:")
        for product in company.products_and_services:
            print(f"  {product}")
    
    print("\n✅ Example completed")

if __name__ == "__main__":
    main()
