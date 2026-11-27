
"""Tests for document persistence in ActivityStore."""

import json
import sqlite3

import pytest

from backend.activity_store import ActivityStore
from backend.search_processor import create_document_chunks
from shared.activity import ActiveWindow
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.search_data import DocumentChunk, SourceMetadata


@pytest.fixture
def store(tmp_path):
    """Create an isolated SQLite database for each test."""
    return ActivityStore(tmp_path / "test_activity.db")


def test_save_and_get_document_record(store, tmp_path):
    """Saved document metadata and extracted text can be retrieved."""
    file_path = tmp_path / "sample.pdf"
    extracted_text = "강써치 document extraction test"
    captured_at = "2026-10-16T10:00:00"

    document_id = store.save_document_record(
        file_path=file_path,
        extracted_text=extracted_text,
        captured_at=captured_at,
    )

    records = store.get_recent_document_records()

    assert len(records) == 1

    record = records[0]
    assert record.id == document_id
    assert record.file_path == str(file_path)
    assert record.file_name == "sample.pdf"
    assert record.file_type == ".pdf"
    assert record.extracted_text == extracted_text
    assert record.captured_at == captured_at


def test_recent_documents_are_ordered_newest_first(store, tmp_path):
    """Documents are returned newest first."""
    first_id = store.save_document_record(
        tmp_path / "first.docx",
        "First document",
        "2026-10-15T10:00:00",
    )
    second_id = store.save_document_record(
        tmp_path / "second.pdf",
        "Second document",
        "2026-10-16T10:00:00",
    )

    records = store.get_recent_document_records()

    assert [record.id for record in records] == [second_id, first_id]
    assert [record.file_name for record in records] == [
        "second.pdf",
        "first.docx",
    ]


def test_recent_documents_respect_limit(store, tmp_path):
    """The requested record limit is respected."""
    for index in range(3):
        store.save_document_record(
            tmp_path / f"document-{index}.pdf",
            f"Document {index}",
            f"2026-10-{14 + index}T10:00:00",
        )

    records = store.get_recent_document_records(limit=2)

    assert len(records) == 2
    assert [record.file_name for record in records] == [
        "document-2.pdf",
        "document-1.pdf",
    ]


@pytest.mark.parametrize(
    "file_path, extracted_text, captured_at",
    [
        ("", "Some text", "2026-10-16T10:00:00"),
        ("sample.pdf", "", "2026-10-16T10:00:00"),
        ("sample.pdf", "Some text", ""),
    ],
)
def test_save_document_rejects_empty_required_fields(
    store, file_path, extracted_text, captured_at
):
    """Empty required fields are rejected."""
    with pytest.raises(ValueError):
        store.save_document_record(
            file_path=file_path,
            extracted_text=extracted_text,
            captured_at=captured_at,
        )


@pytest.mark.parametrize("limit", [0, -1, 201])
def test_get_recent_documents_rejects_invalid_limit(store, limit):
    """The document query limit must be between 1 and 200."""
    with pytest.raises(ValueError):
        store.get_recent_document_records(limit=limit)


def test_get_recent_documents_returns_empty_list(store):
    """An empty document table returns an empty list."""
    assert store.get_recent_document_records() == []


def test_get_record_returns_existing_activity(store):
    """An existing activity record can be retrieved by ID."""
    window = ActiveWindow(
        application="Visual Studio Code",
        process_name="Code.exe",
        process_id=1234,
        window_title="test.py - ContextTrace",
    )

    record_id = store.save_record(
        window=window,
        started_at="2026-10-16T10:00:00+00:00",
        ended_at="2026-10-16T10:05:00+00:00",
        active_duration_ms=300000,
    )

    record = store.get_record(record_id)

    assert record is not None
    assert record.id == record_id
    assert record.application == "Visual Studio Code"
    assert record.process_name == "Code.exe"
    assert record.process_id == 1234
    assert record.window_title == "test.py - ContextTrace"
    assert record.started_at == "2026-10-16T10:00:00+00:00"
    assert record.ended_at == "2026-10-16T10:05:00+00:00"
    assert record.active_duration_ms == 300000


def test_get_record_returns_none_for_missing_id(store):
    """A missing activity record returns None."""
    assert store.get_record(999) is None


@pytest.mark.parametrize("record_id", [0, -1])
def test_get_record_rejects_non_positive_id(store, record_id):
    """Activity record IDs must be positive."""
    with pytest.raises(ValueError):
        store.get_record(record_id)


