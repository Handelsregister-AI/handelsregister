import argparse
import json
from typing import List, Optional, Any

from .client import Handelsregister

DEFAULT_FEATURES = [
    "related_persons",
    "financial_kpi",
    "balance_sheet_accounts",
    "profit_and_loss_account",
    "publications",
]

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.console import Group
    RICH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    Console = None
    Table = None
    Panel = None
    Group = None
    RICH_AVAILABLE = False


def parse_query_properties(props: List[str]):
    mapping = {}
    for p in props:
        if '=' in p:
            k, v = p.split('=', 1)
            mapping[k] = v
    return mapping


def _display_result(client: Handelsregister, result: dict) -> None:
    """Pretty-print the API result."""
    summary = client._format_flat_result(result)

    if RICH_AVAILABLE:
        console = Console()
        console.print(Panel(summary, title="Company", expand=False, style="cyan"))

        profile = Table(title="Profile", show_header=False)
        if result.get("legal_form"):
            profile.add_row("Legal Form", str(result.get("legal_form")))
        if result.get("purpose"):
            profile.add_row("Purpose", str(result.get("purpose")))
        addr = result.get("address", {})
        addr_parts = [addr.get("street"), f"{addr.get('postal_code', '')} {addr.get('city', '')}".strip(), addr.get("country_code")]
        addr_str = ", ".join(filter(None, addr_parts)).strip()
        if addr_str:
            profile.add_row("Address", addr_str)
        contact = result.get("contact_data", {})
        if contact.get("website"):
            profile.add_row("Website", contact.get("website"))
        if contact.get("phone_number"):
            profile.add_row("Phone", contact.get("phone_number"))

        industry_info = result.get("industry_classification", {})
        industries = []
        if isinstance(industry_info, dict):
            for _, entries in industry_info.items():
                if isinstance(entries, list):
                    for entry in entries:
                        code = entry.get("code")
                        label = entry.get("label")
                        if code and label:
                            industries.append(f"{code} {label}")
                        elif code:
                            industries.append(code)
                        elif label:
                            industries.append(label)
                elif isinstance(entries, dict):
                    code = entries.get("code")
                    label = entries.get("label")
                    if code and label:
                        industries.append(f"{code} {label}")
                    elif code:
                        industries.append(code)
                    elif label:
                        industries.append(label)
        if industries:
            profile.add_row("Industry", ", ".join(industries))

        management_table = Table(title="Management")
        management_table.add_column("Name")
        management_table.add_column("Role")
        current_people = result.get("related_persons", {}).get("current", [])
        for person in current_people:
            name = person.get("name", "")
            role = (
                person.get("role", {}).get("en", {}).get("long")
                or person.get("role", {}).get("de", {}).get("long")
                or person.get("label", "")
            )
            management_table.add_row(name, role)

        # Determine latest financial year
        years = {
            *(y.get("year") for y in result.get("financial_kpi", []) if y.get("year")),
            *(y.get("year") for y in result.get("balance_sheet_accounts", []) if y.get("year")),
            *(y.get("year") for y in result.get("profit_and_loss_account", []) if y.get("year")),
        }
        financial_table = None
        if years:
            latest = max(years)
            financial_table = Table(title=f"Financials {latest}")
            financial_table.add_column("Metric")
            financial_table.add_column("Value")

            def fmt_value(key: str, val: Any) -> str:
                if isinstance(val, (int, float)) and key.lower() not in {"employees", "year"}:
                    return f"{val:,.2f} €"
                if isinstance(val, (int, float)):
                    return f"{val:,}"
                return str(val)

            kpi = next((x for x in result.get("financial_kpi", []) if x.get("year") == latest), {})
            for k, v in kpi.items():
                if k != "year" and v is not None:
                    label = "Balance Sum" if k == "active_total" else k.replace("_", " ").title()
                    financial_table.add_row(label, fmt_value(k, v))

            bs = next((x for x in result.get("balance_sheet_accounts", []) if x.get("year") == latest), {})
            acc = bs.get("balance_sheet_accounts") or {}
            if isinstance(acc, dict):
                for k, v in acc.items():
                    financial_table.add_row(k.replace("_", " ").title(), fmt_value(k, v))

            pl = next((x for x in result.get("profit_and_loss_account", []) if x.get("year") == latest), {})
            pla = pl.get("profit_and_loss_accounts") or pl
            if isinstance(pla, dict):
                for k, v in pla.items():
                    if k != "year" and v is not None:
                        financial_table.add_row(k.replace("_", " ").title(), fmt_value(k, v))

        group_items = [profile]
        if management_table.row_count:
            group_items.append(management_table)
        if financial_table and financial_table.row_count:
            group_items.append(financial_table)

        console.print(Panel(Group(*group_items), title="Details", style="magenta"))
        console.print("Data provided by [bold]handelsregister.ai[/bold]")
    else:
        print(summary)



