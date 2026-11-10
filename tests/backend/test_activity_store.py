
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
    extracted_text = "ContextTrace document extraction test"
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