@pytest.mark.parametrize("record_id", ["1", 1.5, True, None])
def test_get_record_rejects_non_integer_id(store, record_id):
    """Activity record IDs must be integers, not booleans."""
    with pytest.raises(TypeError):
        store.get_record(record_id)


def create_activity_record(store):
    """Create an activity record for search source tests."""
    window = ActiveWindow(
        application="Visual Studio Code",
        process_name="Code.exe",
        process_id=1234,
        window_title="test.py - ContextTrace",
    )

    return store.save_record(
        window=window,
        started_at="2026-10-16T10:00:00+00:00",
        ended_at="2026-10-16T10:05:00+00:00",
        active_duration_ms=300000,
    )


def create_document_metadata(file_path, captured_at):
    """Create document source metadata."""
    return SourceMetadata(
        kind="document",
        application="Visual Studio Code",
        process_name="Code.exe",
        window_title="test.py - ContextTrace",
        started_at="2026-10-16T10:00:00+00:00",
        last_active_at="2026-10-16T10:05:00+00:00",
        captured_at=captured_at,
        content_truncated=False,
        document=LocalDocument(
            file_path=str(file_path),
            file_type="pdf",
        ),
    )

def create_search_chunk(store, tmp_path, chunk_id="embedding-test-chunk"):
    """Create a document search chunk for embedding tests."""
    context_id = create_activity_record(store)
    file_path = tmp_path / "embedding-test.pdf"
    captured_at = "2026-11-10T10:00:00"

    document_id = store.save_document_record(
        file_path=file_path,
        extracted_text="Embedding test document",
        captured_at=captured_at,
        context_id=context_id,
    )

    metadata = create_document_metadata(file_path, captured_at)

    chunk = DocumentChunk(
        id=chunk_id,
        context_id=str(context_id),
        chunk_index=0,
        text="Embedding test document",
        source=metadata,
    )

    store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=[chunk],
        document_id=document_id,
    )

    return chunk_id, document_id

def test_save_search_source_from_models_for_document(store, tmp_path):
    """Document search source and chunks can be saved and retrieved."""
    context_id = create_activity_record(store)

    file_path = tmp_path / "sample.pdf"
    captured_at = "2026-10-16T10:10:00"

    document_id = store.save_document_record(
        file_path=file_path,
        extracted_text="ContextTrace document content",
        captured_at=captured_at,
        context_id=context_id,
    )

    metadata = create_document_metadata(file_path, captured_at)

    chunks = [
        DocumentChunk(
            id="document-chunk-1",
            context_id=str(context_id),
            chunk_index=0,
            text="First document chunk",
            source=metadata,
        ),
        DocumentChunk(
            id="document-chunk-2",
            context_id=str(context_id),
            chunk_index=1,
            text="Second document chunk",
            source=metadata,
            semantic_data_id="semantic-1",
        ),
    ]

    search_source_id = store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=chunks,
        document_id=document_id,
    )

    saved_chunks = store.get_search_chunks(search_source_id)

    assert len(saved_chunks) == 2
    assert saved_chunks[0]["id"] == "document-chunk-1"
    assert saved_chunks[0]["chunk_index"] == 0
    assert saved_chunks[0]["text"] == "First document chunk"
    assert saved_chunks[1]["id"] == "document-chunk-2"
    assert saved_chunks[1]["semantic_data_id"] == "semantic-1"


def test_generated_document_chunks_are_saved_with_original_source(
    store, tmp_path
):
    """Generated document chunks retain their original file metadata."""
    context_id = create_activity_record(store)
    file_path = tmp_path / "generated.pdf"
    captured_at = "2026-11-10T10:00:00"

    document_id = store.save_document_record(
        file_path=file_path,
        extracted_text="Document content",
        captured_at=captured_at,
        context_id=context_id,
    )

    metadata = create_document_metadata(file_path, captured_at)
    text = "".join(chr(0x4E00 + i) for i in range(100))

    chunks = create_document_chunks(
        text,
        context_id=context_id,
        source_metadata=metadata,
        max_chunk_length=40,
    )

    source_id = store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=chunks,
        document_id=document_id,
    )

    saved_chunks = store.get_search_chunks(source_id)

    assert [len(chunk["text"]) for chunk in saved_chunks] == [40, 40, 20]
    assert [chunk["chunk_index"] for chunk in saved_chunks] == [0, 1, 2]

    with store._connect() as connection:
        source = connection.execute(
            """
            SELECT document_id, context_id, metadata_json
            FROM search_sources
            WHERE id = ?
            """,
            (source_id,),
        ).fetchone()

    assert source["document_id"] == document_id
    assert source["context_id"] == context_id

    metadata_json = json.loads(source["metadata_json"])
    assert metadata_json["document"]["file_path"] == str(file_path)


