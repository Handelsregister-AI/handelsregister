import argparse
import json
import sys
from typing import List, Optional, Any

from .client import Handelsregister
from .constants import (
    DOCUMENT_TYPES,
    ORGANIZATION_FEATURES,
    SEARCH_ORGANIZATIONS_MAX_LIMIT,
    SEARCH_SORT_FIELDS,
    SORT_ORDERS,
)
from .exceptions import HandelsregisterError, SubscriptionRequiredError
from .models import CapitalInfo, FinancialStatement
from .shareholders import ShareholdersDeep

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


def _format_financial_value(key: str, value: Any) -> str:
    metric = key.lower()
    dimensionless = (
        metric.endswith(("_ratio", "_margin", "_intensity", "_rate", "_coverage"))
        or "_to_" in metric
    )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if dimensionless:
            return f"{value:,.4g}"
        if metric in {"employees", "year"}:
            return f"{value:,}"
        return f"{value:,.2f} €"
    return "" if value is None else str(value)


def _account_display_rows(accounts, prefix=""):
    rows = []
    for account in accounts:
        label = prefix + (account.name_text() or "Unnamed account")
        rows.append((label, _format_financial_value("amount", account.value)))
        rows.extend(_account_display_rows(account.children, label + " > "))
    return rows


def _provenance_text(provenance):
    parts = []
    if provenance.statement_type:
        parts.append(provenance.statement_type)
    if provenance.period_start or provenance.period_end:
        parts.append(f"{provenance.period_start or '?'}–{provenance.period_end or '?'}")
    if provenance.exempt_subsidiary is not None:
        parts.append(
            f"Exempt subsidiary: {'yes' if provenance.exempt_subsidiary else 'no'}"
        )
    if provenance.parent_organization is not None:
        parent = provenance.parent_organization
        parts.append(
            "Parent: "
            + str(
                parent.get("name")
                or parent.get("entity_id")
                or json.dumps(parent, ensure_ascii=False)
            )
        )
    return "; ".join(parts)


def _financial_display(result, financial_year):
    features = (
        ("financial_kpi", "KPIs", None),
        ("balance_sheet_accounts", "Balance sheet", "balance_sheet_entries"),
        ("profit_and_loss_account", "P&L", "profit_and_loss_entries"),
    )
    statements = {}
    for key, _, _ in features:
        payload = result.get(key)
        statements[key] = (
            [
                FinancialStatement.from_payload(row)
                for row in payload
                if isinstance(row, dict)
            ]
            if isinstance(payload, list)
            else []
        )
    years = {
        row.year for rows in statements.values() for row in rows if row.year is not None
    }
    selected_year = (
        financial_year if financial_year is not None else max(years) if years else None
    )
    metrics = []
    activities = []
    for key, label, accounts_property in features:
        for statement in statements[key]:
            if statement.year != selected_year:
                continue
            if accounts_property:
                metrics.extend(
                    (label + " > " + name, value)
                    for name, value in _account_display_rows(
                        getattr(statement, accounts_property)
                    )
                )
            for metric, value in statement.metrics.items():
                if value is not None:
                    name = (
                        "Balance Sum"
                        if metric == "active_total"
                        else metric.replace("_", " ").title()
                    )
                    metrics.append((name, _format_financial_value(metric, value)))
            if statement.provenance:
                metrics.append(
                    (label + " source", _provenance_text(statement.provenance))
                )
            if accounts_property:
                for activity in statement.activity_statements:
                    title = f"Activity {label} {selected_year}: {activity.name_text() or 'Unnamed activity'}"
                    rows = _account_display_rows(getattr(activity, accounts_property))
                    rows.insert(
                        0, ("Activity", activity.name_text() or "Unnamed activity")
                    )
                    if activity.name_in_report:
                        rows.insert(1, ("In report", activity.name_in_report))
                    if activity.provenance:
                        rows.insert(
                            0, ("Source", _provenance_text(activity.provenance))
                        )
                    activities.append((title, rows))
    return selected_year, metrics, activities


