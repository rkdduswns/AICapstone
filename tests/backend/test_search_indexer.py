
"""Tests for the search indexing pipeline."""

import pytest

from backend.activity_store import ActivityStore
from backend.search_indexer import SearchIndexer
from shared.activity import ActiveWindow
from shared.document import LocalDocument
from shared.search_data import SourceMetadata


class FakeEmbeddingService:
    """Deterministic embedding service for unit tests."""

    model_name = "test-embedding-model"

    def split_passage(
        self,
        text,
        privacy_policy=None,
    ):
        return [text]

    def embed_passages(
        self,
        texts,
        privacy_policy=None,
    ):
        return [
            [0.1] * 384
            for _ in texts
        ]


def create_indexing_fixture(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")

    window = ActiveWindow(
        application="Visual Studio Code",
        process_name="Code.exe",
        process_id=1234,
        window_title="test.py - ContextTrace",
    )

    context_id = store.save_record(
        window=window,
        started_at="2026-11-10T10:00:00+00:00",
        ended_at="2026-11-10T10:05:00+00:00",
        active_duration_ms=300000,
    )

    document_path = tmp_path / "test.docx"

    document_id = store.save_document_record(
        file_path=document_path,
        file_name="test.docx",
        extracted_text="ContextTrace indexing test",
        captured_at="2026-11-10T10:05:00+00:00",
        context_id=context_id,
    )

    metadata = SourceMetadata(
        kind="document",
        application=window.application,
        process_name=window.process_name,
        window_title=window.window_title,
        started_at="2026-11-10T10:00:00+00:00",
        last_active_at="2026-11-10T10:05:00+00:00",
        captured_at="2026-11-10T10:05:00+00:00",
        content_truncated=False,
        document=LocalDocument(
            file_path=str(document_path.resolve()),
            file_type="docx",
        ),
    )

    indexer = SearchIndexer(
        store=store,
        embedding_service=FakeEmbeddingService(),
    )

    return store, indexer, context_id, document_id, metadata


def test_index_document_source_success(tmp_path):
    (
        store,
        indexer,
        context_id,
        document_id,
        metadata,
    ) = create_indexing_fixture(tmp_path)

    source_id = indexer.index_source(
        context_id=context_id,
        source_metadata=metadata,
        text="ContextTrace indexing test",
        document_id=document_id,
    )

    assert source_id is not None

    chunks = store.get_search_chunks(source_id)

    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["text"] == "ContextTrace indexing test"
    assert chunks[0]["semantic_data_id"] is not None

    embedding = store.get_semantic_embedding(chunks[0]["id"])

    assert embedding is not None
    assert embedding["model_name"] == "test-embedding-model"
    assert embedding["dimension"] == 384
    assert len(embedding["vector"]) == 384


def test_index_empty_text_returns_none(tmp_path):
    (
        _store,
        indexer,
        context_id,
        document_id,
        metadata,
    ) = create_indexing_fixture(tmp_path)

    result = indexer.index_source(
        context_id=context_id,
        source_metadata=metadata,
        text="   ",
        document_id=document_id,
    )

    assert result is None


def test_index_sensitive_text_is_rejected(tmp_path):
    (
        _store,
        indexer,
        context_id,
        document_id,
        metadata,
    ) = create_indexing_fixture(tmp_path)

    with pytest.raises(ValueError):
        indexer.index_source(
            context_id=context_id,
            source_metadata=metadata,
            text="Contact test@example.com",
            document_id=document_id,
        )
