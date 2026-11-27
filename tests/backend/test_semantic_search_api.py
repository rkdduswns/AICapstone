"""Integration tests for Phase 12 semantic and hybrid search."""

from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.app import create_app
from backend.privacy import PrivacyPolicy
from shared.activity import ActiveWindow
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.search_data import DocumentChunk, SourceMetadata

MODEL_NAME = "intfloat/multilingual-e5-small"


class FakeEmbeddingService:
    """Deterministic query embedding without downloading the E5 model."""

    model_name = MODEL_NAME

    def __init__(self, vector: list[float] | None = None):
        self.vector = vector or [1.0] + [0.0] * 383
        self.queries: list[str] = []

    def embed_query(self, text: str, privacy_policy=None) -> list[float]:
        self.queries.append(text)
        if privacy_policy is not None and privacy_policy.contains_sensitive_data(text):
            raise ValueError("query contains sensitive information")
        return self.vector


def _activity(store: ActivityStore, *, title: str, process: str, ended_at: str) -> int:
    return store.save_record(
        window=ActiveWindow(
            application="Visual Studio Code" if process == "Code.exe" else "Google Chrome",
            process_name=process,
            process_id=1234,
            window_title=title,
        ),
        started_at="2026-11-10T09:00:00+00:00",
        ended_at=ended_at,
        active_duration_ms=60_000,
    )


def _add_document(
    store: ActivityStore,
    tmp_path,
    *,
    name: str,
    text: str,
    vector: list[float],
    ended_at: str = "2026-11-10T10:00:00+00:00",
    process: str = "Code.exe",
) -> int:
    context_id = _activity(
        store,
        title=f"Opened {name}",
        process=process,
        ended_at=ended_at,
    )
    path = tmp_path / name
    document_id = store.save_document_record(
        file_path=path,
        extracted_text=text,
        captured_at=ended_at,
        context_id=context_id,
    )
    metadata = SourceMetadata(
        kind="document",
        application="Visual Studio Code" if process == "Code.exe" else "Google Chrome",
        process_name=process,
        window_title=f"Opened {name}",
        started_at="2026-11-10T09:00:00+00:00",
        last_active_at=ended_at,
        captured_at=ended_at,
        content_truncated=False,
        document=LocalDocument(file_path=str(path.resolve()), file_type=path.suffix.lstrip(".")),
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
        embeddings=[vector],
    )
    return context_id


def _add_web(
    store: ActivityStore,
    *,
    text: str,
    vector: list[float],
    captured_at: str = "2026-11-10T11:00:00+00:00",
) -> int:
    context_id = _activity(
        store,
        title="Browser research",
        process="chrome.exe",
        ended_at=captured_at,
    )
    browser_source_id = store.save_browser_source_record(
        browser="chrome",
        url="https://example.com/research",
        page_title="Research article",
        captured_at=captured_at,
    )
    metadata = SourceMetadata(
        kind="web",
        application="Google Chrome",
        process_name="chrome.exe",
        window_title="Research article - Chrome",
        started_at=captured_at,
        last_active_at=captured_at,
        captured_at=captured_at,
        content_truncated=False,
        browser=BrowserPage(
            browser="chrome",
            page_title="Research article",
            url="https://example.com/research",
        ),
    )
    chunk = DocumentChunk(
        id=f"web-chunk-{browser_source_id}",
        context_id=str(context_id),
        chunk_index=0,
        text=text,
        source=metadata,
    )
    store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=[chunk],
        browser_source_id=browser_source_id,
        embeddings=[vector],
    )
    return browser_source_id


def _client(store: ActivityStore, embedding, policy: PrivacyPolicy | None = None):
    return TestClient(
        create_app(
            activity_store=store,
            browser_token="test-browser-token",
            privacy_policy=policy,
            embedding_service=embedding,
        )
    )


