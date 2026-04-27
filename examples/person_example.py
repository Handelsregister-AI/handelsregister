#!/usr/bin/env python3
"""
Example: look up a person profile via the /v1/fetch-person endpoint.

NOTE: The name/company below are fabricated for documentation purposes. Running
this example against the real API will not return an actual person — replace
``person_q`` and ``organization_q`` with a real German Handelsregister company
and one of its managing directors to see live data.

Run:
    python person_example.py
"""
import os

from handelsregister import Person


def main():
    # Fabricated example inputs — no match is expected from the live API.
    person = Person(
        person_q="Max Beispiel",
        organization_q="Musterwerk Industrie GmbH",
        features=["shareholdings"],
    )

    print(f"Name:            {person.name}")
    print(f"Canonical name:  {person.canonical_name}")
    print(f"Birth date:      {person.birth_date}")
    print(f"City:            {person.home_city}")
    print(f"LinkedIn:        {person.linkedin}")

    if person.bio:
        print("\nBio:")
        print(person.bio)

    print("\nHandelsregister roles:")
    for role in person.handelsregister_roles:
        role_label = (
            (role.get("role") or {}).get("en")
            or (role.get("role") or {}).get("de")
            or role.get("label", "")
        )
        start = role.get("start_date", "?")
        end = role.get("end_date") or "present"
        print(f"  - {role.get('name', '')}: {role_label} ({start} – {end})")

    shareholdings = person.shareholdings
    if shareholdings:
        print("\nShareholdings:")
        for entry in shareholdings.current:
            share = f"{entry.percentage}%" if entry.percentage is not None else "?"
            amount = entry.contribution_amount
            currency = entry.contribution_currency
            parts = [entry.organization_name, share]
            if amount is not None:
                parts.append(f"{amount} {currency}".strip())
            if entry.as_of:
                parts.append(f"as of {entry.as_of}")
            print("  - " + " | ".join(parts))

    print(f"\nCredits spent on this call: {person.request_credit_cost}")


if __name__ == "__main__":
    main()