def test_generated_web_chunks_are_saved_with_original_source(store):
    """Generated web chunks retain their original URL metadata."""
    context_id = create_activity_record(store)
    captured_at = "2026-11-10T10:00:00"
    url = "https://example.com/article"
    page_title = "Example Article"

    browser_source_id = store.save_browser_source_record(
        browser="chrome",
        url=url,
        page_title=page_title,
        captured_at=captured_at,
    )

    metadata = SourceMetadata(
        kind="web",
        application="Google Chrome",
        process_name="chrome.exe",
        window_title=page_title,
        started_at=captured_at,
        last_active_at=captured_at,
        captured_at=captured_at,
        content_truncated=False,
        browser=BrowserPage(
            browser="chrome",
            page_title=page_title,
            url=url,
        ),
    )

    text = "".join(chr(0x4E00 + i) for i in range(100))

    chunks = create_document_chunks(
        text,
        context_id=context_id,
        source_metadata=metadata,
        max_chunk_length=40,
    )

    source_id = store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=chunks,
        browser_source_id=browser_source_id,
    )

    saved_chunks = store.get_search_chunks(source_id)

    assert [len(chunk["text"]) for chunk in saved_chunks] == [40, 40, 20]

    with store._connect() as connection:
        source = connection.execute(
            """
            SELECT browser_source_id, context_id, metadata_json
            FROM search_sources
            WHERE id = ?
            """,
            (source_id,),
        ).fetchone()

    assert source["browser_source_id"] == browser_source_id
    assert source["context_id"] == context_id

    metadata_json = json.loads(source["metadata_json"])
    assert metadata_json["browser"]["url"] == url


def test_save_search_source_from_models_for_web(store):
    """Web search source and chunks can be saved and retrieved."""
    context_id = create_activity_record(store)

    captured_at = "2026-10-16T10:10:00"
    url = "https://www.google.com/"
    page_title = "Google"

    browser_source_id = store.save_browser_source_record(
        browser="chrome",
        url=url,
        page_title=page_title,
        captured_at=captured_at,
    )

    metadata = SourceMetadata(
        kind="web",
        application="Google Chrome",
        process_name="chrome.exe",
        window_title="Google - Google Chrome",
        started_at="2026-10-16T10:00:00+00:00",
        last_active_at="2026-10-16T10:05:00+00:00",
        captured_at=captured_at,
        content_truncated=False,
        browser=BrowserPage(
            browser="chrome",
            page_title=page_title,
            url=url,
        ),
    )

    chunks = [
        DocumentChunk(
            id="web-chunk-1",
            context_id=str(context_id),
            chunk_index=0,
            text="Google search page content",
            source=metadata,
        ),
    ]

    search_source_id = store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=chunks,
        browser_source_id=browser_source_id,
    )

    saved_chunks = store.get_search_chunks(search_source_id)

    assert len(saved_chunks) == 1
    assert saved_chunks[0]["id"] == "web-chunk-1"
    assert saved_chunks[0]["text"] == "Google search page content"


def test_save_search_source_from_models_replaces_existing_chunks(
    store, tmp_path
):
    """Saving the same source again replaces its previous chunks."""
    context_id = create_activity_record(store)

    file_path = tmp_path / "sample.pdf"
    document_id = store.save_document_record(
        file_path=file_path,
        extracted_text="Original document",
        captured_at="2026-10-16T10:00:00",
        context_id=context_id,
    )

    first_metadata = create_document_metadata(
        file_path,
        "2026-10-16T10:00:00",
    )

    first_chunks = [
        DocumentChunk(
            id="old-chunk",
            context_id=str(context_id),
            chunk_index=0,
            text="Old content",
            source=first_metadata,
        ),
    ]

    first_source_id = store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=first_metadata,
        chunks=first_chunks,
        document_id=document_id,
    )

    second_metadata = create_document_metadata(
        file_path,
        "2026-10-16T11:00:00",
    )

    second_chunks = [
        DocumentChunk(
            id="new-chunk-1",
            context_id=str(context_id),
            chunk_index=0,
            text="Updated content 1",
            source=second_metadata,
        ),
        DocumentChunk(
            id="new-chunk-2",
            context_id=str(context_id),
            chunk_index=1,
            text="Updated content 2",
            source=second_metadata,
        ),
    ]

    second_source_id = store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=second_metadata,
        chunks=second_chunks,
        document_id=document_id,
    )

    saved_chunks = store.get_search_chunks(second_source_id)

    assert first_source_id == second_source_id
    assert len(saved_chunks) == 2
    assert [chunk["id"] for chunk in saved_chunks] == [
        "new-chunk-1",
        "new-chunk-2",
    ]
    assert all(chunk["id"] != "old-chunk" for chunk in saved_chunks)


