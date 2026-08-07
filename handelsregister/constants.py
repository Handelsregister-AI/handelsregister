"""Public constants for the handelsregister.ai API contract."""

from enum import Enum
from typing import Iterable, List, Optional, Union


class OrganizationFeature(str, Enum):
    FINANCIAL_KPI = "financial_kpi"
    BALANCE_SHEET_ACCOUNTS = "balance_sheet_accounts"
    PROFIT_AND_LOSS_ACCOUNT = "profit_and_loss_account"
    RELATED_PERSONS = "related_persons"
    PUBLICATIONS = "publications"
    NEWS = "news"
    INSOLVENCY_PUBLICATIONS = "insolvency_publications"
    ANNUAL_FINANCIAL_STATEMENTS = "annual_financial_statements"
    ANNUAL_FINANCIAL_STATEMENTS_HTML = "annual_financial_statements__html"
    SHAREHOLDERS = "shareholders"
    UBOS = "ubos"
    SHAREHOLDINGS = "shareholdings"
    MERGERS_AND_ACQUISITIONS = "mergers_and_acquisitions"
    WEBSITE_CONTENT = "website_content"


class PersonFeature(str, Enum):
    SHAREHOLDINGS = "shareholdings"


class DocumentType(str, Enum):
    SHAREHOLDERS_LIST = "shareholders_list"
    ARTICLES_OF_ASSOCIATION = "articles_of_association"
    CURRENT_EXCERPT = "AD"
    CHRONOLOGICAL_EXCERPT = "CD"
    STRUCTURED_INFORMATION = "SI"


class SignalTopic(str, Enum):
    NEW_REGISTRATIONS = "NEW_REGISTRATIONS"
    MASTER_DATA_CHANGES = "MASTER_DATA_CHANGES"
    CLOSURES = "CLOSURES"
    ROLE_HOLDER_CHANGES = "ROLE_HOLDER_CHANGES"
    CAPITAL_CHANGES = "CAPITAL_CHANGES"
    INSOLVENCIES = "INSOLVENCIES"
    TRANSFORMATIONS = "TRANSFORMATIONS"


class MonitorStatus(str, Enum):
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED_USER = "paused_user"
    PAUSED_CONFIGURATION = "paused_configuration"
    PAUSED_ENTITLEMENT = "paused_entitlement"
    PAUSED_BILLING = "paused_billing"
    ERROR = "error"
    ARCHIVED = "archived"


class WebhookEndpointStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    DISABLED_USER = "disabled_user"
    DISABLED_FAILURES = "disabled_failures"
    ARCHIVED = "archived"


class WebhookDeliveryStatus(str, Enum):
    WITHHELD = "withheld"
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    BLOCKED_ENDPOINT = "blocked_endpoint"
    EXHAUSTED = "exhausted"
    CANCELLED = "cancelled"


class WebhookEventType(str, Enum):
    SIGNAL_DETECTED = "organization.signal.detected"
    SIGNAL_SAMPLE = "organization.signal.sample"
    ENDPOINT_TEST = "endpoint.test"
    ENDPOINT_VERIFICATION = "endpoint.verification"


ORGANIZATION_FEATURES = tuple(feature.value for feature in OrganizationFeature)
PERSON_FEATURES = tuple(feature.value for feature in PersonFeature)
DOCUMENT_TYPES = tuple(document_type.value for document_type in DocumentType)
SIGNAL_TOPICS = tuple(topic.value for topic in SignalTopic)
MONITOR_STATUSES = tuple(status.value for status in MonitorStatus)
WEBHOOK_ENDPOINT_STATUSES = tuple(status.value for status in WebhookEndpointStatus)
WEBHOOK_DELIVERY_STATUSES = tuple(status.value for status in WebhookDeliveryStatus)
WEBHOOK_EVENT_TYPES = tuple(event_type.value for event_type in WebhookEventType)

# Bearer token abilities used by the account/monitoring routes.
ABILITY_ACCOUNT_READ = "account:read"
ABILITY_MONITORING_MANAGE = "monitoring:manage"
ABILITY_ACCOUNT_KEYS = "account:keys"

MONITOR_MIN_POLL_INTERVAL_DAYS = 1
MONITOR_MAX_POLL_INTERVAL_DAYS = 30
WEBHOOK_MAX_ENDPOINTS = 10

AI_SEARCH_ON = "on-default"
REALTIME_MODE_HANDELSREGISTER = "handelsregister-default"
SEARCH_AI_MODE_ON = "on-default"
SEARCH_ORGANIZATIONS_MAX_LIMIT = 30

REALTIME_INCOMPATIBLE_FEATURES = frozenset(
    {
        OrganizationFeature.RELATED_PERSONS.value,
        OrganizationFeature.PUBLICATIONS.value,
    }
)


FeatureValue = Union[str, Enum]


def normalize_features(
    features: Optional[Union[FeatureValue, Iterable[FeatureValue]]],
) -> List[str]:
    """Normalize feature strings/enums while preserving order and removing duplicates."""
    if features is None:
        return []
    if isinstance(features, (str, Enum)):
        values: Iterable[FeatureValue] = [features]
    else:
        values = features

    normalized: List[str] = []
    seen = set()
    for feature in values:
        value = feature.value if isinstance(feature, Enum) else str(feature)
        value = value.strip()
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized
