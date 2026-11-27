
"""Integration tests for the evidence-grounded RAG API."""

from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.app import create_app
from backend.privacy import PrivacyPolicy
from shared.activity import ActiveWindow
from shared.document import LocalDocument
from shared.rag import RAGAnswer
from shared.search_data import DocumentChunk, SourceMetadata

MODEL_NAME = "intfloat/multilingual-e5-small"


class FakeEmbeddingService:
    """Deterministic query embedding without downloading the E5 model."""

    model_name = MODEL_NAME

    def __init__(self):
        self.queries: list[str] = []

    def embed_query(self, text: str, privacy_policy=None) -> list[float]:
        self.queries.append(text)
        if privacy_policy is not None and privacy_policy.contains_sensitive_data(text):
            raise ValueError("query contains sensitive information")
        return [1.0] + [0.0] * 383


class FakeAnswerGenerator:
    """Return an answer that cites the evidence supplied by the RAG service."""

    def __init__(self, *, should_fail: bool = False):
        self.should_fail = should_fail
        self.queries: list[str] = []
        self.evidence_ids: list[str] = []

    def generate(self, query, evidence) -> RAGAnswer:
        self.queries.append(query)
        self.evidence_ids = [item.id for item in evidence]

        if self.should_fail:
            raise RuntimeError("answer generation failed")

        if not evidence:
            return RAGAnswer(
                text="근거만으로 질문에 답하기 어렵습니다.",
                evidence_ids=[],
            )

        return RAGAnswer(
            text="문서에 따르면 데이터베이스 인덱싱은 검색 성능을 개선합니다.",
            evidence_ids=[evidence[0].id],
        )


def _add_document(
    store: ActivityStore,
    tmp_path,
    *,
    name: str = "database-notes.pdf",
    text: str = (
        "Database indexing improves query performance "
        "by reducing the amount of data scanned."
    ),
    process: str = "Code.exe",
) -> int:
    captured_at = "2026-11-10T10:00:00+00:00"

    context_id = store.save_record(
        window=ActiveWindow(
            application=(
                "Visual Studio Code"
                if process == "Code.exe"
                else "Google Chrome"
            ),
            process_name=process,
            process_id=1234,
            window_title=f"Opened {name}",
        ),
        started_at="2026-11-10T09:00:00+00:00",
        ended_at=captured_at,
        active_duration_ms=60_000,
    )

    path = tmp_path / name
    document_id = store.save_document_record(
        file_path=path,
        extracted_text=text,
        captured_at=captured_at,
        context_id=context_id,
    )

    metadata = SourceMetadata(
        kind="document",
        application=(
            "Visual Studio Code"
            if process == "Code.exe"
            else "Google Chrome"
        ),
        process_name=process,
        window_title=f"Opened {name}",
        started_at="2026-11-10T09:00:00+00:00",
        last_active_at=captured_at,
        captured_at=captured_at,
        content_truncated=False,
        document=LocalDocument(
            file_path=str(path.resolve()),
            file_type=path.suffix.lstrip("."),
        ),
    )

    chunk = DocumentChunk(
        id=f"chunk-{document_id}",
        context_id=str(context_id),
        chunk_index=0,
        text=text,
        source=metadata,
    )

    store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=[chunk],
        document_id=document_id,
        embeddings=[[1.0] + [0.0] * 383],
    )

    return document_id


def _client(
    store: ActivityStore,
    *,
    policy: PrivacyPolicy | None = None,
    generator: FakeAnswerGenerator | None = None,
):
    return TestClient(
        create_app(
            activity_store=store,
            browser_token="test-browser-token",
            privacy_policy=policy,
            embedding_service=FakeEmbeddingService(),
            answer_generator=generator or FakeAnswerGenerator(),
        )
    )


def test_rag_api_returns_answer_and_actual_evidence(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    document_id = _add_document(store, tmp_path)
    generator = FakeAnswerGenerator()

    response = _client(store, generator=generator).post(
        "/records/answer",
        json={"query": "How does database indexing improve performance?"},
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["answer"] == (
        "문서에 따르면 데이터베이스 인덱싱은 검색 성능을 개선합니다."
    )
    assert data["insufficient_evidence"] is False
    assert len(data["evidence"]) == 1
    assert data["evidence"][0]["id"] == f"chunk-{document_id}"
    assert data["evidence"][0]["source_kind"] == "document"
    assert data["evidence"][0]["title"] == "database-notes.pdf"
    assert generator.queries == [
        "How does database indexing improve performance?"
    ]
    assert generator.evidence_ids == [f"chunk-{document_id}"]


def test_rag_api_returns_insufficient_evidence_when_no_records_exist(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    generator = FakeAnswerGenerator()

    response = _client(store, generator=generator).post(
        "/records/answer",
        json={"query": "Explain an unknown topic"},
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["insufficient_evidence"] is True
    assert data["evidence"] == []
    assert data["answer"]
    assert generator.queries == []
    assert generator.evidence_ids == []


def test_rag_api_excludes_blocked_applications(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _add_document(store, tmp_path)
    policy = PrivacyPolicy(
        blocked_applications={"visual studio code"},
    )
    generator = FakeAnswerGenerator()

    response = _client(
        store,
        policy=policy,
        generator=generator,
    ).post(
        "/records/answer",
        json={"query": "database indexing"},
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["insufficient_evidence"] is True
    assert data["evidence"] == []
    assert generator.queries == []


def test_rag_api_rejects_sensitive_query(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")

    response = _client(store).post(
        "/records/answer",
        json={"query": "Contact alice@example.com"},
    )

    assert response.status_code == 422


def test_rag_api_rejects_invalid_query_and_time_range(tmp_path):
    client = _client(ActivityStore(tmp_path / "activity.db"))

    empty_query = client.post(
        "/records/answer",
        json={"query": "   "},
    )
    invalid_range = client.post(
        "/records/answer",
        json={
            "query": "valid query",
            "active_from": "2026-11-11T10:00:00+00:00",
            "active_before": "2026-11-10T10:00:00+00:00",
        },
    )
    naive_datetime = client.post(
        "/records/answer",
        json={
            "query": "valid query",
            "active_from": "2026-11-10T10:00:00",
        },
    )

    assert empty_query.status_code == 422
    assert invalid_range.status_code == 422
    assert naive_datetime.status_code == 422


def test_rag_api_rejects_invalid_source_type_and_limit(tmp_path):
    client = _client(ActivityStore(tmp_path / "activity.db"))

    invalid_source = client.post(
        "/records/answer",
        json={
            "query": "valid query",
            "source_type": "image",
        },
    )
    invalid_limit = client.post(
        "/records/answer",
        json={
            "query": "valid query",
            "limit": 0,
        },
    )

    assert invalid_source.status_code == 422
    assert invalid_limit.status_code == 422


def test_rag_api_returns_service_unavailable_when_generator_fails(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _add_document(store, tmp_path)
    generator = FakeAnswerGenerator(should_fail=True)

    response = _client(store, generator=generator).post(
        "/records/answer",
        json={"query": "database indexing"},
    )

    assert response.status_code == 503
