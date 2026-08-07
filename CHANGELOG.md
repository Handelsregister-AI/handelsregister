# Changelog

All notable changes to the Python package are documented here.

## 0.7.0 - 2026-08-07

- **License change: the package is now distributed under the GNU Affero
  General Public License v3.0 (previously MIT).**
- Add full Organization Monitoring support: pricing, monitor create/list/
  show/update/pause/resume/archive.
- Keep the pricing policy version informational: monitor mutations no longer
  accept or send a user-supplied `pricing_policy_version`.
- Update Signals billing documentation and examples: catalog requests are
  free; successful list pages and detail requests cost 20 credits each.
- Add webhook endpoint management: create, verify, rotate-secret, test,
  enable/disable, archive, plus delivery listing/retry and event listing.
- Send a durable `Idempotency-Key` on every monitoring mutation, reuse it
  across internal retries, and expose `client.last_idempotency_status`
  (`created`/`replayed`).
- Map HTTP 409 to `ConflictError` / `IdempotencyConflictError` (never
  retried), HTTP 428 to `IdempotencyKeyRequiredError`, and the 503 execution
  kill switch to `ServiceUnavailableError` (safely retried with the same key).
- Endpoint verify/test retry only HTTP 429 and the pre-operation kill switch;
  other failures surface immediately because receiver-side effects are
  ambiguous. A failed verification challenge returns the documented
  `{"verified": false}` payload instead of raising.
- Add `handelsregister.webhooks` receiver helpers:
  `verify_webhook_signature()`, `construct_event()`,
  `extract_verification_challenge()`, and `verification_response_headers()`
  with multi-secret rotation grace and timestamp tolerance.
- Add `MonitorStatus`, `WebhookEndpointStatus`, `WebhookDeliveryStatus`,
  `WebhookEventType` enums and the `monitoring:manage` / `account:keys`
  ability constants.
- Add `monitors` and `webhooks` CLI command groups.
- Send `Accept: application/json` on all JSON endpoints so validation
  failures surface as 422 Problem JSON instead of an opaque 302 redirect;
  binary document downloads are unaffected. Unexpected redirects now raise
  a descriptive `APIError`.
- Fix the README token-management example: a future `expires_at`, real
  revocation via the id from `list_tokens()`, and documented ability
  normalization (`["*"]` becomes `api:data` + `account:read`;
  `account:keys` cannot be self-granted).
- Add a `HANDELSREGISTER_EXTRA_HEADERS` environment fallback for gateways or
  proxies that require additional request headers.
- Fix the README enrichment example: `enrich()` takes `output_file` and
  `output_type`, not `output_format`.

## 0.6.0 - 2026-07-30

- Add all Account API reads: profile, credits, usage, usage transactions,
  subscription, and masked API-key listing.
- Add Bearer-only API-key creation and revocation.
- Add Signals list, catalog, detail, and lazy cursor pagination APIs.
- Add the public `SignalTopic` enum and `SIGNAL_TOPICS` values.
- Add optional generic request headers for custom gateways and proxies.
- Add a runnable Account and Signals demo with credential redaction and an
  opt-in API-key lifecycle check.
- Validate custom header names and values, avoid logging query values, and add
  pre-release CI across Python 3.8 through 3.13.
- Map Problem JSON `PLAN_REQUIRED` responses to
  `SubscriptionRequiredError`.

## 0.5.1

- Correct the documented `/v1/search-organizations` maximum to 30 results per
  request and expose it as `SEARCH_ORGANIZATIONS_MAX_LIMIT`.
- Reject search limits above 30 instead of allowing silently truncated pages.
- Add `Handelsregister.iter_search_organizations()` for lazy, automatic
  pagination when more than 30 organizations are needed.
- Clarify that each fetched search page is a separate billable API request.

## 0.5.0

- Add current organization features, person-level representation schemes, and
  mergers and acquisitions support.
- Add bearer-token authentication and structured API exceptions.
- Add current search filters, document formats, and response models.
- Migrate PyPI releases to GitHub Actions Trusted Publishing.