def main():
    parser = argparse.ArgumentParser(description="Handelsregister.ai CLI")
    subparsers = parser.add_subparsers(dest="command")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch a company")
    fetch_parser.add_argument("query", nargs="+")
    fetch_parser.add_argument("--feature", dest="features", action="append")
    fetch_parser.add_argument("--ai-search", dest="ai_search")

    enrich_parser = subparsers.add_parser("enrich", help="Enrich a data file")
    enrich_parser.add_argument("file_path")
    enrich_parser.add_argument("--input", dest="input_type", default="json")
    enrich_parser.add_argument("--snapshot-dir", dest="snapshot_dir", default="")
    enrich_parser.add_argument("--output", dest="output_file", default="")
    enrich_parser.add_argument("--output-format", dest="output_type", default="")
    enrich_parser.add_argument(
        "--query-properties",
        nargs="+",
        default=[],
        help="Mappings like name=company_name location=city",
    )
    enrich_parser.add_argument("--feature", dest="features", action="append")
    enrich_parser.add_argument("--ai-search", dest="ai_search")

    document_parser = subparsers.add_parser("document", help="Download company documents")
    document_parser.add_argument("query", nargs="+", help="Company search query")
    document_parser.add_argument(
        "--type", 
        dest="document_type", 
        required=True,
        choices=["shareholders_list", "AD", "CD"],
        help="Document type: shareholders_list (Gesellschafterliste), AD (Aktuelle Daten), CD (Chronologische Daten)"
    )
    document_parser.add_argument(
        "--output", 
        dest="output_file", 
        required=True,
        help="Output PDF file path"
    )
    document_parser.add_argument("--ai-search", dest="ai_search", default="off")

    args = parser.parse_args()

    client = Handelsregister()

    if args.command == "fetch":
        query_parts = list(args.query)
        output_json = False
        if query_parts and query_parts[0].lower() == "json":
            output_json = True
            query_parts = query_parts[1:]

        query_string = " ".join(query_parts)

        features: Optional[List[str]] = args.features if args.features else DEFAULT_FEATURES
        ai_search: str = args.ai_search if args.ai_search else "on-default"

        if RICH_AVAILABLE:
            console = Console()
            with console.status("[bold green]Fetching data..."):
                result = client.fetch_organization(
                    q=query_string,
                    features=features,
                    ai_search=ai_search,
                )
        else:
            print("Fetching data...", flush=True)
            result = client.fetch_organization(
                q=query_string,
                features=features,
                ai_search=ai_search,
            )

        if output_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _display_result(client, result)
    elif args.command == "enrich":
        query_props = parse_query_properties(args.query_properties)
        params = {}
        if args.features:
            params["features"] = args.features
        if args.ai_search:
            params["ai_search"] = args.ai_search
        client.enrich(
            file_path=args.file_path,
            input_type=args.input_type,
            query_properties=query_props,
            snapshot_dir=args.snapshot_dir,
            params=params,
            output_file=args.output_file,
            output_type=args.output_type,
        )
    elif args.command == "document":
        query_string = " ".join(args.query)
        
        if RICH_AVAILABLE:
            console = Console()
            with console.status("[bold green]Fetching company data..."):
                # First fetch the company to get entity_id
                result = client.fetch_organization(
                    q=query_string,
                    ai_search=args.ai_search,
                )
        else:
            print("Fetching company data...", flush=True)
            result = client.fetch_organization(
                q=query_string,
                ai_search=args.ai_search,
            )
        
        company_name = result.get("name", "Unknown Company")
        entity_id = result.get("entity_id")
        
        if not entity_id:
            if RICH_AVAILABLE:
                console.print("[red]Error: Could not find entity_id for the company[/red]")
            else:
                print("Error: Could not find entity_id for the company")
            return
        
        if RICH_AVAILABLE:
            console.print(f"[green]Found company:[/green] {company_name}")
            console.print(f"[green]Entity ID:[/green] {entity_id}")
            
            with console.status(f"[bold green]Downloading {args.document_type} document..."):
                client.fetch_document(
                    company_id=entity_id,
                    document_type=args.document_type,
                    output_file=args.output_file,
                )
            console.print(f"[green]✓ Document saved to:[/green] {args.output_file}")
        else:
            print(f"Found company: {company_name}")
            print(f"Entity ID: {entity_id}")
            print(f"Downloading {args.document_type} document...", flush=True)
            client.fetch_document(
                company_id=entity_id,
                document_type=args.document_type,
                output_file=args.output_file,
            )
            print(f"Document saved to: {args.output_file}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
