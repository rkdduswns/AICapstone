
"""Tests for evidence-grounded RAG orchestration."""

from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import pytest

from backend.rag_service import RAGService
from shared.rag import RAGAnswer, RAGEvidence, RAGRequest


class FakePrivacyPolicy:
    """Minimal privacy policy for RAG service tests."""

    def contains_sensitive_data(self, text: str) -> bool:
        return "test@example.com" in text

    def is_blocked(
        self,
        application: str,
        process_name: str,
    ) -> bool:
        return application == "BlockedApp"

    def sanitize_title(self, title: str) -> str:
        return title

    def sanitize_browser_url(self, url: str) -> str:
        parsed = urlsplit(url)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("unsupported URL")

        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "",
                "",
            )
        )


class FakeEmbeddingService:
    """Deterministic embedding service for tests."""

    model_name = "test-model"

    def embed_query(
        self,
        text: str,
        privacy_policy=None,
    ) -> list[float]:
        return [1.0] * 384


class FakeActivityStore:
    """In-memory search results and chunk text."""

    def __init__(
        self,
        hits: list[dict],
        chunk_texts: dict[str, str],
    ) -> None:
        self.hits = hits
        self.chunk_texts = chunk_texts
        self.search_calls = []

    def search_semantic_chunks(
        self,
        query_vector: list[float],
        **kwargs,
    ) -> tuple[list[dict], bool]:
        self.search_calls.append(
            {
                "query_vector": query_vector,
                **kwargs,
            }
        )
        return self.hits, False

    def get_search_chunk_text(
        self,
        chunk_id: str,
    ) -> str | None:
        return self.chunk_texts.get(chunk_id)


class FakeAnswerGenerator:
    """Answer generator that cites all supplied evidence."""

    def __init__(self, answer: str = "테스트 답변입니다.") -> None:
        self.answer = answer
        self.calls = []

    def generate(
        self,
        query: str,
        evidence: list[RAGEvidence],
    ) -> RAGAnswer:
        self.calls.append(
            {
                "query": query,
                "evidence": evidence,
            }
        )

        return RAGAnswer(
            text=self.answer,
            evidence_ids=[item.id for item in evidence],
        )


def make_hit(
    chunk_id: str,
    *,
    source_kind: str = "web",
    source_id: int = 1,
    similarity: float = 0.9,
    chunk_index: int = 0,
    application: str = "Chrome",
    process_name: str = "chrome.exe",
    url: str = "https://example.com/article",
    page_title: str = "Example article",
    file_path: str = "C:/Documents/example.pdf",
    content_truncated: bool = False,
) -> dict:
    """Build a search hit with source metadata."""

    browser = None
    document = None

    if source_kind == "web":
        browser = SimpleNamespace(
            browser="chrome",
            page_title=page_title,
            url=url,
        )
    elif source_kind == "document":
        document = SimpleNamespace(
            file_path=file_path,
            file_type="pdf",
        )
    else:
        raise ValueError("unsupported test source_kind")

    record = SimpleNamespace(
        id=source_id,
        application=application,
        process_name=process_name,
        window_title=page_title,
        last_active_at="2026-11-19T10:00:00+09:00",
        browser=browser,
        document=document,
    )

    return {
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "similarity": similarity,
        "record": record,
        "content_truncated": content_truncated,
    }


def make_service(
    hits: list[dict],
    chunk_texts: dict[str, str],
    generator: FakeAnswerGenerator | None = None,
) -> tuple[RAGService, FakeActivityStore, FakeAnswerGenerator]:
    """Create a RAG service with fake dependencies."""

    store = FakeActivityStore(hits, chunk_texts)
    answer_generator = generator or FakeAnswerGenerator()

    service = RAGService(
        store=store,
        embedding_service=FakeEmbeddingService(),
        answer_generator=answer_generator,
        privacy_policy=FakePrivacyPolicy(),
    )

    return service, store, answer_generator


def test_answer_with_single_evidence() -> None:
    """A question with one matching source returns that source."""

    hits = [
        make_hit("chunk-1"),
    ]
    texts = {
        "chunk-1": "ContextTrace는 사용자의 작업 기록을 검색하는 시스템이다.",
    }

    service, _, generator = make_service(hits, texts)

    result = service.answer(
        RAGRequest(query="ContextTrace는 무엇인가?")
    )

    assert result.insufficient_evidence is False
    assert result.answer == "테스트 답변입니다."
    assert len(result.evidence) == 1
    assert result.evidence[0].id == "chunk-1"
    assert len(generator.calls) == 1


def test_answer_with_multiple_evidence() -> None:
    """A question can use evidence from multiple web sources."""

    hits = [
        make_hit(
            "chunk-1",
            source_id=1,
            url="https://example.com/one",
        ),
        make_hit(
            "chunk-2",
            source_id=2,
            url="https://example.com/two",
            page_title="Second article",
        ),
    ]
    texts = {
        "chunk-1": "첫 번째 문서의 관련 내용이다.",
        "chunk-2": "두 번째 문서의 추가 설명이다.",
    }

    service, _, _ = make_service(hits, texts)

    result = service.answer(
        RAGRequest(query="두 문서의 내용을 설명해 줘.")
    )

    assert result.insufficient_evidence is False
    assert len(result.evidence) == 2
    assert {item.id for item in result.evidence} == {
        "chunk-1",
        "chunk-2",
    }


def test_duplicate_evidence_from_same_source_is_removed() -> None:
    """Identical passages from the same source are included only once."""

    hits = [
        make_hit("chunk-1"),
        make_hit("chunk-2"),
    ]
    texts = {
        "chunk-1": "동일한 검색 근거 내용입니다.",
        "chunk-2": "동일한   검색 근거 내용입니다.",
    }

    service, _, _ = make_service(hits, texts)

    result = service.answer(
        RAGRequest(query="검색 근거를 알려 줘.")
    )

    assert len(result.evidence) == 1
    assert result.evidence[0].id == "chunk-1"


