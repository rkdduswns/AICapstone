"""Shared request and response contracts for evidence-grounded RAG."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME
from shared.search_data import SourceMetadata

RAG_PATH = "/records/answer"

MAX_RAG_QUERY_LENGTH = 500
MAX_RAG_EVIDENCE_COUNT = 5
MAX_RAG_EVIDENCE_TEXT_LENGTH = 4000
MIN_RAG_EVIDENCE_SIMILARITY = 0.35

RAGSourceKind = Literal["web", "document"]


@dataclass(frozen=True)
class RAGRequest:
    """Natural-language question with optional search filters."""

    query: str
    process_name: str = ""
    source_type: Literal["all", "web", "document", "pdf", "docx"] = "all"
    active_from: str | None = None
    active_before: str | None = None
    limit: int = MAX_RAG_EVIDENCE_COUNT


@dataclass(frozen=True)
class RAGEvidence:
    """A verified source passage selected for answer generation."""

    id: str
    source_kind: RAGSourceKind
    title: str
    text: str
    similarity: float
    chunk_index: int
    captured_at: str
    url: str | None = None
    file_path: str | None = None
    content_truncated: bool = False
    # 실제 작업이 없는 독립 웹 수집에는 ID를 만들어 넣지 않는다.
    context_id: str | None = None
    source: SourceMetadata | None = None


@dataclass(frozen=True)
class RAGAnswer:
    """Generated answer and the evidence IDs cited by the generator."""

    text: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class RAGResults:
    """Answer, evidence sources, and insufficient-evidence status."""

    request: RAGRequest
    answer: str
    evidence: list[RAGEvidence]
    insufficient_evidence: bool
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class RAGResponse:
    """Standard API envelope for a RAG response."""

    data: RAGResults
    ok: Literal[True] = True
    error: None = None