def _display_result(client: Handelsregister, result: dict, financial_year: Optional[int] = None) -> None:
    """Pretty-print the API result."""
    summary = client._format_flat_result(result)
    deep = ShareholdersDeep.from_payload(result.get("shareholders_deep"))
    capital = CapitalInfo.from_payload(result.get("capital")).current
    selected_year, financial_rows, activity_tables = _financial_display(result, financial_year)
    shareholder_rows = []
    for entry in deep.entries:
        ranges = []
        for share in entry.ownership.share_ranges:
            if share.from_number is not None and share.to_number is not None:
                ranges.append(
                    str(share.from_number)
                    if share.from_number == share.to_number
                    else f"{share.from_number}–{share.to_number}"
                )
        name = entry.display_name
        if entry.holder.type == "JOINT" and entry.holder.members:
            members = ", ".join(
                member.name or "Unknown member" for member in entry.holder.members
            )
            name += f" ({members})"
        shareholder_rows.append(
            (
                name,
                entry.role or "",
                "" if entry.percentage is None else f"{entry.percentage:g}%",
                ", ".join(ranges),
                entry.since or "",
                entry.since_basis or "",
            )
        )

    if RICH_AVAILABLE:
        console = Console()
        console.print(Panel(summary, title="Company", expand=False, style="cyan"))

        profile = Table(title="Profile", show_header=False)
        if result.get("legal_form"):
            profile.add_row("Legal Form", str(result.get("legal_form")))
        if result.get("purpose"):
            profile.add_row("Purpose", str(result.get("purpose")))
        if capital is not None:
            profile.add_row("Capital", f"{capital.amount} {capital.currency or ''} ({capital.kind or ''})")
        representation = result.get("representation_scheme") or {}
        active_representation = (
            representation.get("current")
            or representation.get("latest")
            or []
        )
        if active_representation:
            profile.add_row("Representation", "\n".join(active_representation))
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

        financial_table = None
        if financial_rows:
            financial_table = Table(title=f"Financials {selected_year}")
            financial_table.add_column("Metric")
            financial_table.add_column("Value")
            for row in financial_rows:
                financial_table.add_row(*row)

        group_items = [profile]
        if management_table.row_count:
            group_items.append(management_table)
        if financial_table and financial_table.row_count:
            group_items.append(financial_table)
        for title, rows in activity_tables:
            activity_table = Table(title=title)
            activity_table.add_column("Account")
            activity_table.add_column("Value")
            for row in rows:
                activity_table.add_row(*row)
            group_items.append(activity_table)
        if shareholder_rows:
            shareholder_table = Table(title=f"Deep Shareholders ({deep.record.date or deep.record.source or 'current'})")
            for column in ("Holder", "Role", "Ownership", "Share numbers", "Since", "Since basis"):
                shareholder_table.add_column(column)
            for row in shareholder_rows:
                shareholder_table.add_row(*row)
            group_items.append(shareholder_table)

        ma_data = result.get("mergers_and_acquisitions") or {}
        ma_summary = ma_data.get("summary") if isinstance(ma_data, dict) else {}
        if isinstance(ma_summary, dict) and ma_summary:
            ma_table = Table(title="Mergers & Acquisitions", show_header=False)
            ma_table.add_row(
                "Transactions",
                str(ma_summary.get("total_transactions", 0)),
            )
            if ma_summary.get("first_date"):
                ma_table.add_row("First", str(ma_summary["first_date"]))
            if ma_summary.get("last_date"):
                ma_table.add_row("Last", str(ma_summary["last_date"]))
            group_items.append(ma_table)

        console.print(Panel(Group(*group_items), title="Details", style="magenta"))
        console.print("Data provided by [bold]handelsregister.ai[/bold]")
    else:
        print(summary)
        if financial_rows:
            print(f"Financials {selected_year}:")
            for name, value in financial_rows:
                print(f"{name}: {value}")
        for title, rows in activity_tables:
            print(title + ":")
            for name, value in rows:
                print(f"{name}: {value}")
        if capital is not None:
            print(f"Capital: {capital.amount} {capital.currency or ''} ({capital.kind or ''})")
        if shareholder_rows:
            print(f"Deep Shareholders ({deep.record.date or deep.record.source or 'current'}):")
            for row in shareholder_rows:
                print(" | ".join(row))


