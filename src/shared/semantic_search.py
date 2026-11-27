"""Phase 12 semantic-search request and response contracts."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME
from shared.records import ContextRecord

SEMANTIC_SEARCH_PATH = "/records/semantic-search"
SEMANTIC_SEARCH_LIMIT = 20
MAX_SEMANTIC_QUERY_LENGTH = 500
SEMANTIC_PREVIEW_LENGTH = 600
MIN_SEMANTIC_SIMILARITY = 0.35

SemanticSourceKind = Literal["all", "web", "document", "pdf", "docx"]
SemanticSort = Literal["relevance", "recent"]


@dataclass(frozen=True)
class SemanticSearchRequest:
    """Natural-language query combined with optional Phase 11 filters."""

    query: str
    process_name: str = ""
    source_type: SemanticSourceKind = "all"
    active_from: str | None = None
    active_before: str | None = None
    sort: SemanticSort = "relevance"
    limit: int = SEMANTIC_SEARCH_LIMIT


@dataclass(frozen=True)
class SemanticSearchHit:
    """One matching indexed passage and its verified original source."""

    chunk_id: str
    chunk_index: int
    preview: str
    similarity: float
    record: ContextRecord
    content_truncated: bool


@dataclass(frozen=True)
class SemanticSearchResults:
    """Ranked semantic matches. Only a bounded preview is returned per hit."""

    request: SemanticSearchRequest
    hits: list[SemanticSearchHit]
    has_more: bool
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class SemanticSearchResponse:
    data: SemanticSearchResults
    ok: Literal[True] = True
    error: None = None