def test_save_search_source_rejects_document_from_different_context(
    store, tmp_path
):
    """A document belonging to another activity cannot be linked."""
    first_context_id = create_activity_record(store)
    second_context_id = create_activity_record(store)

    document_id = store.save_document_record(
        file_path=tmp_path / "sample.pdf",
        extracted_text="Document content",
        captured_at="2026-10-16T10:00:00",
        context_id=first_context_id,
    )

    metadata = create_document_metadata(
        tmp_path / "sample.pdf",
        "2026-10-16T10:00:00",
    )

    chunks = [
        DocumentChunk(
            id="invalid-context-chunk",
            context_id=str(second_context_id),
            chunk_index=0,
            text="Document content",
            source=metadata,
        ),
    ]

    with pytest.raises(ValueError):
        store.save_search_source_from_models(
            context_id=second_context_id,
            source_metadata=metadata,
            chunks=chunks,
            document_id=document_id,
        )


def test_get_search_chunks_rejects_invalid_id(store):
    """Search source IDs must be positive integers."""
    with pytest.raises(ValueError):
        store.get_search_chunks(0)

    with pytest.raises(ValueError):
        store.get_search_chunks(-1)


def test_save_search_source_from_models_rolls_back_on_chunk_insert_failure(
    store,
):
    """A failed chunk insert rolls back the source replacement."""
    activity_id = create_activity_record(store)

    first_path = "C:/documents/first.pdf"
    second_path = "C:/documents/second.pdf"

    first_document_id = store.save_document_record(
        file_path=first_path,
        extracted_text="First document content",
        captured_at="2026-10-16T10:05:00+00:00",
        context_id=activity_id,
    )
    second_document_id = store.save_document_record(
        file_path=second_path,
        extracted_text="Second document content",
        captured_at="2026-10-16T10:06:00+00:00",
        context_id=activity_id,
    )

    first_metadata = create_document_metadata(
        first_path,
        "2026-10-16T10:05:00+00:00",
    )
    second_metadata = create_document_metadata(
        second_path,
        "2026-10-16T10:06:00+00:00",
    )

    duplicate_chunk_id = "duplicate-chunk-id"

    first_chunk = DocumentChunk(
        id=duplicate_chunk_id,
        context_id=str(activity_id),
        chunk_index=0,
        text="First document chunk",
        source=first_metadata,
    )

    first_source_id = store.save_search_source_from_models(
        context_id=activity_id,
        source_metadata=first_metadata,
        chunks=[first_chunk],
        document_id=first_document_id,
    )

    second_chunk = DocumentChunk(
        id=duplicate_chunk_id,
        context_id=str(activity_id),
        chunk_index=0,
        text="Second document chunk",
        source=second_metadata,
    )

    with pytest.raises(sqlite3.IntegrityError):
        store.save_search_source_from_models(
            context_id=activity_id,
            source_metadata=second_metadata,
            chunks=[second_chunk],
            document_id=second_document_id,
        )

    connection = store._connect()
    try:
        failed_source = connection.execute(
            """
            SELECT id
            FROM search_sources
            WHERE document_id = ?
            """,
            (second_document_id,),
        ).fetchone()
    finally:
        connection.close()

    assert failed_source is None
    assert store.get_search_chunks(first_source_id)[0]["id"] == (
        duplicate_chunk_id
    )


def get_search_record_counts(store):
    """Return the number of persisted search sources and chunks."""
    connection = store._connect()
    try:
        source_count = connection.execute(
            "SELECT COUNT(*) FROM search_sources"
        ).fetchone()[0]
        chunk_count = connection.execute(
            "SELECT COUNT(*) FROM search_chunks"
        ).fetchone()[0]
    finally:
        connection.close()

    return source_count, chunk_count


