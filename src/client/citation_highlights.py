"""명시된 인용 번호만 사용해 선택한 근거의 답변 강조 범위를 계산한다."""

import re

# 이중 괄호·이스케이프·앞자리 0·Unicode 숫자는 표시용 인용 번호로 해석하지 않는다.
_CITATION = re.compile(r"(?<![\\\[])\[([1-9][0-9]*(?:[ \t]*,[ \t]*[1-9][0-9]*)*)\](?!\])")
_SENTENCE_BREAK = re.compile(r'''[.!?。！？]["'”’」』)\]]*[ \t]+(?=\S)''')


def citation_spans(text: str, citation_number: int, evidence_count: int) -> list[tuple[int, int]]:
    """선택한 실제 인용의 직전 문장과 인용 묶음을 Python 문자 위치로 반환한다.

    `[1]`, `[1, 2]`, `[1] [2]`처럼 직접 적힌 번호만 연결한다. 같은 줄에서
    마지막 문장 경계 또는 앞선 인용 뒤부터 현재 묶음 끝까지를 강조한다.
    문장 경계는 마침표·물음표·느낌표 뒤 공백이며, 줄 경계는 넘지 않는다.
    본문을 고치거나 인용 없는 문장의 출처를 의미로 추측하지 않는다.
    Qt 커서에 사용할 때에는 반환한 Python 위치를 UTF-16 위치로 변환해야 한다.
    """
    if (not isinstance(text, str) or not text
            or type(citation_number) is not int or type(evidence_count) is not int
            or not 1 <= citation_number <= evidence_count):
        return []

    # 번호 문자열을 그대로 비교해 [1]을 [10]으로 잘못 매칭하지 않는다.
    # 답변에 매우 긴 숫자가 있어도 int 변환 제한 때문에 화면이 실패하지 않는다.
    selected = str(citation_number)
    clusters: list[tuple[int, int, set[str]]] = []
    for match in _CITATION.finditer(text):
        numbers = {number.strip() for number in match.group(1).split(",")}
        if clusters and not text[clusters[-1][1]:match.start()].strip(" \t"):
            start, _, previous_numbers = clusters[-1]
            clusters[-1] = (start, match.end(), previous_numbers | numbers)
        else:
            clusters.append((match.start(), match.end(), numbers))

    spans = []
    previous_end = 0
    for start, end, numbers in clusters:
        if selected in numbers:
            lower_bound = max(text.rfind("\n", 0, start) + 1, previous_end)
            preceding = text[lower_bound:start].rstrip()
            sentence_start = lower_bound
            for boundary in _SENTENCE_BREAK.finditer(preceding):
                sentence_start = lower_bound + boundary.end()
            while sentence_start < start and text[sentence_start].isspace():
                sentence_start += 1
            spans.append((sentence_start, end))
        # 다른 근거의 인용도 경계로 두어 이전 답변 부분까지 다시 강조하지 않는다.
        previous_end = end
    return spans