def _display_person(result: dict) -> None:
    """Pretty-print a person profile."""
    name = result.get("name") or result.get("name_parts", {}).get("canonical_name", "")
    bio = result.get("bio") or ""
    roles = result.get("handelsregister_roles", []) or []
    affiliations = result.get("affiliations", []) or []

    if RICH_AVAILABLE:
        console = Console()
        console.print(Panel(name, title="Person", expand=False, style="cyan"))

        profile = Table(title="Profile", show_header=False)
        if result.get("birth_date"):
            profile.add_row("Born", str(result.get("birth_date")))
        location = result.get("location", {}) or {}
        home = location.get("home") or {}
        if isinstance(home, dict) and home.get("city"):
            profile.add_row("City", home.get("city"))
        if result.get("expertise"):
            profile.add_row("Expertise", ", ".join(result["expertise"]))
        profiles_data = result.get("profiles", {}) or {}
        for key in ("linkedin", "github"):
            if profiles_data.get(key):
                profile.add_row(key.title(), profiles_data[key])
        if bio:
            profile.add_row("Bio", bio)

        role_table = Table(title="Handelsregister Roles")
        role_table.add_column("Company")
        role_table.add_column("Role")
        role_table.add_column("Start")
        role_table.add_column("End")
        for r in roles:
            role_label = (
                (r.get("role") or {}).get("en")
                or (r.get("role") or {}).get("de")
                or r.get("label", "")
            )
            role_table.add_row(
                r.get("name", ""),
                str(role_label),
                str(r.get("start_date") or ""),
                str(r.get("end_date") or ""),
            )

        affiliation_table = Table(title="Affiliations")
        affiliation_table.add_column("Organization")
        affiliation_table.add_column("Relation")
        for a in affiliations:
            affiliation_table.add_row(
                a.get("organization", ""),
                a.get("relation", ""),
            )

        group_items = [profile]
        if role_table.row_count:
            group_items.append(role_table)
        if affiliation_table.row_count:
            group_items.append(affiliation_table)

        console.print(Panel(Group(*group_items), title="Details", style="magenta"))
        console.print("Data provided by [bold]handelsregister.ai[/bold]")
    else:
        print(name)
        if bio:
            print(bio)
        for r in roles:
            role_label = (
                (r.get("role") or {}).get("en")
                or (r.get("role") or {}).get("de")
                or r.get("label", "")
            )
            print(f"- {r.get('name', '')}: {role_label}")


def _print_json(result: Any) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _display_monitors(result: dict) -> None:
    """Pretty-print a monitor list."""
    monitors = result.get("monitors", []) or []
    if RICH_AVAILABLE:
        console = Console()
        table = Table(title=f"Monitors ({len(monitors)})")
        table.add_column("ID")
        table.add_column("Label")
        table.add_column("Entity")
        table.add_column("Interval")
        table.add_column("Status")
        table.add_column("Next poll")
        for monitor in monitors:
            table.add_row(
                monitor.get("id", ""),
                monitor.get("label") or "",
                monitor.get("entity_id", ""),
                f"{monitor.get('poll_interval_days', '')}d",
                monitor.get("status", ""),
                str(monitor.get("next_poll_at") or ""),
            )
        console.print(table)
    else:
        for monitor in monitors:
            print(
                f"- {monitor.get('id', '')}  {monitor.get('label') or ''} "
                f"[{monitor.get('status', '')}]"
            )


