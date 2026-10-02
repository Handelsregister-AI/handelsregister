# Handelsregister Python SDK

[![PyPI version](https://img.shields.io/pypi/v/handelsregister.svg)](https://pypi.org/project/handelsregister/)
[![Python Versions](https://img.shields.io/pypi/pyversions/handelsregister.svg)](https://pypi.org/project/handelsregister/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

A modern Python client for the [Handelsregister.ai](https://handelsregister.ai) API. Structured, reliable, and fast access to the German commercial register (Handelsregister): company master data, financials, management, shareholders, UBOs, person profiles, and official PDF documents.

## Features

- **Company lookup** — `fetch-organization` with configurable feature flags
- **Deep shareholders** — Max-only share numbers, joint holders, tenure, and list changes
- **Person profiles** — `fetch-person` (Handelsregister roles + web data)
- **Search** — query or filters-only search with geo, registry, size, and financial filters
- **Signals** — cursor-paginated company changes with topic, company, and date filters
- **Monitoring & webhooks** — per-company monitors with signed webhook push, endpoint lifecycle, and receiver-side signature verification
- **Account** — profile, credits, usage, subscription, and API-key management
- **Financial data** — KPIs, balance sheet, P&L, full annual reports (MD/HTML)
- **Management** — current and past related persons with roles
- **Shareholders, UBOs, shareholdings** — who owns the company, who the company owns
- **Mergers & acquisitions** — transactions, succession, enterprise agreements, and control relationships
- **Representation schemes** — current and historical company- and person-role representation rules
- **News, publications, insolvency publications**
- **Website content** — structured Markdown, optimized for LLMs
- **Document downloads** — Gesellschafterliste, Gesellschaftsvertrag, AD/CD PDFs, and SI XML
- **Auth** — `x-api-key` header or Bearer token, plus token management
- **Batch enrichment** — resilient CSV/JSON/XLSX enrichment with snapshots
- **Live mode** — opt-in realtime lookups against the Handelsregister

## Installation

```bash
pip install handelsregister
```

## Authentication

You can authenticate in two ways:

**API key (recommended for server-to-server):**

```bash
export HANDELSREGISTER_API_KEY=your_api_key_here
```

```python
from handelsregister import Handelsregister

client = Handelsregister(api_key="your_api_key_here")
```

**Bearer token (fine-grained control, expiration):**

```bash
export HANDELSREGISTER_BEARER_TOKEN=your_token_here
```

```python
client = Handelsregister(bearer_token="your_token_here")
```

When both are provided, the bearer token wins.

For gateways or proxies that require additional request headers, provide them
explicitly. Managed authentication and User-Agent headers cannot be
overridden:

```python
import os

from handelsregister import Handelsregister

client = Handelsregister(
    api_key="your_api_key_here",
    extra_headers={
        "X-Gateway-Client-Id": os.environ["GATEWAY_CLIENT_ID"],
        "X-Gateway-Client-Secret": os.environ["GATEWAY_CLIENT_SECRET"],
    },
)
```

Additional headers can also come from the environment:

```bash
export HANDELSREGISTER_EXTRA_HEADERS='{"X-Gateway-Client-Id": "...", "X-Gateway-Client-Secret": "..."}'
```

Explicit `extra_headers` always win over this variable.

## Quick Start

### Company lookup

```python
from handelsregister import Handelsregister

client = Handelsregister()

result = client.fetch_organization(
    q="KONUX GmbH München",
    features=["related_persons", "financial_kpi", "shareholders"],
    ai_search="on-default",          # optional: enable AI search
    # realtime_mode="handelsregister-default",  # +10 credits for live data
)

print(result["name"], result["registration"]["register_number"])
```

### Object-oriented `Company` interface

```python
from handelsregister import Company

company = Company(
    "OroraTech GmbH München",
    features=[
        "related_persons",
        "financial_kpi",
        "balance_sheet_accounts",
        "shareholders",
        "ubos",
        "shareholdings",
        "mergers_and_acquisitions",
        "network",
        "annual_financial_statements",
        "news",
    ],
)

print(company.name, company.is_active)
print(company.formatted_address)

# Management
for person in company.current_related_persons:
    print(person["name"], "-", person["role"]["en"]["long"])

# Shareholders (who owns the company)
for entry in company.shareholders.entries:
    print(entry.display_name, entry.percentage)

# Ultimate beneficial owners
for ubo in company.ubos.resolved:
    print(ubo.name, ubo.percentage)

# Outbound shareholdings (what the company owns)
for holding in company.shareholdings.current:
    print(holding.organization_name, holding.percentage)

# Company- and person-level representation rules
for rule in company.representation_scheme.active:
    print(rule)

for director in company.related_person_entries.current:
    print(director.display_name, director.role_representation_scheme.active)

# M&A transactions
for transaction in company.mergers_and_acquisitions.transactions:
    print(transaction.date, transaction.headline_text("en"))

# Relationship graph (Pro/Max)
print(company.network.depth, len(company.network.nodes))
for connection in company.network.connections:
    print(connection.source.name, connection.label, connection.target.name)

# News
for article in company.news:
    print(article["publication_date"], article["title"])
```

### Person profiles

The `/v1/fetch-person` endpoint merges Handelsregister records with public web data. `ai_search` is always on for this endpoint (the 15-credit base cost includes the AI enrichment). `organization_q` is required to disambiguate common names.

```python
from handelsregister import Person

person = Person(
    person_q="Max Mustermann",
    organization_q="Beispielwerk Analytics GmbH",
    features=["shareholdings"],  # +5 credits, only if data is returned
)

print(person.canonical_name, "-", person.home_city)
print(person.bio)

for role in person.handelsregister_roles:
    print(role["name"], role["label"], role.get("start_date"), role.get("end_date"))

for holding in person.shareholdings.current:
    print(holding.organization_name, holding.percentage, holding.as_of)
```

### Search

```python
from handelsregister import (
    FilterCondition,
    Handelsregister,
    OrganizationStatus,
    OwnershipFilters,
    RangeFilter,
    SearchFilters,
    SearchSort,
    SortOrder,
)

client = Handelsregister()

page = client.search_organizations(
    limit=10,
    skip=0,
    filters=SearchFilters(
        city="München",
        legal_form_code="GmbH",
        status=OrganizationStatus.ACTIVE,
        pl_revenue=RangeFilter(gte=1_000_000, lte=5_000_000),
        ownership_filters=OwnershipFilters(
            owner_managed=True,
            oldest_owner_birth_date=FilterCondition(lte="1960"),
        ),
    ),
    sort=SearchSort.REVENUE,
    order=SortOrder.DESC,
    match_context=True,
)

print(page["total"])
for item in page["results"]:
    print(item["name"], item["registration"]["register_number"])
```

The API returns at most **30 organizations per request**. Passing `limit=31`
or higher raises `ValueError` instead of silently returning a truncated page.
Use `skip` for manual pagination, or let the lazy iterator fetch successive
pages:

```python
organizations = list(
    client.iter_search_organizations(
        q="tech",
        page_size=30,
        max_results=100,
    )
)
```

For 100 available matches this makes four requests with page sizes
`30`, `30`, `30`, and `10`. Each page is a separate billable API request;
stopping iteration early prevents subsequent pages from being fetched.

`q` may contain 2–500 characters and may be omitted when at least one filter is
supplied. `filters` may also be an ordinary dictionary. Supported keys cover
registration dates, legal form, exact organization status, liability type,
WZ/NACE industries, location and radius, register data, company size, employee
and financial ranges, plus the Pro/Max `ownership_filters`,
`executive_filters`, and `lifecycle_filters` groups.

Financial range dictionaries use `{"gte": minimum, "lte": maximum}` and are
sent under `financial_filters`. Advanced register-data conditions additionally
support `gt`, `lt`, `eq`, and `exists`; `FilterCondition` builds these objects.
Use `LocationCoordinates(lat=..., lon=...)` for a radius search. The SDK also
accepts the legacy `{"latitude": ..., "longitude": ...}` input and normalizes
it to the current API shape.

`sort` accepts the documented fields exposed by `SearchSort`, `order` accepts
`SortOrder.ASC` or `SortOrder.DESC`, and `match_context=True` requests the
matching ownership, executive, and lifecycle values under each result's
`_match_context` object. Advanced register-data filters require a Pro or Max
subscription; an insufficient plan raises `SubscriptionRequiredError`.

## Signals

Signals expose company changes through seven stable topic codes. Catalog
requests are free; successful list and detail requests cost 20 credits. Pages
contain 20 signals and use opaque cursor pagination.

### Signals endpoints

| HTTP endpoint | Python method | Successful request cost |
|---|---|---:|
| `GET /api/v1/signals` | `list_signals()` | 20 credits per page |
| `GET /api/v1/signals` | `iter_signals()` | 20 credits per fetched page |
| `GET /api/v1/signals/catalog` | `get_signal_catalog()` | Free |
| `GET /api/v1/signals/{signal_id}` | `get_signal()` | 20 credits |

`list_signals()` accepts these arguments:

| Python argument | Description |
|---|---|
| `cursor` | Opaque `pagination.next_cursor` value returned by the previous page |
| `topics` | One topic, a comma-separated string, or an iterable of `SignalTopic`/string values |
| `organization_ids` | One entity ID or an iterable of entity IDs |
| `from_date` | Inclusive publication-date lower bound as an ISO 8601 string, `date`, or `datetime` |
| `to_date` | Inclusive publication-date upper bound as an ISO 8601 string, `date`, or `datetime` |

`iter_signals()` accepts the same filters and adds `max_results`. It requests
the next page only when iteration reaches it.

```python
from handelsregister import Handelsregister, SignalTopic

client = Handelsregister()

page = client.list_signals(
    topics=[
        SignalTopic.CAPITAL_CHANGES,
        SignalTopic.TRANSFORMATIONS,
    ],
    organization_ids=[
        "0123456789abcdef0123456789abcdef",
        "fedcba9876543210fedcba9876543210",
    ],
    from_date="2026-07-01",
    to_date="2026-07-30",
)

for signal in page["signals"]:
    print(signal["event"]["id"], signal["event"]["topic"])

catalog = client.get_signal_catalog()
if page["signals"]:
    detail = client.get_signal(page["signals"][0]["event"]["id"])
    print(detail["signal"]["event"]["topic"])
```

For manual cursor navigation, send the cursor unchanged and preserve the
filters used for the first page:

```python
filters = {
    "topics": [SignalTopic.NEW_REGISTRATIONS],
    "from_date": "2026-07-01",
    "to_date": "2026-07-30",
}

first_page = client.list_signals(**filters)
next_cursor = first_page["pagination"].get("next_cursor")

if next_cursor:
    second_page = client.list_signals(cursor=next_cursor, **filters)
```

Multiple `organization_ids` use OR semantics: a returned Signal may belong to
any supplied entity ID. The SDK sends the IDs as one comma-separated query
value and preserves them while following cursors.

The lazy iterator handles this automatically. Every fetched page is a separate
billable request:

```python
for signal in client.iter_signals(
    topics=[SignalTopic.NEW_REGISTRATIONS],
    max_results=50,
):
    print(signal["organization"]["current_profile"]["name"])
```

### Signal topics

The public topics are available as both `SignalTopic` and `SIGNAL_TOPICS`.

| Code | Data covered | Plan requirement |
|---|---|---|
| `NEW_REGISTRATIONS` | Newly registered organizations | No additional topic gate |
| `MASTER_DATA_CHANGES` | Name, registered seat, address, or register changes | No additional topic gate |
| `CLOSURES` | Dissolution, liquidation, deletion, or expiration | No additional topic gate |
| `ROLE_HOLDER_CHANGES` | Management, board, and procuration changes | No additional topic gate |
| `CAPITAL_CHANGES` | Share, nominal, liable, or authorized capital changes | No additional topic gate |
| `INSOLVENCIES` | Openings, protective measures, and completed proceedings | Pro |
| `TRANSFORMATIONS` | Mergers, divisions, conversions, asset transfers, enterprise agreements, and squeeze-outs | Max |

Requests below the required plan return HTTP 403 with
`PLAN_REQUIRED` and cost zero credits. The SDK maps this response to
`SubscriptionRequiredError`.

### Signal response data

Each list entry contains:

- `event`: stable ID, topic, localized topic name, occurrence/publication dates,
  and date basis. `ROLE_HOLDER_CHANGES` events additionally carry a `type`
  (`ROLE_HOLDER_ENTRY` or `ROLE_HOLDER_EXIT`) with a localized `type_name`.
- `organization`: entity ID and the current organization profile.
- `parties`: topic-specific participants - for `ROLE_HOLDER_CHANGES` a
  `role_holder` with the person/organization entity plus its role `code` and
  `representation_scheme`.
- `register_entry`: entry number/date, phase, description, context, and flags.
- `source`: source kind.
- `details`: topic-specific structured data identified by `details.schema`.

Fields without a value are omitted rather than returned as `null`. A list
response also includes `pagination`, applied `filters`, `warnings`, and `meta`.
The pagination object reports the fixed limit, returned count, `has_more`, and
the next opaque cursor. There is no total count.

`get_signal()` returns the event inside a `signal` envelope:

```python
detail = client.get_signal("0123456789abcdef0123456789abcdef")
signal = detail["signal"]
request_cost = detail["meta"]["request_credit_cost"]
```

The catalog response contains the public topics and their descriptions,
whether data has been observed for each topic, `catalog_version`, and server
`capabilities`.

## Monitoring & Webhooks

Monitoring watches companies you select and pushes new normalized
commercial-register changes to your HTTPS endpoints through signed webhooks.
It shares the topic vocabulary with Signals but is an independent product;
each webhook links to the Signals detail API for on-demand deep data.

Reads are free. Monitor mutations work with an API key or a Bearer token
carrying `account:read` plus `monitoring:manage`. Endpoint creation, secret
rotation, enable/disable, and archive additionally require a Bearer token
with `account:read` plus `account:keys`.

### Setting up a receiver

```python
from handelsregister import Handelsregister

client = Handelsregister(bearer_token="YOUR_ADMIN_TOKEN")

# 1. Register the endpoint; store the one-time whsec_ secret immediately.
created = client.create_webhook_endpoint(
    name="Production receiver",
    url="https://hooks.example.com/handelsregister",
    headers={"x-tenant": "customer-42"},  # optional, write-only
)
endpoint_id = created["endpoint"]["id"]
signing_secret = created["signing_secret"]  # shown exactly once

# 2. Your receiver must echo data.challenge in a `webhook-verification`
#    header with any 2xx status; then trigger the challenge. A successful
#    first verification activates the endpoint immediately.
result = client.verify_webhook_endpoint(endpoint_id)  # {"verified": true/false}

# 3. Optionally send a signed test event. enable_webhook_endpoint() is only
#    needed to reactivate an endpoint after a disable.
client.test_webhook_endpoint(endpoint_id)
```

### Creating a monitor

```python
# Pricing is informational and useful for estimating the cycle cost.
pricing = client.get_monitoring_pricing(poll_interval_days=7)

created = client.create_monitor(
    entity_id="cc78cf0b230aeae35c6df7ba31989bb9",
    poll_interval_days=7,
    endpoint_ids=[endpoint_id],
    label="BMW AG",
)
monitor = created["monitor"]  # status: "initializing", baseline queued, 0 credits

detail = client.get_monitor(monitor["id"])
detail["billing_cycle"]                         # active cycle summary, or None
detail["recent_runs"]                           # newest 20 poll runs
client.update_monitor(monitor["id"], 14)          # prospective interval change
client.pause_monitor(monitor["id"])
client.resume_monitor(monitor["id"])
client.archive_monitor(monitor["id"])           # archive, never hard-delete
```

The free all-topic baseline runs asynchronously and suppresses historical
observations. It can complete within seconds, at which point activation
charges a 10-credit cycle floor covering five complete successful checks in
a rolling 30-day cycle; each further complete successful check costs
2 credits (`max(10, 2 * checks)`). Failed, partial, superseded, or unfunded
checks add no run charge, and pausing or archiving never refunds the floor —
archive while still `initializing` to stop a monitor before activation.
Every account receives the five core topics; `INSOLVENCIES` needs Pro or
Max and `TRANSFORMATIONS` needs Max. Inaccessible observations are
terminally suppressed, not replayed after an upgrade.

### Verifying deliveries in your receiver

Delivery is at-least-once with no ordering guarantee, so verify the exact
raw request bytes and deduplicate on the message id:

```python
from handelsregister.webhooks import construct_event, verification_response_headers

# e.g. in a Flask/FastAPI handler
event = construct_event(raw_body_bytes, request_headers, signing_secret)

if event["type"] == "endpoint.verification":
    return Response(status=204, headers=verification_response_headers(event))

if event["type"] == "organization.signal.detected":
    signal = event["data"]["signal"]
    link = event["data"]["links"]["signal"]  # Signals detail API (20 credits on success)
```

`construct_event()` checks the `v1,<base64>` HMAC-SHA256 signature over
`webhook-id.webhook-timestamp.raw_body`, accepts the current and predecessor
secret during the seven-day rotation grace (pass a list of secrets), and
enforces a configurable timestamp tolerance. Samples always set
`data.sample=true`; detected events never do. Respond with any 2xx quickly;
3xx/4xx/5xx and timeouts are retried for roughly three days across ten
attempts, HTTP 410 disables the endpoint immediately, and five consecutive
exhausted deliveries disable it too.

### Idempotency

Every mutation requires an `Idempotency-Key`. The SDK generates a compliant
key automatically and reuses it across its internal retries, so transient
errors never double-charge or double-create. Pass `idempotency_key=` to make
retries across process restarts safe as well: an exact retry within 24 hours
replays the original response — including the same resource id — with
`client.last_idempotency_status` set to `"replayed"` instead of
`"created"`. Reusing a key with different parameters raises
`IdempotencyConflictError`. Requests rejected by validation (HTTP 400/422)
never claim their key, so the same key can be retried after fixing the
request. Never re-drive an ambiguous 409 on a verify/test operation with a
fresh key, because the API cannot prove whether your receiver saw the
ambiguous request.

### Delivery history

```python
client.list_webhook_endpoints()                  # all non-archived endpoints (max 10)
client.list_webhook_deliveries(endpoint_id)      # newest 50 delivery summaries
client.retry_webhook_delivery("del_...")         # re-drive a retained failed delivery
client.list_webhook_events()                     # newest 50 event summaries
client.rotate_webhook_endpoint_secret(endpoint_id)  # new one-time whsec_ secret
client.disable_webhook_endpoint(endpoint_id)
client.archive_webhook_endpoint(endpoint_id)
```

Event payloads are retained encrypted for 30 days, delivery attempt audit
rows for 90 days.

## Account and Usage

Account endpoints are read-only except for API-key creation and revocation.
Every Account request costs zero credits.

### Account endpoints

| HTTP endpoint | Python method | Authentication |
|---|---|---|
| `GET /api/v1/account` | `get_account()` | API key or `account:read` Bearer token |
| `GET /api/v1/account/credits` | `get_account_credits()` | API key or `account:read` Bearer token |
| `GET /api/v1/account/usage` | `get_account_usage()` | API key or `account:read` Bearer token |
| `GET /api/v1/account/usage/transactions` | `get_account_usage_transactions()` | API key or `account:read` Bearer token |
| `GET /api/v1/account/subscription` | `get_account_subscription()` | API key or `account:read` Bearer token |
| `GET /api/v1/account/api-keys` | `list_api_keys()` | API key or `account:read` Bearer token |
| `POST /api/v1/account/api-keys` | `create_api_key()` | Bearer token with `account:keys` |
| `DELETE /api/v1/account/api-keys/{id}` | `revoke_api_key()` | Bearer token with `account:keys` |

```python
from handelsregister import Handelsregister

client = Handelsregister()

profile = client.get_account()
credits = client.get_account_credits()
subscription = client.get_account_subscription()
keys = client.list_api_keys()  # masked values only

usage = client.get_account_usage(
    from_date="2026-07-01",
    to_date="2026-07-30",
    group_by="day",
)

transactions = client.get_account_usage_transactions(
    endpoint="/api/v1/signals",
    per_page=25,
)
```

`get_account_usage()` and `get_account_usage_transactions()` accept:

| Python argument | Applies to | Description |
|---|---|---|
| `from_date` / `to_date` | Both | ISO 8601 string, `date`, or `datetime`; defaults to the current month; maximum range is 366 days |
| `group_by` | Usage | `"day"` or `"month"`; the server chooses a default based on range length |
| `endpoint` | Transactions | Exact endpoint filter, for example `/api/v1/signals` |
| `per_page` | Transactions | Page size from 1 to 100; default is 25 |
| `cursor` | Transactions | Opaque cursor returned in `pagination.next_cursor` |

A date-only `to_date` includes that entire day. Transactions can also be
consumed across all cursor pages:

```python
for transaction in client.iter_account_usage_transactions(per_page=100):
    print(transaction["endpoint"], transaction["credits"])
```

Account responses provide:

- Profile data: name, email, language, and current plan.
- Credits: remaining balance, bookings, and the next expiration date.
- Usage: selected period, request/credit totals, endpoint breakdown, and daily
  or monthly time-series buckets.
- Transactions: individual billed requests plus cursor pagination.
- Subscription: plan, status, billing period, and included features.
- API keys: active keys in masked form, creation time, and last usage time.

Creating or revoking an API key requires a Bearer token with the
`account:keys` ability. The full key is returned only by the creation response:

```python
import os

from handelsregister import Handelsregister

admin = Handelsregister(
    bearer_token=os.environ["HANDELSREGISTER_ADMIN_BEARER_TOKEN"],
)
created = admin.create_api_key()

try:
    new_key = created["api_key"]["key"]
finally:
    admin.revoke_api_key(created["api_key"]["id"])
```

### End-to-end Account and Signals demo

The repository includes a runnable script that pretty-prints the live
responses while redacting credentials:

```bash
# Account reads are free. Signals catalog + list + detail cost up to 40 credits.
python examples/account_signals_demo.py

# Account only (free)
python examples/account_signals_demo.py --account

# Signals only, without the 20-credit detail call
python examples/account_signals_demo.py --signals --skip-detail
```

For a temporary API-key create/verify/revoke round trip, set
`HANDELSREGISTER_ADMIN_BEARER_TOKEN` and run:

```bash
python examples/account_signals_demo.py \
  --account \
  --admin-key-roundtrip
```

## Document Downloads

```python
from handelsregister import Handelsregister, Company

client = Handelsregister()

# Get the company's entity_id
result = client.fetch_organization(q="KONUX GmbH München")
entity_id = result["entity_id"]

# Download documents directly from the client
client.fetch_document(
    company_id=entity_id,
    document_type="shareholders_list",       # Gesellschafterliste
    output_file="konux_shareholders.pdf",
)

client.fetch_document(
    company_id=entity_id,
    document_type="articles_of_association", # Gesellschaftsvertrag / Satzung
    output_file="konux_articles.pdf",
)

client.fetch_document(
    company_id=entity_id,
    document_type="AD",                      # Aktueller Ausdruck
    output_file="konux_current.pdf",
)

pdf_bytes = client.fetch_document(
    company_id=entity_id,
    document_type="CD",                      # Chronologischer Ausdruck
)

xml_bytes = client.fetch_document(
    company_id=entity_id,
    document_type="SI",                      # Structured information (XML)
    output_file="konux_structured.xml",
)

# Or via the Company helper
company = Company("OroraTech GmbH München")
company.fetch_document(
    document_type="shareholders_list",
    output_file="ororatech_shareholders.pdf",
)
```

### Available document types

| Document Type              | Description                                        |
|----------------------------|----------------------------------------------------|
| `shareholders_list`        | Gesellschafterliste                                |
| `articles_of_association`  | Gesellschaftsvertrag / Satzung / Statut            |
| `AD`                       | Aktuelle Daten (current excerpt)                   |
| `CD`                       | Chronologische Daten (historical excerpt)          |
| `SI`                       | Strukturierter Inhalt (XML)                        |

## Bearer Token Management

If you prefer managing bearer tokens over sharing an API key:

```python
client = Handelsregister(api_key="your_api_key_here")

# Create a new token. expires_at must lie in the future; omit it for a
# non-expiring token.
created = client.create_token(
    token_name="My Application",
    abilities=["account:read", "monitoring:manage"],
    expires_at="2027-01-01 00:00:00",
)
created["token"]      # the bearer token value - shown exactly once
created["abilities"]  # abilities actually granted

# List tokens; the create response has no id, so look it up here.
tokens = client.list_tokens()
token_id = next(
    t["id"] for t in tokens["tokens"] if t["name"] == "My Application"
)
client.revoke_token(token_id=token_id)

# Revokes every bearer token of the account - use deliberately.
client.revoke_all_tokens()
```

Ability notes: passing `["*"]` does not grant a wildcard - the server
replaces it with the defaults `api:data` and `account:read`. Request
additional abilities such as `monitoring:manage` explicitly. `account:keys`
cannot be self-granted through this endpoint; tokens for webhook-endpoint
administration must be created in the dashboard.

## Data Enrichment

Enrich a CSV/JSON/XLSX file of companies with Handelsregister data. Intermediate snapshots let you resume long-running jobs.

```python
from handelsregister import Handelsregister

client = Handelsregister()

client.enrich(
    file_path="companies.csv",
    input_type="csv",
    query_properties={
        "name": "company_name",   # map 'company_name' column to query
        "location": "city",       # map 'city' column to query
    },
    snapshot_dir="snapshots",
    params={
        "features": ["related_persons", "financial_kpi", "ubos"],
        "ai_search": "on-default",
    },
    output_file="companies_enriched.csv",
    output_type="csv",
)
```

Each output row keeps the input columns and adds the API response under
`_handelsregister_result` plus a `_in_file` marker.

There is also a DataFrame convenience:

```python
import pandas as pd
from handelsregister import Handelsregister

client = Handelsregister()
df = pd.read_csv("companies.csv")
enriched = client.enrich_dataframe(
    df,
    query_properties={"name": "company_name", "location": "city"},
    params={"features": ["financial_kpi"]},
)
```

## Command Line Interface

Installing the package exposes the `handelsregister` CLI. If the optional `rich` dependency is installed, commands render colorful tables.

```bash
# Company lookup (defaults: all standard features + AI search)
$ handelsregister fetch "KONUX GmbH München"

# Raw JSON
$ handelsregister fetch json "KONUX GmbH München"

# Opt-in to realtime mode for live register data
$ handelsregister fetch "KONUX GmbH München" --realtime-mode handelsregister-default

# Person profile
$ handelsregister person \
    --person "Max Mustermann" \
    --organization "Beispielwerk Analytics GmbH" \
    --feature shareholdings

# Search (maximum 30 results per request)
$ handelsregister search "tech" --postal-code 80992 --limit 20 \
    --sort revenue --order desc

# Filters-only search (JSON or repeated key=value)
$ handelsregister search \
    --filters '{"city":"München","ownership_filters":{"owner_managed":true}}' \
    --match-context

# Enrich a file
$ handelsregister enrich companies.csv --input csv \
    --query-properties name=company_name location=city \
    --snapshot-dir snapshots \
    --feature related_persons --feature financial_kpi \
    --output-format csv

# Download documents
$ handelsregister document "KONUX GmbH München" \
    --type shareholders_list --output konux_shareholders.pdf

$ handelsregister document "KONUX GmbH München" \
    --type articles_of_association --output konux_articles.pdf

$ handelsregister document "KONUX GmbH München" \
    --type SI --output konux_structured.xml

# Monitoring
$ handelsregister monitors pricing --interval 7
$ handelsregister monitors list
$ handelsregister monitors create --entity-id cc78cf0b230aeae35c6df7ba31989bb9 \
    --interval 7 --endpoint wep_01hzy2q6j3g5m8v9x0abcde123 \
    --label "BMW AG"
$ handelsregister monitors show mon_01hzy2q6j3g5m8v9x0abcde123
$ handelsregister monitors pause mon_01hzy2q6j3g5m8v9x0abcde123

# Webhook endpoints, deliveries, events
$ handelsregister webhooks create --name "Production receiver" \
    --url https://hooks.example.com/handelsregister --header x-tenant=customer-42
$ handelsregister webhooks verify wep_01hzy2q6j3g5m8v9x0abcde123
$ handelsregister webhooks deliveries --endpoint wep_01hzy2q6j3g5m8v9x0abcde123
$ handelsregister webhooks events
```

## Available Features (`fetch-organization`)

| Feature Flag                         | Description                                                   |
|--------------------------------------|---------------------------------------------------------------|
| `related_persons`                    | Current and past management                                   |
| `financial_kpi`                      | Yearly revenue, net income, employees, …                      |
| `balance_sheet_accounts`             | Hierarchical balance sheet data                               |
| `profit_and_loss_account`            | Profit & loss statements                                      |
| `annual_financial_statements`        | Full annual reports as Markdown                               |
| `annual_financial_statements__html`  | Full annual reports as HTML                                   |
| `publications`                       | Official Handelsregister publications                         |
| `insolvency_publications`            | Insolvency court publications                                 |
| `news`                               | News articles about the company                               |
| `website_content`                    | Company website as structured Markdown (AI mode, 0 credits)   |
| `shareholders` (beta)                | Shareholders with capital contribution, ratio, roles, and history |
| `shareholders_deep` (Max)            | Individual share ranges, joint holders, tenure, history, and changes |
| `ubos` (beta)                        | Ultimate beneficial owners (resolved / unresolved / coverage) |
| `shareholdings` (beta)               | Outbound shareholdings (what the company owns in others)      |
| `mergers_and_acquisitions` (beta)     | M&A transactions, succession, agreements, and control         |
| `network` (beta, Pro/Max)             | Relationship graph of connected organizations and people     |

`network` costs 25 credits when it returns data, in addition to the 5-credit
organization lookup. It requires a Pro or Max plan.
When `network` is requested, the SDK checks the account's subscription through
the free Account API before making the billable organization request. Accounts
below Pro receive `SubscriptionRequiredError` with the accepted plans instead
of a silently reduced base profile.

`shareholders_deep` costs 80 credits in addition to the 5-credit lookup, only
when current entries are returned. The API ignores this feature on plans other
than Max (the response key is absent). With no current shareholder information,
the key is `null`; an empty `entries` array also incurs no feature charge.
The SDK follows this behavior without a subscription preflight.

`realtime_mode="handelsregister-default"` forces a live Handelsregister lookup (+10 credits), independent of the feature flags above.
It cannot be combined with `related_persons` or `publications`.

The base response includes `representation_scheme`. Entries in
`related_persons` may include both `organization_representation_scheme` and
`role_representation_scheme`. Historical person records can expose their last
applicable rules as `latest`; the SDK normalizes `current` and `latest` through
the `.active` property.

## `Company` properties

```python
# Basic
company.name
company.entity_id
company.status
company.is_active
company.purpose
company.representation_scheme          # RepresentationScheme
company.capital                         # original raw capital payload
company.capital_info                    # CapitalInfo: current + history

# Registration
company.registration_number
company.registration_court
company.registration_type
company.registration_date

# Contact & address
company.address
company.formatted_address
company.coordinates
company.website
company.phone_number
company.email

# Financial
company.financial_kpi
company.financial_kpi_entries            # typed years, metrics, provenance
company.balance_sheet_entries           # typed years + activity statements
company.profit_and_loss_entries          # typed years + activity statements
company.financial_years
company.balance_sheet_accounts
company.profit_and_loss_account
company.annual_financial_statements
company.annual_financial_statements_html
company.get_financial_kpi_for_year(2023)
company.get_balance_sheet_for_year(2023)
company.get_profit_and_loss_for_year(2023)
company.get_balance_sheet_entry_for_year(2023)  # typed year or None
company.get_profit_and_loss_entry_for_year(2023)
company.get_activity_balance_sheets_for_year(2023)  # Max: list[ActivityStatement]
company.get_activity_profit_and_loss_for_year(2023)
company.get_annual_financial_statement_for_year(2023)  # Markdown
company.get_annual_financial_statement_for_year(2023, html=True)

# People & ownership
company.current_related_persons
company.past_related_persons
company.get_related_persons_by_role("MANAGING_DIRECTOR")
company.related_person_entries         # typed persons + representation schemes
company.shareholders           # ShareholderInfo
company.shareholders_deep      # ShareholdersDeep (Max)
company.ubos                   # UBOInfo
company.shareholdings          # ShareholdingsInfo
company.mergers_and_acquisitions  # MergersAndAcquisitions
company.network               # OrganizationNetwork

# News & publications
company.publications
company.insolvency_publications
company.news
company.website_content
```

### Deep shareholders

Use an organization's `entity_id` as the query to identify it reliably:

```python
from handelsregister import Company, OrganizationFeature

company = Company(
    "YOUR_ORGANIZATION_ENTITY_ID",
    features=[OrganizationFeature.SHAREHOLDERS_DEEP],
)
deep = company.shareholders_deep
print(deep.record.date, deep.record.source)
if deep.share_capital is not None:
    print(deep.share_capital.value, deep.share_capital.currency, deep.share_capital.basis)

for entry in deep.entries:
    print(entry.holder.name, entry.role, entry.percentage)  # percentage: 0–100
    print(entry.since, entry.since_basis)
    for shares in entry.ownership.share_ranges:
        print(shares.from_number, shares.to_number, shares.count)
        if shares.nominal_value is not None:
            print(shares.nominal_value.value, shares.nominal_value.currency)

for snapshot in deep.history:
    print(snapshot.record.date, snapshot.record.source, len(snapshot.entries))
if deep.changes is not None:
    print(deep.changes.compared_to)
    for change in deep.changes.changed:
        print(change.holder.name, change.percentage_before, change.percentage_after)
```

`holder.type` can be `ORGANIZATION`, `PERSON`, or `JOINT`. A joint community's
`holder.members` contains its co-owners; its ownership belongs to the community
as a whole and is never divided among the members by the SDK. Each entry is a
document row, so holders can appear multiple times. History preserves printed
names and row order; changes aggregate by holder as supplied by the API.

Unknown fields remain in `.raw` / `.as_dict()`, unknown enum strings are
accepted, and unknown amounts, dates, IDs, and percentages remain `None`.
`changes` can be `None` when there is no previous list or the source is not a
shareholder list. Register history entries may include `until`.
`since_basis="EARLIEST_RECORD"` means recorded at least since that date;
`ENTRY_RECORDED` identifies the recorded start. Deep percentages use **0–100**,
while regular `company.shareholders.entries[].percentage` remains a **0–1 ratio**.
Regular entries also expose `entity_id`, `birth_date`, `role`, and `role_name`.

`Company.shareholders_deep` returns an empty view for missing or null blocks;
inspect `company.data` to distinguish those cases. Every nested model exposes
the original dictionary through `.as_dict()`.

```bash
handelsregister fetch YOUR_ORGANIZATION_ENTITY_ID --feature shareholders_deep
handelsregister fetch json YOUR_ORGANIZATION_ENTITY_ID --feature shareholders_deep
python examples/shareholders_deep_example.py YOUR_ORGANIZATION_ENTITY_ID
```

See the [deep shareholder reference](https://dev.handelsregister.ai/de/documentation/data-shareholders-deep)
for the complete contract.

### Capital history and financial sources

Capital is included in the base response. `company.capital` retains the raw
interface; `company.capital_info.current` exposes `amount`, `currency`, and
the open-ended `kind`. Its `.history` entries expose `.value`, `.effective_from`,
and `.effective_to` (`None` for an ongoing value). A history value's
`change_amount` is an unsigned reported amount, not necessarily the difference
between successive values. Infer increases and reductions from the actual
capital amounts. Companies without registered capital have `current=None`
and an empty history.

```python
for year in company.financial_kpi_entries:
    print(year.year, year.metrics.get("revenue"), year.provenance.statement_type)
    print(year.provenance.period_start, year.provenance.period_end)
    print(year.provenance.exempt_subsidiary, year.provenance.parent_organization)

for year in company.balance_sheet_entries:
    for activity in year.activity_statements:
        print(activity.name_text("en"), activity.balance_sheet_accounts)
        print(activity.provenance.statement_type)
```

Raw financial properties and year helpers retain `_provenance` and all
plan-dependent metrics. Pro/Max KPIs can include additional metrics such as
`equity_ratio`, `revenue_per_employee`, and `source_statement_type`; these
remain accessible in each typed year's `.metrics` without a fixed schema.
Max balance-sheet and P&L years may also include `activity_statements` for
regulated energy activities. Each has its own activity label, account tree,
and provenance. P&L activity accounts use `profit_and_loss_accounts`.

`_provenance` is included on **all tiers**, including the source statement
type, period, subsidiary-exemption flag, and parent organization when
applicable. It is metadata within each year, rather than a separate feature
flag. The `balance_sheet_accounts` and `profit_and_loss_account` features
each cost **3 credits on every tier**. On Max, their responses also include
activity statements when available, with no additional flag or surcharge.
Years without activity statements omit that key; typed activity lists are
empty in that case.

The year-specific helpers keep the main accounts and activity accounts
separate. Every activity keeps its own provenance and report label; activity
names can differ between balance-sheet and P&L reports, so the SDK does not
merge them by name or add them to the main account totals.

```python
from handelsregister import Company

company = Company(
    "Stadtwerke Bad Pyrmont GmbH",
    features=["balance_sheet_accounts", "profit_and_loss_account"],
)
balance = company.get_balance_sheet_entry_for_year(2023)
if balance is not None:
    print(balance.provenance.statement_type)  # all tiers

for activity in company.get_activity_balance_sheets_for_year(2023):
    print(activity.name_text("en"), activity.name_in_report)
    print(activity.provenance.period_start, activity.provenance.period_end)
    for root in activity.balance_sheet_entries:
        for account in root.walk():
            print(account.name_text("de"), account.value)

for activity in company.get_activity_profit_and_loss_for_year(2023):
    for root in activity.profit_and_loss_entries:
        print(root.name_text("en"), root.value)
```

`FinancialAccount` exposes the original `name`, `value`, `children`, and
`.as_dict()`. `.walk()` visits every descendant in report order. Existing raw
account properties remain available. Missing years return `None` from the
typed year helpers, and `[]` from the activity helpers.

The CLI displays account trees and provenance separately for each activity.
Use `--financial-year` to select a year locally; this option does not change
the request or filter JSON output:

```bash
handelsregister fetch "Stadtwerke Bad Pyrmont GmbH" \
    --feature balance_sheet_accounts --feature profit_and_loss_account \
    --financial-year 2023 --ai-search off
python examples/activity_financials_example.py "Stadtwerke Bad Pyrmont GmbH" --year 2023
```

Tabular enrichment preserves `capital` and `shareholders_deep` as JSON columns.
Financial summaries retain their existing columns and add JSON metadata
columns, when supplied: `<feature>_provenance` and
`<feature>_activity_statements`, each carrying its year and original payload.

Excel limits cells to 32,767 characters. When an export value exceeds that
limit, its cell contains a JSON `_handelsregister_excel_overflow` reference.
The complete text is split across the **Long values** worksheet, with `row`
(the main-sheet Excel row), `column`, `part`, and `value`. Concatenate the
matching `value` cells in `part` order before decoding JSON. Small exports
retain their existing single-cell format; CSV and JSON preserve values directly.

## `Person` properties

```python
person.entity_id
person.name
person.canonical_name
person.given_name
person.family_name
person.maiden_name
person.previous_names
person.birth_date
person.home_city
person.home_location
person.bio
person.expertise
person.emails
person.phones
person.linkedin
person.github
person.other_profiles

person.handelsregister_roles
person.current_handelsregister_roles
person.get_handelsregister_roles_by_label("MANAGING_DIRECTOR")
person.affiliations

person.shareholdings           # PersonShareholdings (requires feature flag)
```

## Error handling

All API exceptions inherit from `HandelsregisterError`. Documented HTTP
responses are mapped to `RequestValidationError` (HTTP 400/422), `AuthenticationError`,
`InsufficientCreditsError`, `ForbiddenError` /
`SubscriptionRequiredError`, `NotFoundError`, `ConflictError` /
`IdempotencyConflictError` (HTTP 409), `IdempotencyKeyRequiredError`
(HTTP 428), `RateLimitError`, and `RequestTimeoutError` / `ServerError` /
`ServiceUnavailableError` (503 kill switch). Receiver-side signature
failures raise `WebhookSignatureError`. API exceptions preserve
`status_code`, the raw JSON `payload`, and billing metadata through `.meta`.
`SubscriptionRequiredError` additionally exposes `.required_plans`,
`.blocked_filters`, and `.blocked_features` when the API supplies them:

```python
from handelsregister import SubscriptionRequiredError

try:
    page = client.search_organizations(filters={
        "ownership_filters": {"owner_managed": True},
    })
except SubscriptionRequiredError as error:
    print(error)                 # Human-readable server explanation
    print(error.required_plans)  # e.g. ["pro", "max"]
    print(error.blocked_filters)
```

The command-line client renders these failures as a concise plan-required
message on stderr and exits with status 1; it does not print a Python traceback.

Only network failures, HTTP 408/429, and server errors are retried. When supplied,
the API's `Retry-After` header controls the delay. Monitoring mutations retry
with the same idempotency key; HTTP 409 is never retried, and endpoint
verify/test retry only the pre-operation 503 kill switch and HTTP 429
because other failures are ambiguous once the receiver may have been
contacted.

## Security

Do not commit API keys or Bearer tokens. Load credentials from environment
variables or a secret manager, and revoke any credential that may have been
exposed. Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md).

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE).
