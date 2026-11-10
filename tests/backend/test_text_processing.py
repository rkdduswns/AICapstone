"""Tests for backend search text normalization."""

import pytest

from backend.text_processing import (
    merge_short_chunks,
    normalize_text,
    split_text_into_chunks,
)


def test_normalize_text_unifies_line_endings():
    """Windows and legacy line endings are converted to LF."""
    assert normalize_text("first\r\nsecond\rthird") == "first\nsecond\nthird"


def test_normalize_text_removes_null_characters():
    """NUL characters introduced by extraction are removed."""
    assert normalize_text("first\x00second") == "firstsecond"


def test_normalize_text_uses_unicode_nfc():
    """Canonically equivalent Unicode text uses NFC composition."""
    decomposed = "e\u0301"
    assert normalize_text(decomposed) == "\u00e9"


def test_normalize_text_preserves_internal_spacing_and_lines():
    """Meaningful internal spaces, blank lines, and tabs are preserved."""
    text = "  title  \r\n\r\n  first\tline  \n second "
    assert normalize_text(text) == "title  \n\n  first\tline  \n second"


@pytest.mark.parametrize("text", ["", "   ", "\r\n\t"])
def test_normalize_text_returns_empty_for_whitespace_only(text):
    """Whitespace-only input becomes an empty string."""
    assert normalize_text(text) == ""


def test_normalize_text_rejects_non_string_input():
    """The processing boundary rejects values that are not text."""
    with pytest.raises(TypeError, match="text must be a string"):
        normalize_text(None)


def test_split_text_into_chunks_splits_long_text():
    """Long text is divided into chunks within the maximum size."""
    text = "a" * 4500

    chunks = split_text_into_chunks(
        text,
        max_chunk_size=2000,
        overlap=200,
    )

    assert len(chunks) > 1
    assert all(len(chunk) <= 2000 for chunk in chunks)


def test_split_text_into_chunks_returns_empty_for_empty_text():
    assert split_text_into_chunks("   ") == []


def test_split_text_into_chunks_preserves_all_text():
    text = "a" * 4500

    chunks = split_text_into_chunks(
        text,
        max_chunk_size=2000,
        overlap=200,
    )

    assert "".join(
        [chunks[0]] + [chunk[200:] for chunk in chunks[1:]]
    ) == text


def test_split_text_into_chunks_keeps_short_text():
    """Short meaningful text is not discarded."""
    text = "This is a short document."

    chunks = split_text_into_chunks(text)

    assert chunks == [text]

def test_split_text_into_chunks_prefers_sentence_boundaries():
    """Text is preferably split at sentence boundaries."""
    text = ("First sentence. " * 100) + ("Second sentence. " * 100)

    chunks = split_text_into_chunks(
        text,
        max_chunk_size=2000,
        overlap=200,
    )

    assert len(chunks) >= 2
    assert all(len(chunk) <= 2000 for chunk in chunks)

def test_split_text_into_chunks_uses_sentence_boundaries():
    """Sentence endings are preferred when splitting long text."""
    text = "First sentence. " * 150

    chunks = split_text_into_chunks(
        text,
        max_chunk_size=2000,
        overlap=200,
    )

    assert len(chunks) > 1
    assert all(len(chunk) <= 2000 for chunk in chunks)
    assert chunks[0].endswith(".")

def test_merge_short_chunks_merges_with_previous_chunk():
    chunks = ["A" * 150, "short"]

    result = merge_short_chunks(chunks)

    assert len(result) == 1
    assert result[0] == "A" * 150 + "short"


def test_merge_short_chunks_merges_with_next_chunk():
    chunks = ["short", "B" * 150]

    result = merge_short_chunks(chunks)

    assert len(result) == 1
    assert result[0] == "short" + "B" * 150


def test_merge_short_chunks_preserves_unmergeable_short_chunk():
    chunks = ["A" * 2000, "short"]

    result = merge_short_chunks(chunks)

    assert result == chunks


def test_merge_short_chunks_removes_existing_overlap():
    chunks = ["A" * 150, "A" * 50 + "B" * 100]

    result = merge_short_chunks(chunks)

    assert result == ["A" * 150 + "B" * 100]


def test_merge_short_chunks_preserves_short_document():
    chunks = ["This is a short document."]

    result = merge_short_chunks(chunks)

    assert result == chunks


def test_merge_short_chunks_rejects_invalid_size():
    with pytest.raises(ValueError):
        merge_short_chunks(["hello"], min_chunk_size=200, max_chunk_size=100)