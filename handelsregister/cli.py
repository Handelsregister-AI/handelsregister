import argparse
import json
from typing import List

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

    fetch_parser = subparsers.add_parser("fetch", help="Fetch and display company information")
    fetch_parser.add_argument("query")
    fetch_parser.add_argument("--feature", dest="features", action="append")
    fetch_parser.add_argument("--ai-search", dest="ai_search")
    fetch_parser.add_argument(
        "--field",
        dest="fields",
        action="append",
        help="Fields to display from the result (dot notation)",
    )

    enrich_parser = subparsers.add_parser("enrich", help="Enrich a data file")
    enrich_parser.add_argument("file_path")
    enrich_parser.add_argument("--input", dest="input_type", default="json")
    enrich_parser.add_argument("--output", dest="output_path")
    enrich_parser.add_argument("--output-type", dest="output_type")
    enrich_parser.add_argument("--snapshot-dir", dest="snapshot_dir", default="")
    enrich_parser.add_argument(
        "--query-properties",
        nargs="+",
        default=[],
        help="Mappings like name=company_name location=city",
    )

    args = parser.parse_args()

    client = Handelsregister()

    if args.command == "fetch":
        result = client.fetch_organization(
            q=args.query,
            features=args.features,
            ai_search=args.ai_search,
        )
        fields = args.fields or ["name", "registration.register_number", "status"]

        def get_value(data, path):
            parts = path.split(".")
            val = data
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                if val is None:
                    break
            return val

        lines = []
        for field in fields:
            lines.append(f"{field}: {get_value(result, field)}")
        print("\n".join(lines))
    elif args.command == "enrich":
        query_props = parse_query_properties(args.query_properties)
        client.enrich(
            file_path=args.file_path,
            input_type=args.input_type,
            output_path=args.output_path,
            output_type=args.output_type,
            query_properties=query_props,
            snapshot_dir=args.snapshot_dir,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
