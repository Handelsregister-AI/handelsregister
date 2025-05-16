import argparse
import json
from typing import Any, Callable, Dict, List

from .client import Handelsregister


def parse_query_properties(props: List[str]):
    mapping = {}
    for p in props:
        if '=' in p:
            k, v = p.split('=', 1)
            mapping[k] = v
    return mapping


def main():
    parser = argparse.ArgumentParser(description="Handelsregister.ai CLI")
    subparsers = parser.add_subparsers(dest="command")

    search_parser = subparsers.add_parser(
        "search", help="Search for a company and print a short summary"
    )
    search_parser.add_argument("query")
    search_parser.add_argument("--feature", dest="features", action="append")
    search_parser.add_argument("--ai-search", dest="ai_search")

    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch company details with custom fields"
    )
    fetch_parser.add_argument("query")
    fetch_parser.add_argument("--feature", dest="features", action="append")
    fetch_parser.add_argument("--ai-search", dest="ai_search")
    fetch_parser.add_argument(
        "--field",
        dest="fields",
        action="append",
        help="Fields to print (e.g. --field name --field status)",
    )

    enrich_parser = subparsers.add_parser("enrich", help="Enrich a data file")
    enrich_parser.add_argument("file_path")
    enrich_parser.add_argument("--input", dest="input_type", default="json")
    enrich_parser.add_argument("--snapshot-dir", dest="snapshot_dir", default="")
    enrich_parser.add_argument(
        "--query-properties",
        nargs="+",
        default=[],
        help="Mappings like name=company_name location=city",
    )

    args = parser.parse_args()

    client = Handelsregister()

    def format_output(data: Dict[str, Any], fields: List[str]) -> str:
        field_map: Dict[str, Callable[[Dict[str, Any]], str]] = {
            "name": lambda d: d.get("name", ""),
            "status": lambda d: d.get("status", ""),
            "registration": lambda d: (
                f"{d.get('registration', {}).get('register_type', '')} "
                f"{d.get('registration', {}).get('register_number', '')} "
                f"({d.get('registration', {}).get('court', '')})"
            ),
            "address": lambda d: (
                f"{d.get('address', {}).get('street', '')}, "
                f"{d.get('address', {}).get('postal_code', '')} "
                f"{d.get('address', {}).get('city', '')}, "
                f"{d.get('address', {}).get('country_code', '')}"
            ),
            "purpose": lambda d: d.get("purpose", ""),
        }

        lines = []
        for f in fields:
            func = field_map.get(f)
            if func:
                lines.append(f"{f.capitalize()}: {func(data)}")
        return "\n".join(lines)

    if args.command == "search":
        result = client.fetch_organization(
            q=args.query,
            features=args.features,
            ai_search=args.ai_search,
        )
        summary = format_output(result, ["name", "registration", "status"])
        print(summary)
    elif args.command == "fetch":
        result = client.fetch_organization(
            q=args.query,
            features=args.features,
            ai_search=args.ai_search,
        )
        fields = args.fields or ["name", "registration", "status", "address"]
        print(format_output(result, fields))
    elif args.command == "enrich":
        query_props = parse_query_properties(args.query_properties)
        client.enrich(
            file_path=args.file_path,
            input_type=args.input_type,
            query_properties=query_props,
            snapshot_dir=args.snapshot_dir,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
