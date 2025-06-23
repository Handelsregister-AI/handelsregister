#!/usr/bin/env python3
"""
Example script demonstrating how to download official PDF documents from Handelsregister.

This script shows how to:
1. Search for a company
2. Download different types of documents (shareholders list, current/historical excerpts)
3. Handle errors appropriately

To run:
python document_example.py
"""
import os
from handelsregister import Handelsregister, Company
from handelsregister.exceptions import HandelsregisterError

# Set your API key (or use environment variable HANDELSREGISTER_API_KEY)
API_KEY = os.getenv("HANDELSREGISTER_API_KEY", "your_api_key_here")

def download_documents_using_client():
    """Example using the Handelsregister client directly."""
    print("🔍 Example 1: Using Handelsregister client directly")
    
    # Initialize the client
    client = Handelsregister(api_key=API_KEY)
    
    # First, search for a company to get the entity_id
    print("\n  Searching for company...")
    result = client.fetch_organization(q="Konux GmbH München")
    
    company_name = result.get("name", "Unknown")
    entity_id = result.get("entity_id")
    
    if not entity_id:
        print("  ❌ Could not find entity_id for the company")
        return
    
    print(f"  ✅ Found: {company_name}")
    print(f"  Entity ID: {entity_id}")
    
    # Download shareholders list
    try:
        print("\n  📄 Downloading shareholders list...")
        client.fetch_document(
            company_id=entity_id,
            document_type="shareholders_list",
            output_file="konux_shareholders.pdf"
        )
        print("  ✅ Saved to: konux_shareholders.pdf")
    except HandelsregisterError as e:
        print(f"  ❌ Error downloading shareholders list: {e}")
    
    # Download current excerpts (AD - Aktuelle Daten)
    try:
        print("\n  📄 Downloading current excerpts (AD)...")
        client.fetch_document(
            company_id=entity_id,
            document_type="AD",
            output_file="konux_current.pdf"
        )
        print("  ✅ Saved to: konux_current.pdf")
    except HandelsregisterError as e:
        print(f"  ❌ Error downloading current excerpts: {e}")
    
    # Download historical excerpts (CD - Chronologische Daten)
    try:
        print("\n  📄 Downloading historical excerpts (CD)...")
        client.fetch_document(
            company_id=entity_id,
            document_type="CD",
            output_file="konux_history.pdf"
        )
        print("  ✅ Saved to: konux_history.pdf")
    except HandelsregisterError as e:
        print(f"  ❌ Error downloading historical excerpts: {e}")


def download_documents_using_company():
    """Example using the Company class."""
    print("\n\n🔍 Example 2: Using Company class")
    
    # Initialize a Company instance
    print("\n  Searching for company...")
    company = Company("OroraTech GmbH München")
    
    print(f"  ✅ Found: {company.name}")
    print(f"  Registration: {company.registration_number}")
    print(f"  Entity ID: {company.entity_id}")
    
    # Download documents using the Company instance
    try:
        print("\n  📄 Downloading shareholders list...")
        company.fetch_document(
            document_type="shareholders_list",
            output_file="ororatech_shareholders.pdf"
        )
        print("  ✅ Saved to: ororatech_shareholders.pdf")
    except HandelsregisterError as e:
        print(f"  ❌ Error: {e}")
    
    # Example: Get PDF content as bytes (without saving to file)
    try:
        print("\n  📄 Getting current excerpts as bytes...")
        pdf_bytes = company.fetch_document(document_type="AD")
        print(f"  ✅ Received {len(pdf_bytes)} bytes of PDF data")
        
        # You can now process the PDF bytes as needed
        # For example, save with a custom name:
        with open("ororatech_custom_name.pdf", "wb") as f:
            f.write(pdf_bytes)
        print("  ✅ Saved to: ororatech_custom_name.pdf")
    except HandelsregisterError as e:
        print(f"  ❌ Error: {e}")


def batch_download_example():
    """Example of downloading documents for multiple companies."""
    print("\n\n🔍 Example 3: Batch download for multiple companies")
    
    client = Handelsregister(api_key=API_KEY)
    
    # List of companies to process
    companies = [
        "Konux GmbH München",
        "OroraTech GmbH München",
        "Isar Aerospace SE Ottobrunn"
    ]
    
    for company_query in companies:
        print(f"\n  Processing: {company_query}")
        try:
            # Search for company
            result = client.fetch_organization(q=company_query)
            company_name = result.get("name", "Unknown")
            entity_id = result.get("entity_id")
            
            if not entity_id:
                print(f"  ⚠️  No entity_id found for {company_query}")
                continue
            
            # Create safe filename
            safe_name = company_name.replace(" ", "_").replace("/", "_")
            
            # Download shareholders list
            output_file = f"{safe_name}_shareholders.pdf"
            client.fetch_document(
                company_id=entity_id,
                document_type="shareholders_list",
                output_file=output_file
            )
            print(f"  ✅ Downloaded: {output_file}")
            
        except HandelsregisterError as e:
            print(f"  ❌ Error processing {company_query}: {e}")
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")


def main():
    print("📚 Handelsregister Document Download Examples")
    print("=" * 50)
    
    # Run examples
    download_documents_using_client()
    download_documents_using_company()
    batch_download_example()
    
    print("\n\n✅ Examples completed!")
    print("\nNote: The availability of documents depends on:")
    print("  - Your API subscription level")
    print("  - The specific company and document type")
    print("  - Whether the documents exist in the registry")


if __name__ == "__main__":
    main()