def test_deleting_document_cascades_to_search_data(store, tmp_path):
    """Deleting a document also deletes its search source and chunks."""
    context_id = create_activity_record(store)
    file_path = tmp_path / "delete-test.pdf"
    captured_at = "2026-11-10T10:00:00"

    document_id = store.save_document_record(
        file_path=file_path,
        extracted_text="Document content for deletion test",
        captured_at=captured_at,
        context_id=context_id,
    )

    metadata = create_document_metadata(file_path, captured_at)
    chunks = [
        DocumentChunk(
            id="delete-document-chunk",
            context_id=str(context_id),
            chunk_index=0,
            text="Document content for deletion test",
            source=metadata,
        )
    ]

    store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=chunks,
        document_id=document_id,
    )

    assert get_search_record_counts(store) == (1, 1)
    store.save_semantic_embedding(
    "delete-document-chunk",
    [0.01] * 384,
    )

    assert store.get_semantic_embedding("delete-document-chunk") is not None
    store.delete_document_record(document_id)
    assert get_search_record_counts(store) == (0, 0)
    assert store.get_semantic_embedding("delete-document-chunk") is None

    connection = store._connect()
    try:
        connection.execute(
            "DELETE FROM document_records WHERE id = ?",
            (document_id,),
        )
        connection.commit()
    finally:
        connection.close()

    assert get_search_record_counts(store) == (0, 0)


def test_deleting_browser_source_cascades_to_search_data(store):
    """Deleting a browser source also deletes its search source and chunks."""
    context_id = create_activity_record(store)
    captured_at = "2026-11-10T10:00:00"
    url = "https://example.com/delete-test"
    page_title = "Deletion Test"

    browser_source_id = store.save_browser_source_record(
        browser="chrome",
        url=url,
        page_title=page_title,
        captured_at=captured_at,
    )

    metadata = SourceMetadata(
        kind="web",
        application="Google Chrome",
        process_name="chrome.exe",
        window_title=page_title,
        started_at=captured_at,
        last_active_at=captured_at,
        captured_at=captured_at,
        content_truncated=False,
        browser=BrowserPage(
            browser="chrome",
            page_title=page_title,
            url=url,
        ),
    )

    chunks = [
        DocumentChunk(
            id="delete-web-chunk",
            context_id=str(context_id),
            chunk_index=0,
            text="Web content for deletion test",
            source=metadata,
        )
    ]

    store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=chunks,
        browser_source_id=browser_source_id,
    )

    assert get_search_record_counts(store) == (1, 1)

    connection = store._connect()
    try:
        connection.execute(
            "DELETE FROM browser_source_records WHERE id = ?",
            (browser_source_id,),
        )
        connection.commit()
    finally:
        connection.close()

    assert get_search_record_counts(store) == (0, 0)


def test_deleting_activity_cascades_to_search_data(store, tmp_path):
    """Deleting an activity also deletes its linked search data."""
    context_id = create_activity_record(store)
    file_path = tmp_path / "activity-delete-test.pdf"
    captured_at = "2026-11-10T10:00:00"

    document_id = store.save_document_record(
        file_path=file_path,
        extracted_text="Activity deletion test",
        captured_at=captured_at,
        context_id=context_id,
    )

    metadata = create_document_metadata(file_path, captured_at)
    chunks = [
        DocumentChunk(
            id="activity-delete-chunk",
            context_id=str(context_id),
            chunk_index=0,
            text="Activity deletion test",
            source=metadata,
        )
    ]

    store.save_search_source_from_models(
        context_id=context_id,
        source_metadata=metadata,
        chunks=chunks,
        document_id=document_id,
    )

    assert get_search_record_counts(store) == (1, 1)

    connection = store._connect()
    try:
        connection.execute(
            "DELETE FROM activity_records WHERE id = ?",
            (context_id,),
        )
        connection.commit()
    finally:
        connection.close()

    assert get_search_record_counts(store) == (0, 0)

def test_save_and_get_semantic_embedding(store, tmp_path):
    """An embedding vector can be saved and retrieved."""
    chunk_id, _ = create_search_chunk(store, tmp_path)
    vector = [0.01] * 384

    semantic_data_id = store.save_semantic_embedding(
        chunk_id,
        vector,
    )

    result = store.get_semantic_embedding(chunk_id)

    assert result is not None
    assert result["semantic_data_id"] == semantic_data_id
    assert result["chunk_id"] == chunk_id
    assert result["model_name"] == "intfloat/multilingual-e5-small"
    assert result["dimension"] == 384
    assert result["vector"] == vector


