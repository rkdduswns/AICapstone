
"""Evidence selection and orchestration for retrieval-augmented generation."""

import math
import re
from typing import Protocol

from backend.activity_store import ActivityStore
from backend.embedding import EmbeddingService
from backend.privacy import PrivacyPolicy
from shared.rag import (
    MAX_RAG_EVIDENCE_COUNT,
    MAX_RAG_EVIDENCE_TEXT_LENGTH,
    MIN_RAG_EVIDENCE_SIMILARITY,
    RAGAnswer,
    RAGEvidence,
    RAGRequest,
    RAGResults,
)


class AnswerGenerator(Protocol):
    """Model-independent interface for generating grounded answers."""

    def generate(
        self,
        query: str,
        evidence: list[RAGEvidence],
    ) -> RAGAnswer:
        """Generate an answer using only the supplied evidence."""
        ...


class RAGService:
    """Retrieve, validate, and assemble evidence before answer generation."""

    def __init__(
        self,
        store: ActivityStore,
        embedding_service: EmbeddingService,
        answer_generator: AnswerGenerator,
        privacy_policy: PrivacyPolicy,
    ) -> None:
        self.store = store
        self.embedding_service = embedding_service
        self.answer_generator = answer_generator
        self.privacy_policy = privacy_policy

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize whitespace for exact duplicate detection."""
        return re.sub(r"\s+", " ", text).strip().casefold()

    @staticmethod
    def _source_details(
        hit: dict,
    ) -> tuple[str, str, str | None, str | None]:
        """Resolve source identity and display metadata from a search hit."""
        record = hit["record"]

        if record.browser is not None:
            return (
                "web",
                record.browser.page_title or record.window_title,
                record.browser.url,
                None,
            )

        if record.document is not None:
            file_path = record.document.file_path

            return (
                "document",
                file_path.replace("\\", "/").rsplit("/", 1)[-1],
                None,
                file_path,
            )

        raise ValueError("Search hit has no supported source")

    def _select_evidence(
        self,
        hits: list[dict],
        limit: int,
    ) -> list[RAGEvidence]:
        """Load full passages, remove duplicates, and recheck privacy."""
        selected: list[RAGEvidence] = []
        seen_chunks: set[str] = set()
        seen_content: set[tuple[str, str]] = set()

        for hit in hits:
            if len(selected) >= limit:
                break

            chunk_id = hit.get("chunk_id")

            if (
                not isinstance(chunk_id, str)
                or not chunk_id.strip()
                or chunk_id in seen_chunks
            ):
                continue

            similarity = hit.get("similarity")

            if (
                isinstance(similarity, bool)
                or not isinstance(similarity, (int, float))
                or not math.isfinite(float(similarity))
                or similarity < MIN_RAG_EVIDENCE_SIMILARITY
            ):
                continue

            try:
                source_kind, title, url, file_path = self._source_details(
                    hit
                )
            except (KeyError, AttributeError, TypeError, ValueError):
                continue

            if not isinstance(title, str) or not title.strip():
                continue

            if url is not None:
                try:
                    url = self.privacy_policy.sanitize_browser_url(url)
                except (TypeError, ValueError):
                    continue

                if not isinstance(url, str) or not url:
                    continue

            if file_path is not None:
                if not isinstance(file_path, str) or not file_path.strip():
                    continue

                # Do not pass sensitive local paths to the generator.
                if self.privacy_policy.contains_sensitive_data(file_path):
                    file_path = None

            full_text = self.store.get_search_chunk_text(chunk_id)

            if not isinstance(full_text, str) or not full_text.strip():
                continue

            # Recheck the complete passage immediately before generation.
            if self.privacy_policy.contains_sensitive_data(full_text):
                continue

            record = hit["record"]

            if self.privacy_policy.is_blocked(
                record.application,
                record.process_name,
            ):
                continue

            safe_title = self.privacy_policy.sanitize_title(title)

            if not isinstance(safe_title, str) or not safe_title.strip():
                continue

            source_identity = (
                url
                or file_path
                or str(record.id)
            )

            normalized = self._normalize_text(full_text)
            duplicate_key = (
                source_identity.casefold(),
                normalized,
            )

            if duplicate_key in seen_content:
                continue

            chunk_index = hit.get("chunk_index")

            if (
                isinstance(chunk_index, bool)
                or not isinstance(chunk_index, int)
                or chunk_index < 0
            ):
                continue

            seen_chunks.add(chunk_id)
            seen_content.add(duplicate_key)

            selected.append(
                RAGEvidence(
                    id=chunk_id,
                    source_kind=source_kind,
                    title=safe_title,
                    text=full_text[:MAX_RAG_EVIDENCE_TEXT_LENGTH],
                    similarity=float(similarity),
                    chunk_index=chunk_index,
                    captured_at=record.last_active_at,
                    url=url,
                    file_path=file_path,
                    content_truncated=(
                        bool(hit.get("content_truncated"))
                        or len(full_text) > MAX_RAG_EVIDENCE_TEXT_LENGTH
                    ),
                )
            )

        return selected

    def answer(self, request: RAGRequest) -> RAGResults:
        """Answer a question using verified search evidence only."""
        if not isinstance(request.query, str):
            raise ValueError("query must be a string")

        query = request.query.strip()

        if not query or len(query) > 500:
            raise ValueError(
                "query must contain between 1 and 500 characters"
            )

        if self.privacy_policy.contains_sensitive_data(query):
            raise ValueError("query contains sensitive information")

        if (
            isinstance(request.limit, bool)
            or not isinstance(request.limit, int)
            or not 1 <= request.limit <= MAX_RAG_EVIDENCE_COUNT
        ):
            raise ValueError(
                f"limit must be between 1 and {MAX_RAG_EVIDENCE_COUNT}"
            )

        if not isinstance(request.process_name, str):
            raise ValueError("process_name must be a string")

        if len(request.process_name) > 255:
            raise ValueError("process_name is too long")

        query_vector = self.embedding_service.embed_query(
            query,
            privacy_policy=self.privacy_policy,
        )

        hits, _ = self.store.search_semantic_chunks(
            query_vector,
            model_name=self.embedding_service.model_name,
            process_name=request.process_name,
            source_type=request.source_type,
            active_from=request.active_from,
            active_before=request.active_before,
            sort="relevance",
            limit=20,
            privacy_policy=self.privacy_policy,
        )

        evidence = self._select_evidence(
            hits,
            limit=request.limit,
        )

        if not evidence:
            return RAGResults(
                request=request,
                answer="관련된 충분한 근거를 찾지 못했습니다.",
                evidence=[],
                insufficient_evidence=True,
            )

        generated = self.answer_generator.generate(
            query,
            evidence,
        )

        if not isinstance(generated, RAGAnswer):
            raise TypeError("answer generator must return RAGAnswer")

        if not isinstance(generated.text, str):
            raise TypeError("generated answer text must be a string")

        if not isinstance(generated.evidence_ids, list):
            raise TypeError("evidence_ids must be a list")

        if any(
            not isinstance(item, str)
            for item in generated.evidence_ids
        ):
            raise ValueError("evidence_ids must contain only strings")

        allowed_ids = {item.id for item in evidence}
        cited_ids = list(dict.fromkeys(generated.evidence_ids))

        # Reject references that do not belong to retrieved evidence.
        if any(item not in allowed_ids for item in cited_ids):
            raise ValueError("answer contains an unknown evidence reference")

        answer_text = generated.text.strip()

        if not answer_text:
            raise ValueError("answer generator returned empty text")

        # URLs belong in verified evidence metadata, not generated prose.
        if re.search(r"https?://", answer_text, re.IGNORECASE):
            raise ValueError("generated answer must not contain URLs")

        # A generated answer without evidence references is not trustworthy.
        if not cited_ids:
            return RAGResults(
                request=request,
                answer="검색된 근거만으로는 질문에 답하기 어렵습니다.",
                evidence=[],
                insufficient_evidence=True,
            )

        cited_evidence = [
            item for item in evidence if item.id in cited_ids
        ]

        return RAGResults(
            request=request,
            answer=answer_text,
            evidence=cited_evidence,
            insufficient_evidence=False,
        )
