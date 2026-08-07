"""
Monitoring & webhooks demo for the handelsregister.ai Python SDK.

Free by default: lists pricing, monitors, webhook endpoints, deliveries and
events. Pass --setup with the flags below to run the full paid lifecycle
(endpoint registration, verification, monitor creation).

Usage:
    export HANDELSREGISTER_API_KEY=...        # or HANDELSREGISTER_BEARER_TOKEN
    python monitoring_example.py                              # free reads only
    python monitoring_example.py --setup \
        --url https://hooks.example.com/handelsregister \
        --entity-id cc78cf0b230aeae35c6df7ba31989bb9 --label "BMW AG"

Receiver side (framework-agnostic):

    from handelsregister.webhooks import (
        construct_event,
        verification_response_headers,
    )

    def handle_webhook(raw_body: bytes, headers: dict) -> tuple:
        event = construct_event(raw_body, headers, SIGNING_SECRET)
        if event["type"] == "endpoint.verification":
            return 204, verification_response_headers(event), b""
        if not dedupe_store_add(event["id"]):   # at-least-once delivery
            return 200, {}, b""
        if event["type"] == "organization.signal.detected":
            signal = event["data"]["signal"]
            print("New signal:", signal["event"]["topic"])
        return 200, {}, b""
"""

import argparse
import json

from handelsregister import Handelsregister


def show(title, payload):
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def free_reads(client: Handelsregister) -> None:
    show("Pricing (free)", client.get_monitoring_pricing(poll_interval_days=7))
    show("Monitors (free)", client.list_monitors())
    show("Webhook endpoints (free)", client.list_webhook_endpoints())
    show("Newest deliveries (free)", client.list_webhook_deliveries())
    show("Newest events (free)", client.list_webhook_events())


def setup_lifecycle(client: Handelsregister, url: str, entity_id: str, label: str) -> None:
    """Register + verify an endpoint, then create a monitor for one company."""
    created = client.create_webhook_endpoint(name="Demo receiver", url=url)
    endpoint = created["endpoint"]
    print("\nEndpoint created:", endpoint["id"], endpoint["status"])
    print("Signing secret (store now, shown once):", created["signing_secret"])

    # Your receiver must echo data.challenge in a `webhook-verification`
    # header for this to succeed.
    verification = client.verify_webhook_endpoint(endpoint["id"])
    print("Verified:", verification["verified"])
    if not verification["verified"]:
        print("Receiver did not answer the challenge; fix it and re-run verify.")
        return

    client.enable_webhook_endpoint(endpoint["id"])
    test = client.test_webhook_endpoint(endpoint["id"])
    print("Test delivery status:", test.get("delivery", {}).get("status"))

    pricing = client.get_monitoring_pricing(poll_interval_days=7)
    print(
        "Estimated credits per cycle:",
        pricing["pricing"]["estimated_credits"],
    )

    monitor = client.create_monitor(
        entity_id=entity_id,
        poll_interval_days=7,
        endpoint_ids=[endpoint["id"]],
        label=label,
    )
    # 202: the free baseline is queued; activation charges the 10-credit
    # floor only after the baseline completes.
    show("Monitor created (baseline queued, 0 credits charged)", monitor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--setup", action="store_true", help="Run the paid lifecycle")
    parser.add_argument("--url", help="Public HTTPS receiver URL (port 443)")
    parser.add_argument("--entity-id", dest="entity_id", help="Organization entity id")
    parser.add_argument("--label", default=None, help="Monitor label")
    args = parser.parse_args()

    client = Handelsregister()
    free_reads(client)

    if args.setup:
        if not args.url or not args.entity_id:
            parser.error("--setup requires --url and --entity-id")
        setup_lifecycle(client, args.url, args.entity_id, args.label)


if __name__ == "__main__":
    main()
