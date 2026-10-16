
"""Tests for document persistence in ActivityStore."""

import pytest

from backend.activity_store import ActivityStore


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