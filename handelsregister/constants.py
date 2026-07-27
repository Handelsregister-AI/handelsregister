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


ORGANIZATION_FEATURES = tuple(feature.value for feature in OrganizationFeature)
PERSON_FEATURES = tuple(feature.value for feature in PersonFeature)
DOCUMENT_TYPES = tuple(document_type.value for document_type in DocumentType)

AI_SEARCH_ON = "on-default"
REALTIME_MODE_HANDELSREGISTER = "handelsregister-default"
SEARCH_AI_MODE_ON = "on-default"

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