def test_semantic_search_ranks_by_similarity_and_restores_document_path(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    best_vector = [1.0] + [0.0] * 383
    weaker_vector = [0.8, 0.6] + [0.0] * 382
    _add_document(
        store,
        tmp_path,
        name="best.pdf",
        text="A detailed explanation of database indexing and query planning.",
        vector=best_vector,
    )
    _add_document(
        store,
        tmp_path,
        name="weaker.docx",
        text="A general note about application development.",
        vector=weaker_vector,
    )
    embedding = FakeEmbeddingService()

    response = _client(store, embedding).post(
        "/records/semantic-search",
        json={"query": "how database queries are optimized"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["hits"]) == 2
    assert data["hits"][0]["chunk_id"] == "chunk-1"
    assert data["hits"][0]["similarity"] > data["hits"][1]["similarity"]
    assert data["hits"][0]["record"]["document"]["file_path"].endswith("best.pdf")
    assert "database indexing" in data["hits"][0]["preview"]
    assert embedding.queries == ["how database queries are optimized"]


def test_semantic_search_combines_process_time_and_source_filters(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    vector = [1.0] + [0.0] * 383
    _add_document(
        store,
        tmp_path,
        name="matching.pdf",
        text="Machine learning search notes",
        vector=vector,
        ended_at="2026-11-10T10:00:00+00:00",
        process="Code.exe",
    )
    _add_web(
        store,
        text="Machine learning article",
        vector=vector,
        captured_at="2026-11-10T12:00:00+00:00",
    )

    response = _client(store, FakeEmbeddingService()).post(
        "/records/semantic-search",
        json={
            "query": "find my machine learning research",
            "process_name": "CODE.EXE",
            "source_type": "pdf",
            "active_from": "2026-11-10T09:30:00+00:00",
            "active_before": "2026-11-10T10:30:00+00:00",
        },
    )

    assert response.status_code == 200
    hits = response.json()["data"]["hits"]
    assert len(hits) == 1
    assert hits[0]["record"]["document"]["file_type"] == "pdf"


def test_semantic_search_returns_web_url_for_web_source(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _add_web(
        store,
        text="Research on vector databases and semantic retrieval",
        vector=[1.0] + [0.0] * 383,
    )

    response = _client(store, FakeEmbeddingService()).post(
        "/records/semantic-search",
        json={"query": "vector database research", "source_type": "web"},
    )

    assert response.status_code == 200
    hit = response.json()["data"]["hits"][0]
    assert hit["record"]["id"] == hit["context_id"] == "1"
    assert hit["record"]["browser"]["url"] == "https://example.com/research"


def test_semantic_search_excludes_unrelated_similarity(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _add_document(
        store,
        tmp_path,
        name="unrelated.pdf",
        text="An unrelated document",
        vector=[0.0, 1.0] + [0.0] * 382,
    )

    response = _client(store, FakeEmbeddingService()).post(
        "/records/semantic-search",
        json={"query": "something completely different"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["hits"] == []
    assert response.json()["data"]["has_more"] is False


def test_semantic_search_excludes_blocked_applications(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _add_document(
        store,
        tmp_path,
        name="private.pdf",
        text="Private but otherwise relevant content",
        vector=[1.0] + [0.0] * 383,
    )
    policy = PrivacyPolicy(blocked_applications={"visual studio code"})

    response = _client(store, FakeEmbeddingService(), policy).post(
        "/records/semantic-search",
        json={"query": "relevant content"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["hits"] == []


def test_semantic_search_rejects_invalid_query_and_time_range(tmp_path):
    client = _client(
        ActivityStore(tmp_path / "activity.db"),
        FakeEmbeddingService(),
    )
    empty = client.post("/records/semantic-search", json={"query": "   "})
    invalid_range = client.post(
        "/records/semantic-search",
        json={
            "query": "valid query",
            "active_from": "2026-11-11T10:00:00+00:00",
            "active_before": "2026-11-10T10:00:00+00:00",
        },
    )
    naive = client.post(
        "/records/semantic-search",
        json={"query": "valid query", "active_from": "2026-11-10T10:00:00"},
    )

    assert empty.status_code == 422
    assert invalid_range.status_code == 422
    assert naive.status_code == 422
