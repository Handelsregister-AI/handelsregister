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

    fetch_parser = subparsers.add_parser("fetch", help="Fetch a company")
    fetch_parser.add_argument("query")
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

    args = parser.parse_args()

    client = Handelsregister()

    if args.command == "fetch":
        result = client.fetch_organization(
            q=args.query,
            features=args.features,
            ai_search=args.ai_search,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
