
import pytest

from backend.search_processor import create_document_chunks, normalize_search_text
from shared.search_data import MAX_CHUNK_TEXT_LENGTH, SourceMetadata


def test_normalize_search_text_whitespace():
    text = "  First   line\t\n\n\n Second   line  "

    assert normalize_search_text(text) == "First line\n\nSecond line"


def test_normalize_search_text_line_endings():
    text = "First line\r\nSecond line\rThird line"

    assert normalize_search_text(text) == (
        "First line\nSecond line\nThird line"
    )


def test_normalize_search_text_unicode_nfc():
    text = "e\u0301"

    assert normalize_search_text(text) == "\u00e9"


def test_normalize_search_text_preserves_case_and_punctuation():
    text = "ContextTrace: PDF, DOCX, and Chrome!"

    assert normalize_search_text(text) == text


def test_normalize_search_text_rejects_sensitive_email():
    with pytest.raises(ValueError):
        normalize_search_text("Contact: test@example.com")


def test_normalize_search_text_rejects_sensitive_token():
    with pytest.raises(ValueError):
        normalize_search_text("api_key=sample-secret-value")


def test_normalize_search_text_rejects_non_string():
    with pytest.raises(TypeError):
        normalize_search_text(None)


def test_normalize_search_text_empty_input():
    assert normalize_search_text("") == ""
    assert normalize_search_text("   \n  ") == ""

def make_source_metadata():
    return SourceMetadata(
        kind="web",
        application="Chrome",
        process_name="chrome.exe",
        window_title="Test page",
        started_at="2026-11-10T10:00:00",
        last_active_at="2026-11-10T10:00:00",
        captured_at="2026-11-10T10:00:00",
        content_truncated=False,
        browser=None,
        document=None,
    )


def test_create_document_chunks_splits_long_text():
    metadata = make_source_metadata()
    text = "".join(chr(0x4E00 + i) for i in range(120))

    chunks = create_document_chunks(
        text,
        context_id=10,
        source_metadata=metadata,
        max_chunk_length=50,
    )

    assert [len(chunk.text) for chunk in chunks] == [50, 50, 20]
    assert all(chunk.context_id == "10" for chunk in chunks)
    assert all(chunk.source == metadata for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]


def test_create_document_chunks_removes_duplicate_chunks():
    metadata = make_source_metadata()

    chunks = create_document_chunks(
        "First paragraph\n\nFirst paragraph\n\nSecond paragraph",
        context_id=10,
        source_metadata=metadata,
    )

    assert [chunk.text for chunk in chunks] == [
        "First paragraph",
        "Second paragraph",
    ]


def test_create_document_chunks_preserves_short_text():
    metadata = make_source_metadata()

    chunks = create_document_chunks(
        "Short text",
        context_id=10,
        source_metadata=metadata,
    )

    assert len(chunks) == 1
    assert chunks[0].text == "Short text"


def test_create_document_chunks_empty_text():
    assert create_document_chunks(
        "   ",
        context_id=10,
        source_metadata=make_source_metadata(),
    ) == []


def test_create_document_chunks_rejects_invalid_max_length():
    with pytest.raises(ValueError):
        create_document_chunks(
            "Some text",
            context_id=10,
            source_metadata=make_source_metadata(),
            max_chunk_length=MAX_CHUNK_TEXT_LENGTH + 1,
        )