"""인용 문장만 선택하고 원래 답변과 문자 위치를 보존하는지 확인한다."""

import pytest

from client.citation_highlights import citation_spans


@pytest.mark.parametrize(
    ("text", "number", "expected"),
    [
        ("웹 설명입니다. [1]\n\nPDF 설명입니다. [2]", 1, ["웹 설명입니다. [1]"]),
        ("웹 설명입니다. [1]\n\nPDF 설명입니다. [2]", 2, ["PDF 설명입니다. [2]"]),
        ("웹 설명입니다. [1] PDF 설명입니다. [2]", 1, ["웹 설명입니다. [1]"]),
        ("웹 설명입니다. [1] PDF 설명입니다. [2]", 2, ["PDF 설명입니다. [2]"]),
        ("출처 없는 문장입니다. 선택한 문장입니다. [1]", 1, ["선택한 문장입니다. [1]"]),
        ("출처 없는 문장입니다. “선택한 문장입니다.” [1]", 1, ["“선택한 문장입니다.” [1]"]),
        ("먼저 한 설명 [2] 이어지는 선택 설명 [1]", 1, ["이어지는 선택 설명 [1]"]),
        ("\t- 선택한 항목입니다. [1]\n- 다른 항목입니다. [2]", 1, ["- 선택한 항목입니다. [1]"]),
        ("첫 줄은 연결하지 않습니다.\r\n  선택한 줄 [1]", 1, ["선택한 줄 [1]"]),
        ("설명 다음 줄입니다.\n[1]", 1, ["[1]"]),
    ],
)
def test_highlights_only_the_sentence_with_the_selected_citation(text, number, expected):
    """같은 문단에서도 이전 문장·다른 인용·이전 줄을 강조 범위에서 제외한다."""
    spans = citation_spans(text, number, 2)
    assert [text[start:end] for start, end in spans] == expected


@pytest.mark.parametrize("marker", ["[1, 2]", "[1,2]", "[1][2]", "[1] [2]", "[1]\t[2]"])
def test_grouped_citations_connect_the_same_sentence_to_each_evidence(marker):
    """하나의 문장을 함께 뒷받침하는 근거는 같은 인용 묶음 범위를 사용한다."""
    text = f"같은 문장을 뒷받침합니다. {marker}"
    for number in (1, 2):
        assert citation_spans(text, number, 2) == [(0, len(text))]


def test_repeated_citation_highlights_each_sentence_without_changing_text():
    """여러 위치의 같은 번호를 모두 반환하며 원문·순서는 유지한다."""
    text = "첫 설명 [1]\n다른 설명 [2]\n마지막 설명 [1]"
    spans = citation_spans(text, 1, 2)
    assert [text[start:end] for start, end in spans] == ["첫 설명 [1]", "마지막 설명 [1]"]
    assert spans == sorted(spans)
    assert text == "첫 설명 [1]\n다른 설명 [2]\n마지막 설명 [1]"


def test_positions_use_python_codepoints_with_non_bmp_and_combining_characters():
    """이모지와 조합 문자가 있어도 반환 위치가 원래 Python 문자열을 정확히 자른다."""
    prefix = "🙂 첫 문장 [2] "
    selected = "가 문장 🧑‍💻 [1]"
    text = prefix + selected
    spans = citation_spans(text, 1, 2)
    assert spans == [(len(prefix), len(text))]
    assert text[spans[0][0]:spans[0][1]] == selected


@pytest.mark.parametrize("marker", ["[10]", "[01]", "[0]", "[-1]", "[1a]", "[[1]]", r"\[1]", "［1］", "[١]"])
def test_invalid_or_different_markers_do_not_match_selected_evidence(marker):
    """다른 번호와 비표준 표기를 실제 선택 근거의 인용으로 꾸미지 않는다."""
    assert citation_spans(f"가상 설명 {marker}", 1, 10) == []


@pytest.mark.parametrize(
    ("text", "number", "count"),
    [("", 1, 2), ("인용 없는 설명", 1, 2), ("설명 [1]", 0, 2),
     ("설명 [1]", 3, 2), ("설명 [1]", 1, 0), ("설명 [1]", True, 2),
     (None, 1, 2), ("설명 [1]", 1, None)],
)
def test_missing_input_or_invalid_selection_does_not_infer_a_connection(text, number, count):
    """비어 있거나 검증된 근거 범위를 벗어난 선택은 강조하지 않는다."""
    assert citation_spans(text, number, count) == []


def test_tenth_evidence_has_its_own_number_and_large_unknown_numbers_are_safe():
    """두 자리 번호와 긴 미지 번호가 있어도 부분 매칭이나 숫자 변환 오류를 만들지 않는다."""
    text = "다른 근거 [1] 선택한 근거 [10]"
    spans = citation_spans(text, 10, 10)
    assert [text[start:end] for start, end in spans] == ["선택한 근거 [10]"]
    assert citation_spans("설명 [" + "9" * 5000 + "]", 1, 10) == []