def test_save_semantic_embedding_updates_existing_vector(store, tmp_path):
    """Saving another vector updates the existing embedding."""
    chunk_id, _ = create_search_chunk(store, tmp_path)

    first_id = store.save_semantic_embedding(
        chunk_id,
        [0.01] * 384,
    )

    second_id = store.save_semantic_embedding(
        chunk_id,
        [0.02] * 384,
    )

    result = store.get_semantic_embedding(chunk_id)

    assert first_id == second_id
    assert result["vector"] == [0.02] * 384


def test_save_semantic_embedding_rejects_missing_chunk(store):
    """An embedding cannot reference a missing chunk."""
    with pytest.raises(ValueError, match="search chunk does not exist"):
        store.save_semantic_embedding(
            "missing-chunk",
            [0.01] * 384,
        )


@pytest.mark.parametrize(
    "vector",
    [
        [0.01] * 383,
        [float("nan")] * 384,
        [float("inf")] * 384,
        ["invalid"] * 384,
    ],
)
def test_save_semantic_embedding_rejects_invalid_vector(
    store, tmp_path, vector
):
    """Invalid embedding vectors are rejected."""
    chunk_id, _ = create_search_chunk(store, tmp_path)

    with pytest.raises((ValueError, TypeError)):
        store.save_semantic_embedding(chunk_id, vector)


def test_deleting_document_cascades_to_semantic_embedding(
    store, tmp_path
):
    """Deleting the original document also deletes its embedding."""
    chunk_id, document_id = create_search_chunk(store, tmp_path)

    store.save_semantic_embedding(
        chunk_id,
        [0.01] * 384,
    )

    connection = store._connect()

    try:
        connection.execute(
            "DELETE FROM document_records WHERE id = ?",
            (document_id,),
        )
        connection.commit()

        count = connection.execute(
            "SELECT COUNT(*) FROM semantic_embeddings"
        ).fetchone()[0]
    finally:
        connection.close()

    assert count == 0
    assert store.get_semantic_embedding(chunk_id) is None

def _save_timed_activity(store, started_at, ended_at, title="test.py"):
    """Save a small activity record with explicit UTC timestamps."""
    window = ActiveWindow(
        application="Visual Studio Code",
        process_name="Code.exe",
        process_id=1234,
        window_title=title,
    )
    return store.save_record(
        window=window,
        started_at=started_at,
        ended_at=ended_at,
        active_duration_ms=60_000,
    )


def _get_activity_session_id(store, record_id):
    connection = store._connect()
    try:
        row = connection.execute(
            "SELECT session_id FROM activity_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        return row["session_id"]
    finally:
        connection.close()


def test_activity_records_within_inactivity_gap_share_session(store):
    """Window changes within the inactivity threshold stay in one session."""
    first_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
        "first.py",
    )
    second_id = _save_timed_activity(
        store,
        "2026-11-19T09:20:00+00:00",
        "2026-11-19T09:25:00+00:00",
        "second.py",
    )

    first_session_id = _get_activity_session_id(store, first_id)
    second_session_id = _get_activity_session_id(store, second_id)

    assert first_session_id == second_session_id
    assert store.get_session(first_session_id) == {
        "id": first_session_id,
        "started_at": "2026-11-19T09:00:00+00:00",
        "ended_at": "2026-11-19T09:25:00+00:00",
        "activity_count": 2,
    }


def test_activity_after_inactivity_gap_starts_new_session(store):
    """An inactivity gap greater than 30 minutes starts a new session."""
    first_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
    )
    second_id = _save_timed_activity(
        store,
        "2026-11-19T09:36:00+00:00",
        "2026-11-19T09:40:00+00:00",
    )

    assert _get_activity_session_id(store, first_id) != _get_activity_session_id(
        store, second_id
    )
    assert len(store.get_recent_sessions()) == 2


def test_activity_at_exact_inactivity_threshold_stays_in_session(store):
    """A gap equal to the configured threshold remains in the same session."""
    first_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
    )
    second_id = _save_timed_activity(
        store,
        "2026-11-19T09:35:00+00:00",
        "2026-11-19T09:40:00+00:00",
    )

    assert _get_activity_session_id(store, first_id) == _get_activity_session_id(
        store, second_id
    )


