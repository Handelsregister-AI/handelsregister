#!/usr/bin/env python3
"""Read typed audit information attached to annual reports.

Set HANDELSREGISTER_API_KEY, then run:
    python examples/audit_example.py "KONUX GmbH" --year 2024

Use --html to request HTML instead of Markdown. The requested report feature
costs 5 credits when data is returned, in addition to the 5-credit lookup.
Audit information needs no separate feature flag.
"""

import argparse

from handelsregister import Company, OrganizationFeature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Company query or entity_id")
    parser.add_argument(
        "--year", type=int, help="Display this financial year (default: latest)"
    )
    parser.add_argument("--html", action="store_true", help="Request HTML reports")
    args = parser.parse_args()
    feature = (
        OrganizationFeature.ANNUAL_FINANCIAL_STATEMENTS_HTML
        if args.html
        else OrganizationFeature.ANNUAL_FINANCIAL_STATEMENTS
    )
    company = Company(args.query, features=[feature])
    year = args.year
    if year is None and company.financial_years:
        year = company.financial_years[0]
    reports = company.get_annual_financial_statement_entries_for_year(
        year, html=args.html
    )
    if not reports:
        print("No annual reports returned for the selected year.")
    for report in reports:
        print(f"{company.name}: {report.year} / {report.document_type}")
        print(f"Report: {report.document_title} (published {report.document_date})")
        audit = report.audit
        if audit is None:
            print("Audit information: not available")
            continue
        print(
            f"Audit: {audit.kind}, subject: {audit.subject}, audited: {audit.audited}"
        )
        print(f"Accounting framework: {audit.accounting_framework}")
        auditor = audit.auditor
        if auditor is not None:
            print(f"Auditor: {auditor.name or 'Name not available'} ({auditor.type})")
            if auditor.entity_id is not None:
                print(f"Auditor entity ID: {auditor.entity_id}")
            if auditor.network is not None:
                print(f"Network: {auditor.network.name} ({auditor.network.key})")
            for signatory in auditor.signatories:
                name = " ".join(
                    part for part in (signatory.academic_title, signatory.name) if part
                )
                print(f"Signatory: {name}, qualification: {signatory.qualification}")
        if audit.signed is not None:
            print(f"Signed: {audit.signed.place}, {audit.signed.date}")


if __name__ == "__main__":
    main()
