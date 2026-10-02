#!/usr/bin/env python3
"""Read deep shareholders on a Max plan (5 base + 80 feature credits).

Set HANDELSREGISTER_API_KEY, then run:
    python examples/shareholders_deep_example.py <organization-entity-id>
"""

import argparse

from handelsregister import Company, OrganizationFeature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "entity_id", help="Organization entity_id from search-organizations"
    )
    args = parser.parse_args()
    company = Company(args.entity_id, features=[OrganizationFeature.SHAREHOLDERS_DEEP])
    if "shareholders_deep" not in company.data:
        print("Deep shareholder data was omitted. This feature requires Max.")
        return
    deep = company.shareholders_deep
    if not deep:
        print("No current shareholder entries available.")
        return
    print(f"{company.name}: {deep.record.date} ({deep.record.source})")
    for entry in deep.entries:
        percentage = "unknown" if entry.percentage is None else f"{entry.percentage:g}%"
        print(
            f"{entry.display_name}: {percentage}, since {entry.since} ({entry.since_basis})"
        )
        for share in entry.ownership.share_ranges:
            nominal = share.nominal_value
            amount = (
                "unknown" if nominal is None else f"{nominal.value} {nominal.currency}"
            )
            print(
                f"  Shares {share.from_number}–{share.to_number}: {share.count}, nominal value {amount} each"
            )
        if entry.holder.type == "JOINT":
            print(
                "  Joint community members:",
                ", ".join(
                    member.name or "Unknown member" for member in entry.holder.members
                ),
            )
    if deep.changes is not None:
        print(
            f"Compared with {deep.changes.compared_to}: {len(deep.changes.joined)} joined, "
            f"{len(deep.changes.left)} left, {len(deep.changes.changed)} changed"
        )
    print(f"Historical documents: {len(deep.history)}")


if __name__ == "__main__":
    main()