def test_recent_sessions_and_session_records(store):
    """Session summaries and their activity records can be queried."""
    first_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
        "first.py",
    )
    second_id = _save_timed_activity(
        store,
        "2026-11-19T09:10:00+00:00",
        "2026-11-19T09:15:00+00:00",
        "second.py",
    )
    session_id = _get_activity_session_id(store, first_id)

    sessions = store.get_recent_sessions()
    records = store.get_session_records(session_id)

    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    assert sessions[0]["activity_count"] == 2
    assert [record.id for record in records] == [first_id, second_id]
    assert store.get_session(999) is None


def test_session_query_validates_ids_and_limits(store):
    with pytest.raises(TypeError):
        store.get_session(True)
    with pytest.raises(ValueError):
        store.get_session(0)
    with pytest.raises(TypeError):
        store.get_session_records(1, limit=True)
    with pytest.raises(ValueError):
        store.get_recent_sessions(limit=201)
    with pytest.raises(ValueError):
        store.get_session_records(1, offset=-1)


def test_initialize_migrates_legacy_activity_records_into_sessions(tmp_path):
    """Existing activity rows are retained and grouped during migration."""
    db_path = tmp_path / "legacy_activity.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE activity_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application TEXT NOT NULL,
                process_name TEXT NOT NULL,
                process_id INTEGER NOT NULL,
                window_title TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                active_duration_ms INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO activity_records (
                application, process_name, process_id, window_title,
                started_at, ended_at, active_duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "Visual Studio Code", "Code.exe", 1234, "one.py",
                    "2026-11-19T09:00:00+00:00",
                    "2026-11-19T09:05:00+00:00", 300_000,
                ),
                (
                    "Visual Studio Code", "Code.exe", 1234, "two.py",
                    "2026-11-19T09:10:00+00:00",
                    "2026-11-19T09:15:00+00:00", 300_000,
                ),
                (
                    "Visual Studio Code", "Code.exe", 1234, "three.py",
                    "2026-11-19T10:00:00+00:00",
                    "2026-11-19T10:05:00+00:00", 300_000,
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    store = ActivityStore(db_path)
    connection = store._connect()
    try:
        rows = connection.execute(
            "SELECT id, session_id FROM activity_records ORDER BY id"
        ).fetchall()
        activity_count = connection.execute(
            "SELECT COUNT(*) FROM activity_records"
        ).fetchone()[0]
    finally:
        connection.close()

    assert activity_count == 3
    assert rows[0]["session_id"] == rows[1]["session_id"]
    assert rows[2]["session_id"] != rows[0]["session_id"]
    assert len(store.get_recent_sessions()) == 2


def test_invalid_legacy_timestamps_are_preserved_in_isolated_sessions(store):
    """Malformed timestamps do not block activity persistence or migration."""
    first_id = _save_timed_activity(store, "not-a-time", "also-not-a-time")
    second_id = _save_timed_activity(store, "not-a-time-2", "also-not-a-time-2")

    assert _get_activity_session_id(store, first_id) != _get_activity_session_id(
        store, second_id
    )
    assert len(store.get_recent_sessions()) == 2


def test_out_of_order_record_bridges_and_merges_sessions(store):
    """A later flush can bridge nearby sessions without insertion-order bugs."""
    first_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
        "first.py",
    )
    last_id = _save_timed_activity(
        store,
        "2026-11-19T10:00:00+00:00",
        "2026-11-19T10:05:00+00:00",
        "last.py",
    )
    middle_id = _save_timed_activity(
        store,
        "2026-11-19T09:30:00+00:00",
        "2026-11-19T09:35:00+00:00",
        "middle.py",
    )

    session_ids = {
        _get_activity_session_id(store, item_id)
        for item_id in (first_id, last_id, middle_id)
    }
    assert len(session_ids) == 1
    session = store.get_session(session_ids.pop())
    assert session["started_at"] == "2026-11-19T09:00:00+00:00"
    assert session["ended_at"] == "2026-11-19T10:05:00+00:00"
    assert session["activity_count"] == 3


