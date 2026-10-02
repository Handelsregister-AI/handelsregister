#!/usr/bin/env python3
"""Inspect activity accounts on Max and financial provenance on every tier.

Set HANDELSREGISTER_API_KEY, then run:
    python examples/activity_financials_example.py <query-or-entity-id> --year 2023

Each financial feature costs 3 credits, in addition to the 5-credit lookup.
Activity statements need no extra flag and incur no extra feature charge.
"""

import argparse

from handelsregister import Company, OrganizationFeature


def print_accounts(roots, prefix=""):
    for account in roots:
        print(f"{prefix}{account.name_text()}: {account.value}")
        print_accounts(account.children, prefix + "  ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Company query or entity_id")
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    company = Company(
        args.query,
        features=[
            OrganizationFeature.BALANCE_SHEET_ACCOUNTS,
            OrganizationFeature.PROFIT_AND_LOSS_ACCOUNT,
        ],
    )
    statements = (
        (
            "Balance sheet",
            company.get_balance_sheet_entry_for_year(args.year),
            "balance_sheet_entries",
        ),
        (
            "P&L",
            company.get_profit_and_loss_entry_for_year(args.year),
            "profit_and_loss_entries",
        ),
    )
    for label, statement, accounts_property in statements:
        if statement is None:
            print(f"No {label} for {args.year}")
            continue
        source = statement.provenance
        print(
            f"{label} {args.year}: {source.statement_type}, {source.period_start}–{source.period_end}"
        )
        print(
            f"Exempt subsidiary: {source.exempt_subsidiary}; parent: {source.parent_organization}"
        )
        print_accounts(getattr(statement, accounts_property))
        for activity in statement.activity_statements:
            source = activity.provenance
            print(
                f"Activity {label}: {activity.name_text()} ({activity.name_in_report})"
            )
            print(
                f"Source: {source.statement_type}, {source.period_start}–{source.period_end}"
            )
            print_accounts(getattr(activity, accounts_property))
        if not statement.activity_statements:
            print("No activity statements returned for this year (available on Max).")


if __name__ == "__main__":
    main()