def _display_webhook_endpoints(result: dict) -> None:
    """Pretty-print a webhook endpoint list."""
    endpoints = result.get("endpoints", []) or []
    if RICH_AVAILABLE:
        console = Console()
        table = Table(title=f"Webhook endpoints ({len(endpoints)})")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("URL")
        table.add_column("Status")
        table.add_column("Failures")
        for endpoint in endpoints:
            table.add_row(
                endpoint.get("id", ""),
                endpoint.get("name", ""),
                endpoint.get("url", ""),
                endpoint.get("status", ""),
                str(endpoint.get("consecutive_failures", "")),
            )
        console.print(table)
    else:
        for endpoint in endpoints:
            print(
                f"- {endpoint.get('id', '')}  {endpoint.get('name', '')} "
                f"[{endpoint.get('status', '')}]"
            )


def _display_search_results(result: dict) -> None:
    """Pretty-print search results."""
    results = result.get("results", []) or []
    total = result.get("total")

    if RICH_AVAILABLE:
        console = Console()
        table = Table(title=f"Search results ({len(results)} of {total})")
        table.add_column("Name")
        table.add_column("Registration")
        table.add_column("City")
        for item in results:
            reg = item.get("registration", {}) or {}
            reg_str = " ".join(
                str(p) for p in (reg.get("court"), reg.get("register_type"), reg.get("register_number")) if p
            )
            addr = item.get("address", {}) or {}
            table.add_row(
                item.get("name", ""),
                reg_str,
                addr.get("city", ""),
            )
        console.print(table)
    else:
        for item in results:
            print(f"- {item.get('name', '')}  [{item.get('entity_id', '')}]")
        if total is not None:
            print(f"Total: {total}")


