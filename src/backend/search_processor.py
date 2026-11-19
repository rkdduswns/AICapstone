
"""검색용 텍스트 정규화 및 청크 생성 기능."""

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
    """개인정보 검사 후 검색에 사용할 텍스트를 정규화한다.

    처리 순서:
    1. 입력 자료형 확인
    2. 개인정보 검사
    3. Unicode NFC 정규화
    4. 줄바꿈 및 특수 공백 통일
    5. 연속 공백과 불필요한 빈 줄 정리
    """
    if not isinstance(text, str):
        raise TypeError("Search text must be a string.")

    # 개인정보 검사는 정규화나 분할보다 먼저 수행한다.
    policy = privacy_policy or PrivacyPolicy()

    if policy.contains_sensitive_data(text):
        raise ValueError(
            "Search text contains potentially sensitive data."
        )

    normalized = unicodedata.normalize("NFC", text)

    # 운영체제별 줄바꿈을 LF로 통일한다.
    normalized = normalized.replace("\r\n", "\n")
    normalized = normalized.replace("\r", "\n")

    # 줄바꿈하지 않는 공백을 일반 공백으로 변경한다.
    normalized = normalized.replace("\u00a0", " ")

    # 줄 단위로 공백을 정리한다.
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in normalized.split("\n")
    ]

    normalized = "\n".join(lines)

    # 연속된 빈 줄은 최대 한 줄만 유지한다.
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    return normalized.strip()


def _split_long_paragraph(
    paragraph: str,
    max_chunk_length: int,
) -> list[str]:
    """길이가 제한을 초과하는 문단을 일정한 문자 수로 나눈다."""
    if len(paragraph) <= max_chunk_length:
        return [paragraph]

    parts: list[str] = []

    for start in range(0, len(paragraph), max_chunk_length):
        part = paragraph[
            start : start + max_chunk_length
        ].strip()

        if part:
            parts.append(part)

    return parts


def _split_paragraphs(
    text: str,
    max_chunk_length: int,
) -> list[str]:
    """문단 구조를 우선 유지하면서 긴 문단을 분할한다."""
    paragraphs = text.split("\n\n")
    parts: list[str] = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        parts.extend(
            _split_long_paragraph(
                paragraph,
                max_chunk_length,
            )
        )

    return parts


def _remove_duplicate_chunks(
    parts: list[str],
) -> list[str]:
    """동일한 텍스트를 가진 청크를 최초 한 개만 유지한다."""
    unique_parts: list[str] = []
    seen_parts: set[str] = set()

    for part in parts:
        normalized_part = part.strip()

        if not normalized_part:
            continue

        if normalized_part in seen_parts:
            continue

        seen_parts.add(normalized_part)
        unique_parts.append(normalized_part)

    return unique_parts


def create_document_chunks(
    text: str,
    context_id: int | None,
    source_metadata: SourceMetadata,
    max_chunk_length: int = MAX_CHUNK_TEXT_LENGTH,
    privacy_policy: PrivacyPolicy | None = None,
) -> list[DocumentChunk]:
    """웹 또는 로컬 문서의 텍스트를 검색 청크로 분할한다.

    웹과 문서는 동일한 DocumentChunk 구조를 사용한다.

    모든 청크는 다음 정보를 유지한다.
    - 원본 작업 ID(context_id)
    - 청크 순서(chunk_index)
    - 원문 출처 메타데이터(source)
    - 고유 청크 ID(id)

    임베딩 생성과 DB 저장은 이 함수에서 수행하지 않는다.
    """
    if context_id is not None:
        if isinstance(context_id, bool) or not isinstance(
            context_id,
            int,
        ):
            raise TypeError("context_id must be an integer or None")

        if context_id < 1:
            raise ValueError("context_id must be positive")

    if not isinstance(source_metadata, SourceMetadata):
        raise TypeError(
            "source_metadata must be SourceMetadata"
        )

    if source_metadata.kind == "document" and context_id is None:
        raise ValueError("document source requires context_id")
    if source_metadata.kind == "web" and context_id is not None:
        # A web page may be collected independently from active-window tracking.
        pass

    if (
        isinstance(max_chunk_length, bool)
        or not isinstance(max_chunk_length, int)
        or not 1 <= max_chunk_length <= MAX_CHUNK_TEXT_LENGTH
    ):
        raise ValueError("invalid max_chunk_length")

    # 개인정보 검사와 텍스트 정규화를 먼저 수행한다.
    normalized = normalize_search_text(
        text,
        privacy_policy=privacy_policy,
    )

    if not normalized:
        return []

    # 문단을 우선 유지하고 긴 문단만 분할한다.
    parts = _split_paragraphs(
        normalized,
        max_chunk_length,
    )

    # 중복 청크는 최초 한 개만 보존한다.
    unique_parts = _remove_duplicate_chunks(parts)

    # 검색 청크에 원본 작업 ID와 출처를 연결한다.
    return [
        DocumentChunk(
            id=str(uuid.uuid4()),
            context_id=(str(context_id) if context_id is not None else None),
            chunk_index=index,
            text=part,
            source=source_metadata,
        )
        for index, part in enumerate(unique_parts)
    ]
