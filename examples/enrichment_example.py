#!/usr/bin/env python3
"""
Example script demonstrating the data enrichment functionality.

This script shows how to:
1. Create a sample JSON file with company data
2. Enrich that data with information from the Handelsregister.ai API
3. Save the results as snapshots
4. Examine the enriched data

To run:
python enrichment_example.py
"""
import os
import json
import tempfile
from pathlib import Path
from handelsregister import Handelsregister

# Set your API key (or use environment variable HANDELSREGISTER_API_KEY)
API_KEY = os.getenv("HANDELSREGISTER_API_KEY", "your_api_key_here")

# Sample company data
SAMPLE_COMPANIES = [
    {"id": "1", "company_name": "KONUX GmbH", "city": "München"},
    {"id": "2", "company_name": "OroraTech GmbH", "city": "München"},
    {"id": "3", "company_name": "Isar Aerospace SE", "city": "Ottobrunn"},
    {"id": "4", "company_name": "Celonis SE", "city": "München"},
    {"id": "5", "company_name": "Personio SE", "city": "München"},
]

def main():
    # Create client
    client = Handelsregister(api_key=API_KEY)
    print(f"🔑 Initialized Handelsregister client")
    
    # Create temporary directory for our example
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create input file with companies
        input_file = temp_path / "companies.json"
        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_COMPANIES, f, indent=2)
        print(f"📄 Created sample data file: {input_file}")
        
        # Create snapshot directory
        snapshot_dir = temp_path / "snapshots"
        snapshot_dir.mkdir(exist_ok=True)
        print(f"📁 Created snapshot directory: {snapshot_dir}")
        
        # Enrich the data
        print("\n🔍 Enriching company data...")
        client.enrich(
            file_path=str(input_file),
            input_type="json",
            query_properties={
                "name": "company_name",    # Use the "company_name" field for the name part of the query
                "location": "city"         # Use the "city" field for the location part of the query
            },
            snapshot_dir=str(snapshot_dir),
            snapshot_steps=2,              # Take snapshots every 2 items
            params={
                "features": [
                    "related_persons",     # Include management information
                    "financial_kpi"        # Include financial KPIs
                ],
                "ai_search": "off"         # Disable AI-based search
            }
        )
        
        # Load the latest snapshot
        snapshots = sorted(snapshot_dir.glob("snapshot_*.json"))
        if snapshots:
            latest_snapshot = snapshots[-1]
            print(f"\n📊 Loaded latest snapshot: {latest_snapshot.name}")
            
            with open(latest_snapshot, "r", encoding="utf-8") as f:
                enriched_data = json.load(f)
            
            # Show summary of enriched data
            print("\n📋 Enrichment Results:")
            for item in enriched_data:
                company_name = item.get("company_name", "Unknown")
                result = item.get("_handelsregister_result", {})
                
                # Check if enrichment was successful
                if result:
                    name = result.get("name", "Unknown")
                    status = result.get("status", "Unknown")
                    reg_num = result.get("registration", {}).get("register_number", "Unknown")
                    print(f"  ✅ {company_name}: Found as {name}, Status: {status}, Reg: {reg_num}")
                    
                    # Show some related persons if available
                    related = result.get("related_persons", {}).get("current", [])
                    if related:
                        print(f"     👥 Current related persons: {len(related)}")
                else:
                    print(f"  ❌ {company_name}: No data found or error during enrichment")
        
        print("\n✅ Example completed")
        print(f"👉 Check {snapshot_dir} for the snapshot files (they will be deleted when this script exits)")
        print("   To keep them, use a permanent directory instead of a temporary one.")

if __name__ == "__main__":
    main()
