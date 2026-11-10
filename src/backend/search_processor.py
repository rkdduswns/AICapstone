
"""검색용 텍스트 정규화 기능."""

import re
import unicodedata
import uuid

from backend.privacy import PrivacyPolicy
from shared.search_data import (
    MAX_CHUNK_TEXT_LENGTH,
    DocumentChunk,
    SourceMetadata,
)


def normalize_search_text(
    text: str,
    privacy_policy: PrivacyPolicy | None = None,
) -> str:
    """개인정보를 먼저 검사한 뒤 검색에 사용할 텍스트를 정리한다.

    - Unicode 문자를 NFC 형식으로 통일한다.
    - Windows 및 Unix 줄바꿈을 LF로 통일한다.
    - 탭과 연속 공백을 하나의 공백으로 정리한다.
    - 불필요하게 반복되는 빈 줄을 최대 한 줄로 줄인다.
    - 문장의 대소문자와 문장부호는 변경하지 않는다.
    """
    if not isinstance(text, str):
        raise TypeError("Search text must be a string.")

    # 개인정보는 정규화나 분할보다 먼저 검사한다.
    policy = privacy_policy or PrivacyPolicy()
    if policy.contains_sensitive_data(text):
        raise ValueError("Search text contains potentially sensitive data.")

    normalized = unicodedata.normalize("NFC", text)

    # 운영체제별 줄바꿈과 특수 공백을 통일한다.
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u00a0", " ")

    # 줄 단위로 공백을 정리해 문단 구조는 보존한다.
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in normalized.split("\n")
    ]
    normalized = "\n".join(lines)

    # 연속된 빈 줄은 하나만 남긴다.
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    return normalized.strip()

def create_document_chunks(
    text: str,
    context_id: int,
    source_metadata: SourceMetadata,
    max_chunk_length: int = MAX_CHUNK_TEXT_LENGTH,
) -> list[DocumentChunk]:
    """웹 또는 문서 텍스트를 검색 청크로 분할한다."""
    if isinstance(context_id, bool) or not isinstance(context_id, int):
        raise TypeError("context_id must be an integer")
    if context_id < 1:
        raise ValueError("context_id must be positive")

    if not isinstance(source_metadata, SourceMetadata):
        raise TypeError("source_metadata must be SourceMetadata")

    if (
        isinstance(max_chunk_length, bool)
        or not isinstance(max_chunk_length, int)
        or not 1 <= max_chunk_length <= MAX_CHUNK_TEXT_LENGTH
    ):
        raise ValueError("invalid max_chunk_length")

    normalized = normalize_search_text(text)
    if not normalized:
        return []

    # 문단을 우선 유지하고, 너무 긴 문단은 길이 제한에 맞춰 분할한다.
    paragraphs = normalized.split("\n\n")
    text_parts: list[str] = []

    for paragraph in paragraphs:
        if len(paragraph) <= max_chunk_length:
            text_parts.append(paragraph)
            continue

        for start in range(0, len(paragraph), max_chunk_length):
            part = paragraph[start : start + max_chunk_length].strip()
            if part:
                text_parts.append(part)

    # 여러 번 반복된 동일 청크는 한 번만 저장한다.
    unique_parts: list[str] = []
    seen_parts: set[str] = set()

    for part in text_parts:
        part = part.strip()
        if not part or part in seen_parts:
            continue

        seen_parts.add(part)
        unique_parts.append(part)

    return [
        DocumentChunk(
            id=str(uuid.uuid4()),
            context_id=str(context_id),
            chunk_index=index,
            text=part,
            source=source_metadata,
        )
        for index, part in enumerate(unique_parts)
    ]