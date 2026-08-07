#!/usr/bin/env python3
"""
Exercise the Account and Signals APIs.

Required environment variables:

    HANDELSREGISTER_API_KEY=...

Optional gateway configuration:

    HANDELSREGISTER_EXTRA_HEADERS_JSON='{"X-Gateway-Token": "..."}'

Optional for the API-key lifecycle test:

    HANDELSREGISTER_ADMIN_BEARER_TOKEN=...
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

from handelsregister import (
    APIError,
    AuthenticationError,
    Handelsregister,
    HandelsregisterError,
)


SENSITIVE_RESPONSE_FIELDS = {
    "accesstoken",
    "apikey",
    "authorization",
    "bearertoken",
    "clientsecret",
    "key",
    "secret",
    "token",
}


def normalize_field_name(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def redact(value: Any) -> Any:
    """Return a copy safe to print to a terminal or CI log."""
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if normalize_field_name(key) in SENSITIVE_RESPONSE_FIELDS
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def print_result(label: str, payload: Any) -> None:
    print(f"\n{'=' * 20} {label} {'=' * 20}")
    print(json.dumps(redact(payload), indent=2, ensure_ascii=False, default=str))


def load_extra_headers() -> Dict[str, str]:
    raw_value = os.getenv("HANDELSREGISTER_EXTRA_HEADERS_JSON")
    if not raw_value:
        return {}
    value = json.loads(raw_value)
    if not isinstance(value, dict):
        raise ValueError(
            "HANDELSREGISTER_EXTRA_HEADERS_JSON must contain a JSON object."
        )
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call the handelsregister.ai Account and Signals APIs and pretty-print "
            "their responses."
        )
    )
    parser.add_argument(
        "--account",
        action="store_true",
        help="Call all free, read-only Account endpoints.",
    )
    parser.add_argument(
        "--signals",
        action="store_true",
        help="Call Signals catalog, list, and (when available) detail endpoints.",
    )
    parser.add_argument(
        "--topic",
        action="append",
        dest="topics",
        help="Filter Signals by topic. Repeat for multiple topics.",
    )
    parser.add_argument(
        "--organization-id",
        action="append",
        dest="organization_ids",
        help="Filter Signals by entity ID. Repeat for multiple organizations.",
    )
    parser.add_argument("--from-date", help="Inclusive ISO 8601 start date.")
    parser.add_argument("--to-date", help="Inclusive ISO 8601 end date.")
    parser.add_argument(
        "--skip-detail",
        action="store_true",
        help="Skip the Signal detail request and save 20 credits.",
    )
    parser.add_argument(
        "--admin-key-roundtrip",
        action="store_true",
        help=(
            "Create, verify, list, revoke, and re-check a temporary API key. "
            "Requires HANDELSREGISTER_ADMIN_BEARER_TOKEN."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Do not ask before making billable Signals requests.",
    )
    return parser.parse_args()


def confirm_signals_calls(skip_detail: bool, assume_yes: bool) -> bool:
    expected = 20 if skip_detail else 40
    print(
        f"\nSignals catalog + list"
        f"{'' if skip_detail else ' + detail'} will cost up to {expected} credits."
    )
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Non-interactive input: rerun with --yes to allow billable calls.")
        return False
    return input("Continue? [y/N] ").strip().lower() in {"y", "yes"}


def account_demo(client: Handelsregister) -> None:
    print_result("Account profile", client.get_account())
    print_result("Account credits", client.get_account_credits())
    print_result("Account usage (current month)", client.get_account_usage())
    print_result(
        "Account usage transactions (first 5)",
        client.get_account_usage_transactions(per_page=5),
    )
    print_result("Account subscription", client.get_account_subscription())
    print_result("Account API keys (masked)", client.list_api_keys())


def signals_demo(
    client: Handelsregister,
    *,
    topics: Any,
    organization_ids: Any,
    from_date: Any,
    to_date: Any,
    skip_detail: bool,
) -> None:
    credits_before = client.get_account_credits()["balance"]["total"]

    catalog = client.get_signal_catalog()
    print_result("Signals catalog (free)", catalog)

    page = client.list_signals(
        topics=topics,
        organization_ids=organization_ids,
        from_date=from_date,
        to_date=to_date,
    )
    print_result("Signals list (20 credits)", page)

    detail = None
    signals = page.get("signals", []) if isinstance(page, dict) else []
    if not skip_detail and signals:
        signal_id = signals[0].get("event", {}).get("id")
        if signal_id:
            detail = client.get_signal(signal_id)
            print_result("First Signal detail (20 credits)", detail)
    elif not skip_detail:
        print("\nNo Signal was returned, so no detail request was made.")

    credits_after = client.get_account_credits()["balance"]["total"]
    print_result(
        "Signals billing summary",
        {
            "credits_before": credits_before,
            "credits_after": credits_after,
            "credits_charged": credits_before - credits_after,
            "detail_requested": detail is not None,
        },
    )


def admin_key_roundtrip(client: Handelsregister) -> None:
    admin_token = os.getenv("HANDELSREGISTER_ADMIN_BEARER_TOKEN")
    if not admin_token:
        raise AuthenticationError(
            "Set HANDELSREGISTER_ADMIN_BEARER_TOKEN to run the admin API-key "
            "round trip."
        )

    admin = Handelsregister(
        bearer_token=admin_token,
        extra_headers=client.extra_headers,
    )
    created = admin.create_api_key()
    print_result("Temporary API key created (key redacted)", created)

    api_key: Dict[str, Any] = created.get("api_key", {})
    key_id = api_key.get("id")
    key_value = api_key.get("key")
    if not key_id or not key_value:
        raise HandelsregisterError(
            "Create response did not include api_key.id and api_key.key."
        )

    temporary_client = Handelsregister(
        api_key=key_value,
        extra_headers=client.extra_headers,
    )

    try:
        print_result(
            "Temporary API key authentication",
            temporary_client.get_account(),
        )
        listed = admin.list_api_keys()
        print_result(
            "Temporary API key appears in list",
            {
                "api_key_id": key_id,
                "present": any(
                    item.get("id") == key_id for item in listed.get("api_keys", [])
                ),
            },
        )
    finally:
        revoked = admin.revoke_api_key(key_id)
        print_result("Temporary API key revoked", revoked)

    try:
        temporary_client.get_account()
    except AuthenticationError:
        revoked_key_rejected = True
    else:
        revoked_key_rejected = False
    print_result(
        "Revocation verification",
        {"revoked_key_rejected": revoked_key_rejected},
    )


def main() -> int:
    args = parse_args()
    run_account = args.account
    run_signals = args.signals
    if not run_account and not run_signals:
        run_account = True
        run_signals = True

    if run_signals and not confirm_signals_calls(args.skip_detail, args.yes):
        return 2

    try:
        client = Handelsregister(extra_headers=load_extra_headers())

        if run_account:
            account_demo(client)
        if run_signals:
            signals_demo(
                client,
                topics=args.topics,
                organization_ids=args.organization_ids,
                from_date=args.from_date,
                to_date=args.to_date,
                skip_detail=args.skip_detail,
            )
        if args.admin_key_roundtrip:
            admin_key_roundtrip(client)
    except APIError as exc:
        print_result(
            f"API error ({exc.status_code or 'no status'})",
            exc.payload or {"message": str(exc)},
        )
        return 1
    except HandelsregisterError as exc:
        print(f"\nHandelsregister client error: {exc}")
        return 1
    except (KeyError, TypeError, ValueError) as exc:
        print(f"\nUnexpected response or argument error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
