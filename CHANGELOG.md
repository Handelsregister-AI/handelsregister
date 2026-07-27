# Changelog

All notable changes to the Python package are documented here.

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
