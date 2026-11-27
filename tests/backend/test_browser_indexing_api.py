"""Tests for authenticated browser capture and search indexing."""

import json

from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.app import create_app


class FakeEmbeddingService:
    """Deterministic embedding service for API tests."""

    model_name = "test-embedding-model"

    def split_passage(self, text: str, privacy_policy=None) -> list[str]:
        return [text]

    def embed_passages(
        self,
        texts: list[str],
        privacy_policy=None,
    ) -> list[list[float]]:
        return [[0.1] * 384 for _ in texts]


def create_client(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    client = TestClient(
        create_app(
            activity_store=store,
            browser_token="test-browser-token",
            embedding_service=FakeEmbeddingService(),
        )
    )
    return client, store


def test_browser_content_is_indexed_without_activity_context(tmp_path):
    client, store = create_client(tmp_path)
    headers = {"Authorization": "Bearer test-browser-token"}

    source_response = client.post(
        "/browser/source",
        headers=headers,
        json={
            "browser": "chrome",
            "url": "https://example.com/article?private=value#section",
            "page_title": "Example Article",
        },
    )
    assert source_response.status_code == 200
    source_id = source_response.json()["data"]["id"]

    content_response = client.post(
        "/browser/content",
        headers=headers,
        json={
            "browser_source_id": source_id,
            "content_text": "ContextTrace browser indexing test content",
        },
    )

    assert content_response.status_code == 200
    body = content_response.json()["data"]
    assert body["search_source_id"] is not None

    saved_content = store.get_browser_content_record(source_id)
    assert saved_content is not None
    assert "browser indexing test" in saved_content.content_text

    chunks = store.get_search_chunks(body["search_source_id"])
    assert len(chunks) == 1
    assert chunks[0]["text"] == "ContextTrace browser indexing test content"

    embedding = store.get_semantic_embedding(chunks[0]["id"])
    assert embedding is not None
    assert embedding["dimension"] == 384

    with store._connect() as connection:
        source = connection.execute(
            "SELECT context_id, metadata_json FROM search_sources WHERE id = ?",
            (body["search_source_id"],),
        ).fetchone()

    assert source["context_id"] is None
    metadata = json.loads(source["metadata_json"])
    assert metadata["kind"] == "web"
    assert metadata["browser"]["url"] == "https://example.com/article"


def test_browser_content_with_sensitive_data_is_rejected(tmp_path):
    client, store = create_client(tmp_path)
    headers = {"Authorization": "Bearer test-browser-token"}

    source_response = client.post(
        "/browser/source",
        headers=headers,
        json={
            "browser": "chrome",
            "url": "https://example.com/",
            "page_title": "Example",
        },
    )
    source_id = source_response.json()["data"]["id"]

    response = client.post(
        "/browser/content",
        headers=headers,
        json={
            "browser_source_id": source_id,
            "content_text": "Contact me at person@example.com",
        },
    )

    assert response.status_code == 403
    assert store.get_browser_content_record(source_id) is None


def test_browser_content_requires_bearer_token(tmp_path):
    client, _ = create_client(tmp_path)

    response = client.post(
        "/browser/content",
        json={
            "browser_source_id": 1,
            "content_text": "Some page text",
        },
    )

    assert response.status_code == 401