def _main():
    parser = argparse.ArgumentParser(description="Handelsregister.ai CLI")
    subparsers = parser.add_subparsers(dest="command")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch a company")
    fetch_parser.add_argument("query", nargs="+")
    fetch_parser.add_argument(
        "--feature",
        dest="features",
        action="append",
        help="Organization feature; repeat as needed. Supported: "
        + ", ".join(ORGANIZATION_FEATURES),
    )
    fetch_parser.add_argument("--ai-search", dest="ai_search")
    fetch_parser.add_argument("--realtime-mode", dest="realtime_mode")
    fetch_parser.add_argument(
        "--financial-year", type=int,
        help="Financial year to display, including Max activity statements (default: latest). Does not change the API request.",
    )

    person_parser = subparsers.add_parser("person", help="Fetch a person profile")
    person_parser.add_argument(
        "--person", dest="person_q", required=True, help="Person name (min. 2 chars)"
    )
    person_parser.add_argument(
        "--organization",
        dest="organization_q",
        required=True,
        help="Organization context for disambiguation",
    )
    person_parser.add_argument(
        "--feature",
        dest="features",
        action="append",
        help="Additional features (currently: shareholdings)",
    )
    person_parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Emit raw JSON instead of a formatted view",
    )

    search_parser = subparsers.add_parser("search", help="Search organizations")
    search_parser.add_argument("query", nargs="*")
    search_parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Result offset for pagination (default: 0)",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "Results per request "
            f"(default: 10, maximum: {SEARCH_ORGANIZATIONS_MAX_LIMIT})"
        ),
    )
    search_parser.add_argument(
        "--postal-code",
        dest="postal_code",
        help="Filter by postal code",
    )
    search_parser.add_argument(
        "--filters",
        dest="filters_json",
        help="Complete search filter object as JSON",
    )
    search_parser.add_argument(
        "--filter",
        dest="filter_items",
        action="append",
        default=[],
        help="One filter as key=value; values may be JSON. Repeat as needed.",
    )
    search_parser.add_argument(
        "--ai-mode",
        dest="ai_mode",
        help="AI-assisted search mode (on-default)",
    )
    search_parser.add_argument(
        "--sort",
        choices=SEARCH_SORT_FIELDS,
        help="Sort field for organization results",
    )
    search_parser.add_argument(
        "--order",
        choices=SORT_ORDERS,
        help="Sort direction (asc or desc)",
    )
    search_parser.add_argument(
        "--match-context",
        action="store_true",
        default=None,
        help="Include register-data values that matched advanced filters",
    )
    search_parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Emit raw JSON instead of a formatted view",
    )

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
        choices=DOCUMENT_TYPES,
        help=(
            "Document type: shareholders_list (Gesellschafterliste), "
            "articles_of_association (Gesellschaftsvertrag/Satzung), "
            "AD (Aktuelle Daten), CD (Chronologische Daten), "
            "SI (Strukturierte Informationen/XML)"
        ),
    )
    document_parser.add_argument(
        "--output",
        dest="output_file",
        required=True,
        help="Output document path (.pdf, or .xml for SI)",
    )
    document_parser.add_argument("--ai-search", dest="ai_search", default="off")

    monitors_parser = subparsers.add_parser(
        "monitors", help="Manage organization monitors"
    )
    monitors_sub = monitors_parser.add_subparsers(dest="monitors_action")

    mon_pricing = monitors_sub.add_parser(
        "pricing", help="Show the current pricing policy and estimate"
    )
    mon_pricing.add_argument(
        "--interval",
        dest="poll_interval_days",
        type=int,
        help="Poll interval in days (1-30) used for the estimate",
    )

    mon_list = monitors_sub.add_parser("list", help="List monitors")
    mon_list.add_argument("--json", dest="output_json", action="store_true")

    mon_show = monitors_sub.add_parser("show", help="Show one monitor with runs")
    mon_show.add_argument("monitor_id", help="Monitor id (mon_...)")

    mon_create = monitors_sub.add_parser("create", help="Create a monitor")
    mon_create.add_argument("--entity-id", dest="entity_id", required=True)
    mon_create.add_argument(
        "--interval", dest="poll_interval_days", type=int, required=True
    )
    mon_create.add_argument(
        "--endpoint",
        dest="endpoint_ids",
        action="append",
        required=True,
        help="Webhook endpoint id (wep_...); repeat as needed",
    )
    mon_create.add_argument("--label", dest="label")
    mon_create.add_argument("--idempotency-key", dest="idempotency_key")

    mon_update = monitors_sub.add_parser("update", help="Change the poll interval")
    mon_update.add_argument("monitor_id")
    mon_update.add_argument(
        "--interval", dest="poll_interval_days", type=int, required=True
    )
    mon_update.add_argument("--idempotency-key", dest="idempotency_key")

    mon_pause = monitors_sub.add_parser("pause", help="Pause a monitor")
    mon_pause.add_argument("monitor_id")
    mon_pause.add_argument("--idempotency-key", dest="idempotency_key")

    mon_resume = monitors_sub.add_parser("resume", help="Resume a monitor")
    mon_resume.add_argument("monitor_id")
    mon_resume.add_argument("--idempotency-key", dest="idempotency_key")

    mon_archive = monitors_sub.add_parser("archive", help="Archive a monitor")
    mon_archive.add_argument("monitor_id")
    mon_archive.add_argument("--idempotency-key", dest="idempotency_key")

    webhooks_parser = subparsers.add_parser(
        "webhooks", help="Manage webhook endpoints, deliveries and events"
    )
    webhooks_sub = webhooks_parser.add_subparsers(dest="webhooks_action")

    wh_list = webhooks_sub.add_parser("list", help="List webhook endpoints")
    wh_list.add_argument("--json", dest="output_json", action="store_true")

    wh_create = webhooks_sub.add_parser("create", help="Register a webhook endpoint")
    wh_create.add_argument("--name", required=True)
    wh_create.add_argument("--url", required=True, help="Public HTTPS URL (port 443)")
    wh_create.add_argument(
        "--header",
        dest="header_items",
        action="append",
        default=[],
        help="Custom header as name=value; repeat as needed",
    )
    wh_create.add_argument("--idempotency-key", dest="idempotency_key")

    for action_name, action_help in [
        ("verify", "Send the signed verification challenge"),
        ("test", "Send a signed test delivery"),
        ("rotate-secret", "Rotate the signing secret"),
        ("enable", "Enable a verified endpoint"),
        ("disable", "Disable an endpoint"),
        ("archive", "Archive an endpoint"),
    ]:
        action_parser = webhooks_sub.add_parser(action_name, help=action_help)
        action_parser.add_argument("endpoint_id", help="Endpoint id (wep_...)")
        action_parser.add_argument("--idempotency-key", dest="idempotency_key")

    wh_deliveries = webhooks_sub.add_parser(
        "deliveries", help="List the newest 50 deliveries"
    )
    wh_deliveries.add_argument(
        "--endpoint", dest="endpoint_id", help="Filter by endpoint id (wep_...)"
    )

    wh_retry = webhooks_sub.add_parser(
        "retry-delivery", help="Retry a retained failed delivery"
    )
    wh_retry.add_argument("delivery_id", help="Delivery id (del_...)")
    wh_retry.add_argument("--idempotency-key", dest="idempotency_key")

    webhooks_sub.add_parser("events", help="List the newest 50 webhook events")

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
        realtime_mode: Optional[str] = args.realtime_mode

        if RICH_AVAILABLE:
            console = Console()
            with console.status("[bold green]Fetching data..."):
                result = client.fetch_organization(
                    q=query_string,
                    features=features,
                    ai_search=ai_search,
                    realtime_mode=realtime_mode,
                )
        else:
            print("Fetching data...", flush=True)
            result = client.fetch_organization(
                q=query_string,
                features=features,
                ai_search=ai_search,
                realtime_mode=realtime_mode,
            )

        if output_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _display_result(client, result, financial_year=args.financial_year)
    elif args.command == "person":
        if RICH_AVAILABLE:
            console = Console()
            with console.status("[bold green]Fetching person..."):
                result = client.fetch_person(
                    person_q=args.person_q,
                    organization_q=args.organization_q,
                    features=args.features,
                )
        else:
            print("Fetching person...", flush=True)
            result = client.fetch_person(
                person_q=args.person_q,
                organization_q=args.organization_q,
                features=args.features,
            )

        if args.output_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _display_person(result)
    elif args.command == "search":
        query_string = " ".join(args.query).strip() or None
        filters = {}
        if args.filters_json:
            try:
                parsed_filters = json.loads(args.filters_json)
            except json.JSONDecodeError as exc:
                search_parser.error(f"--filters must be valid JSON: {exc}")
            if not isinstance(parsed_filters, dict):
                search_parser.error("--filters must decode to a JSON object")
            filters.update(parsed_filters)
        for item in args.filter_items:
            if "=" not in item:
                search_parser.error("--filter values must use key=value")
            key, raw_value = item.split("=", 1)
            key = key.strip()
            if not key:
                search_parser.error("--filter key must not be empty")
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            filters[key] = value
        if args.postal_code:
            filters["postal_code"] = args.postal_code
        filters = filters or None

        if RICH_AVAILABLE:
            console = Console()
            with console.status("[bold green]Searching..."):
                result = client.search_organizations(
                    q=query_string,
                    skip=args.skip,
                    limit=args.limit,
                    filters=filters,
                    ai_mode=args.ai_mode,
                    sort=args.sort,
                    order=args.order,
                    match_context=args.match_context,
                )
        else:
            print("Searching...", flush=True)
            result = client.search_organizations(
                q=query_string,
                skip=args.skip,
                limit=args.limit,
                filters=filters,
                ai_mode=args.ai_mode,
                sort=args.sort,
                order=args.order,
                match_context=args.match_context,
            )

        if args.output_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _display_search_results(result)
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
    elif args.command == "monitors":
        action = args.monitors_action
        if action == "pricing":
            _print_json(
                client.get_monitoring_pricing(
                    poll_interval_days=args.poll_interval_days
                )
            )
        elif action == "list":
            result = client.list_monitors()
            if args.output_json:
                _print_json(result)
            else:
                _display_monitors(result)
        elif action == "show":
            _print_json(client.get_monitor(args.monitor_id))
        elif action == "create":
            _print_json(
                client.create_monitor(
                    entity_id=args.entity_id,
                    poll_interval_days=args.poll_interval_days,
                    endpoint_ids=args.endpoint_ids,
                    label=args.label,
                    idempotency_key=args.idempotency_key,
                )
            )
        elif action == "update":
            _print_json(
                client.update_monitor(
                    args.monitor_id,
                    poll_interval_days=args.poll_interval_days,
                    idempotency_key=args.idempotency_key,
                )
            )
        elif action == "pause":
            _print_json(
                client.pause_monitor(
                    args.monitor_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "resume":
            _print_json(
                client.resume_monitor(
                    args.monitor_id,
                    idempotency_key=args.idempotency_key,
                )
            )
        elif action == "archive":
            _print_json(
                client.archive_monitor(
                    args.monitor_id, idempotency_key=args.idempotency_key
                )
            )
        else:
            monitors_parser.print_help()
    elif args.command == "webhooks":
        action = args.webhooks_action
        if action == "list":
            result = client.list_webhook_endpoints()
            if args.output_json:
                _print_json(result)
            else:
                _display_webhook_endpoints(result)
        elif action == "create":
            custom_headers = {}
            for item in args.header_items:
                if "=" not in item:
                    wh_create.error("--header values must use name=value")
                header_name, header_value = item.split("=", 1)
                custom_headers[header_name.strip()] = header_value
            _print_json(
                client.create_webhook_endpoint(
                    name=args.name,
                    url=args.url,
                    headers=custom_headers or None,
                    idempotency_key=args.idempotency_key,
                )
            )
        elif action == "verify":
            _print_json(
                client.verify_webhook_endpoint(
                    args.endpoint_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "test":
            _print_json(
                client.test_webhook_endpoint(
                    args.endpoint_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "rotate-secret":
            _print_json(
                client.rotate_webhook_endpoint_secret(
                    args.endpoint_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "enable":
            _print_json(
                client.enable_webhook_endpoint(
                    args.endpoint_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "disable":
            _print_json(
                client.disable_webhook_endpoint(
                    args.endpoint_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "archive":
            _print_json(
                client.archive_webhook_endpoint(
                    args.endpoint_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "deliveries":
            _print_json(client.list_webhook_deliveries(endpoint_id=args.endpoint_id))
        elif action == "retry-delivery":
            _print_json(
                client.retry_webhook_delivery(
                    args.delivery_id, idempotency_key=args.idempotency_key
                )
            )
        elif action == "events":
            _print_json(client.list_webhook_events())
        else:
            webhooks_parser.print_help()
    else:
        parser.print_help()


def _format_cli_error(error: HandelsregisterError) -> str:
    """Render API failures without exposing a Python traceback."""
    if not isinstance(error, SubscriptionRequiredError):
        return f"Error: {error}"

    lines = [f"Plan required: {error}"]
    if error.required_plans:
        plans = ", ".join(plan.capitalize() for plan in error.required_plans)
        lines.append(f"Required plans: {plans}")
    if error.blocked_filters:
        lines.append("Blocked filters: " + ", ".join(error.blocked_filters))
    if error.blocked_features:
        lines.append("Blocked features: " + ", ".join(error.blocked_features))
    return "\n".join(lines)


def main():
    """Run the CLI and turn SDK errors into concise terminal messages."""
    try:
        _main()
    except HandelsregisterError as error:
        print(_format_cli_error(error), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