def test_session_materials_include_only_explicitly_linked_web_and_documents(store, tmp_path):
    activity_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:30:00+00:00",
    )
    session_id = _get_activity_session_id(store, activity_id)
    document_id = store.save_document_record(
        tmp_path / "notes.pdf",
        "sample document text",
        "2026-11-19T09:10:00+00:00",
        context_id=activity_id,
    )
    browser_id = store.save_browser_source_record(
        "chrome",
        "https://example.com/page",
        "Example page",
        "2026-11-19T09:20:00+00:00",
        activity_record_id=activity_id,
    )
    store.save_browser_content_record(
        browser_id,
        "example page body",
        "2026-11-19T09:21:00+00:00",
    )
    store.save_browser_source_record(
        "edge",
        "https://outside.example/",
        "Outside session",
        "2026-11-19T11:00:00+00:00",
    )

    store.save_browser_source_record("chrome", "https://unlinked.example/",
                                     "동일 시각의 미연결 페이지", "2026-11-19T09:20:00+00:00")
    materials = store.get_session_materials(session_id)
    assert [item["id"] for item in materials["documents"]] == [document_id]
    assert [item["id"] for item in materials["web_pages"]] == [browser_id]
    assert materials["web_pages"][0]["has_content"] is True


def test_delete_activity_cascades_dependent_data_and_recalculates_session(store, tmp_path):
    first_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
        "first.py",
    )
    second_id = _save_timed_activity(
        store,
        "2026-11-19T09:10:00+00:00",
        "2026-11-19T09:15:00+00:00",
        "second.py",
    )
    session_id = _get_activity_session_id(store, first_id)
    first_record = store.get_record(first_id)
    store.save_clipboard_record(
        first_record.application,
        first_record.started_at,
        "2026-11-19T09:02:00+00:00",
        "clipboard data",
    )
    document_id = store.save_document_record(
        tmp_path / "linked.docx",
        "linked document text",
        "2026-11-19T09:03:00+00:00",
        context_id=first_id,
    )
    store.save_search_source_and_chunks(
        source_kind="document",
        captured_at="2026-11-19T09:03:00+00:00",
        chunks=["indexed document text"],
        document_id=document_id,
        context_id=first_id,
    )
    linked_browser_id = store.save_browser_source_record(
        "chrome",
        "https://example.com/linked",
        "Linked page",
        "2026-11-19T09:04:00+00:00",
    )
    store.save_browser_content_record(
        linked_browser_id,
        "linked page body",
        "2026-11-19T09:04:30+00:00",
    )
    store.save_search_source_and_chunks(
        source_kind="web",
        captured_at="2026-11-19T09:04:30+00:00",
        chunks=["indexed linked page body"],
        browser_source_id=linked_browser_id,
        context_id=first_id,
    )

    assert store.delete_activity_record(first_id) is True
    assert store.get_browser_source_record(linked_browser_id) is None
    assert store.delete_activity_record(first_id) is False
    assert store.get_session(session_id)["activity_count"] == 1
    assert store.get_session(session_id)["started_at"] == "2026-11-19T09:10:00+00:00"
    assert store.get_session_records(session_id)[0].id == second_id
    assert store.get_recent_document_records() == []
    assert store.get_recent_clipboard_records() == []

    connection = store._connect()
    try:
        assert connection.execute("SELECT COUNT(*) FROM search_sources").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM search_chunks").fetchone()[0] == 0
    finally:
        connection.close()


def test_delete_all_records_clears_every_data_table_and_keeps_schema(store):
    activity_id = _save_timed_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
    )
    store.save_clipboard_record(
        "Visual Studio Code",
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:02:00+00:00",
        "clipboard",
    )
    browser_id = store.save_browser_source_record(
        "chrome", "https://example.com", "Example", "2026-11-19T09:03:00+00:00"
    )
    store.save_browser_content_record(
        browser_id, "page content", "2026-11-19T09:04:00+00:00"
    )
    document_id = store.save_document_record(
        "test.pdf", "document content", "2026-11-19T09:04:00+00:00", context_id=activity_id
    )
    store.save_search_source_and_chunks(
        source_kind="document",
        captured_at="2026-11-19T09:04:00+00:00",
        chunks=["document chunk"],
        document_id=document_id,
        context_id=activity_id,
    )

    counts = store.delete_all_records()
    assert counts["activity_records"] == 1
    assert counts["browser_source_records"] == 1
    assert counts["document_records"] == 1

    connection = store._connect()
    try:
        for table in (
            "activity_records", "sessions", "clipboard_records",
            "browser_source_records", "browser_content_records",
            "document_records", "document_chunks", "search_sources",
            "search_chunks", "semantic_embeddings",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        connection.close()

    # Delete-all is data-only: tables remain usable for future collection.
    new_id = _save_timed_activity(
        store,
        "2026-11-19T11:00:00+00:00",
        "2026-11-19T11:05:00+00:00",
    )
    assert store.get_record(new_id) is not None