def test_similar_text_from_different_documents_is_preserved() -> None:
    """Similar passages from different documents remain distinguishable."""

    hits = [
        make_hit(
            "chunk-1",
            source_kind="document",
            source_id=1,
            file_path="C:/Documents/first.pdf",
        ),
        make_hit(
            "chunk-2",
            source_kind="document",
            source_id=2,
            file_path="C:/Documents/second.pdf",
        ),
    ]
    texts = {
        "chunk-1": "두 문서에 공통으로 포함된 유사한 내용입니다.",
        "chunk-2": "두 문서에 공통으로 포함된 유사한 내용입니다.",
    }

    service, _, _ = make_service(hits, texts)

    result = service.answer(
        RAGRequest(query="문서 내용을 비교해 줘.")
    )

    assert len(result.evidence) == 2
    assert {item.id for item in result.evidence} == {
        "chunk-1",
        "chunk-2",
    }


def test_no_evidence_returns_insufficient_result() -> None:
    """No matching evidence produces an insufficient-evidence response."""

    service, _, generator = make_service([], {})

    result = service.answer(
        RAGRequest(query="검색 기록에 없는 질문")
    )

    assert result.insufficient_evidence is True
    assert result.evidence == []
    assert "근거" in result.answer
    assert generator.calls == []


def test_sensitive_evidence_is_excluded() -> None:
    """Evidence containing sensitive information is never generated."""

    hits = [
        make_hit("chunk-1"),
    ]
    texts = {
        "chunk-1": "사용자 이메일은 test@example.com이다.",
    }

    service, _, generator = make_service(hits, texts)

    result = service.answer(
        RAGRequest(query="사용자 정보는?")
    )

    assert result.insufficient_evidence is True
    assert result.evidence == []
    assert generator.calls == []


def test_blocked_application_evidence_is_excluded() -> None:
    """Evidence from a blocked application is excluded."""

    hits = [
        make_hit(
            "chunk-1",
            application="BlockedApp",
        ),
    ]
    texts = {
        "chunk-1": "민감한 애플리케이션의 기록이다.",
    }

    service, _, generator = make_service(hits, texts)

    result = service.answer(
        RAGRequest(query="이 기록의 내용은?")
    )

    assert result.insufficient_evidence is True
    assert result.evidence == []
    assert generator.calls == []


def test_unknown_evidence_reference_is_rejected() -> None:
    """The generator cannot cite a source outside retrieved evidence."""

    class InvalidReferenceGenerator:
        def generate(
            self,
            query: str,
            evidence: list[RAGEvidence],
        ) -> RAGAnswer:
            return RAGAnswer(
                text="검증되지 않은 답변",
                evidence_ids=["nonexistent-chunk"],
            )

    service = RAGService(
        store=FakeActivityStore(
            [make_hit("chunk-1")],
            {"chunk-1": "검증 가능한 근거 내용이다."},
        ),
        embedding_service=FakeEmbeddingService(),
        answer_generator=InvalidReferenceGenerator(),
        privacy_policy=FakePrivacyPolicy(),
    )

    with pytest.raises(
        ValueError,
        match="unknown evidence reference",
    ):
        service.answer(
            RAGRequest(query="근거를 확인해 줘.")
        )


def test_generated_answer_url_is_rejected() -> None:
    """The generator cannot invent URLs in answer text."""

    generator = FakeAnswerGenerator(
        answer="자세한 내용은 https://fake.example.com 에 있습니다."
    )

    service, _, _ = make_service(
        [make_hit("chunk-1")],
        {"chunk-1": "검증 가능한 근거 내용이다."},
        generator,
    )

    with pytest.raises(ValueError, match="must not contain URLs"):
        service.answer(
            RAGRequest(query="관련 내용을 알려 줘.")
        )


def test_requested_evidence_limit_is_respected() -> None:
    """The number of returned evidence items follows request.limit."""

    hits = [
        make_hit(
            "chunk-1",
            source_id=1,
            url="https://example.com/one",
        ),
        make_hit(
            "chunk-2",
            source_id=2,
            url="https://example.com/two",
        ),
        make_hit(
            "chunk-3",
            source_id=3,
            url="https://example.com/three",
        ),
    ]
    texts = {
        "chunk-1": "첫 번째 근거",
        "chunk-2": "두 번째 근거",
        "chunk-3": "세 번째 근거",
    }

    service, _, _ = make_service(hits, texts)

    result = service.answer(
        RAGRequest(
            query="관련 내용을 알려 줘.",
            limit=2,
        )
    )

    assert len(result.evidence) == 2


@pytest.mark.parametrize("limit", [0, 6, -1, True])
def test_invalid_evidence_limit_is_rejected(limit) -> None:
    """Evidence limits outside the supported range are rejected."""

    service, store, generator = make_service([], {})

    with pytest.raises(ValueError, match="limit"):
        service.answer(
            RAGRequest(
                query="테스트 질문",
                limit=limit,
            )
        )

    assert store.search_calls == []
    assert generator.calls == []


def test_low_similarity_evidence_is_excluded() -> None:
    """Evidence below the minimum similarity threshold is excluded."""

    hits = [
        make_hit(
            "chunk-1",
            similarity=0.2,
        ),
    ]
    texts = {
        "chunk-1": "유사도가 낮은 근거 내용이다.",
    }

    service, _, generator = make_service(hits, texts)

    result = service.answer(
        RAGRequest(query="관련 내용을 알려 줘.")
    )

    assert result.insufficient_evidence is True
    assert result.evidence == []
    assert generator.calls == []
