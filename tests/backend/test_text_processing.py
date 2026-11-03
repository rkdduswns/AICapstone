"""Tests for backend search text normalization."""

import pytest

from backend.text_processing import normalize_text


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
    assert normalize_text(text) == "title\n\n  first\tline  \n second"


@pytest.mark.parametrize("text", ["", "   ", "\r\n\t"])
def test_normalize_text_returns_empty_for_whitespace_only(text):
    """Whitespace-only input becomes an empty string."""
    assert normalize_text(text) == ""


def test_normalize_text_rejects_non_string_input():
    """The processing boundary rejects values that are not text."""
    with pytest.raises(TypeError, match="text must be a string"):
        normalize_text(None)
