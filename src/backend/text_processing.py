"""검색 색인에 사용할 원문 텍스트의 기본 정규화 기능을 제공한다."""

import unicodedata


def normalize_text(text: str) -> str:
    """원문 의미와 내부 공백을 보존하면서 기본적인 텍스트 형식을 정리한다.

    줄바꿈을 LF로 통일하고, Unicode 문자를 NFC로 정규화하며,
    추출 과정에서 섞일 수 있는 NUL 문자와 양끝의 불필요한 공백만 제거한다.
    문장이나 단락을 합치거나 내부 공백을 축약하지 않아 원문 구조를 최대한 보존한다.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\x00", "")
    normalized = unicodedata.normalize("NFC", normalized)
    return normalized.strip()
