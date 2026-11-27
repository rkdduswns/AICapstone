
"""검색 색인에 사용할 원문 텍스트의 정규화 및 분할 기능을 제공한다."""

import unicodedata


def normalize_text(text: str) -> str:
    """원문 의미와 내부 공백을 보존하면서 기본적인 텍스트 형식을 정리한다."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\x00", "")
    normalized = unicodedata.normalize("NFC", normalized)
    return normalized.strip()


def _find_split_position(
    text: str,
    start: int,
    end: int,
) -> int:
    """지정된 범위 안에서 우선순위에 따라 분할 위치를 찾는다."""
    separators = ("\n\n", "\n", ". ", "! ", "? ", " ")

    for separator in separators:
        position = text.rfind(separator, start, end)

        if position > start:
            return position + len(separator)

    return end


def split_text_into_chunks(
    text: str,
    max_chunk_size: int = 2000,
    overlap: int = 200,
) -> list[str]:
    """긴 텍스트를 중복 구간이 있는 작은 청크들로 분할한다."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be positive")

    if overlap < 0 or overlap >= max_chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than max_chunk_size"
        )

    normalized = normalize_text(text)

    if not normalized:
        return []

    chunks = []
    start = 0

    while start < len(normalized):
        end = min(start + max_chunk_size, len(normalized))

        if end < len(normalized):
            end = _find_split_position(normalized, start, end)

        chunk = normalized[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(normalized):
            break

        next_start = max(start + 1, end - overlap)

        while next_start < end and normalized[next_start].isspace():
            next_start += 1

        start = next_start

    return chunks


def _overlap_length(left: str, right: str) -> int:
    """왼쪽 청크의 끝과 오른쪽 청크의 시작이 겹치는 길이를 반환한다."""
    max_length = min(len(left), len(right))

    for length in range(max_length, 0, -1):
        if left[-length:] == right[:length]:
            return length

    return 0


def merge_short_chunks(
    chunks: list[str],
    min_chunk_size: int = 100,
    max_chunk_size: int = 2000,
) -> list[str]:
    """짧은 청크를 인접 청크와 병합하고 기존 중복 구간을 제거한다."""
    if not isinstance(chunks, list):
        raise TypeError("chunks must be a list")

    if min_chunk_size <= 0:
        raise ValueError("min_chunk_size must be positive")

    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be positive")

    if min_chunk_size > max_chunk_size:
        raise ValueError("min_chunk_size must not exceed max_chunk_size")

    if any(not isinstance(chunk, str) for chunk in chunks):
        raise TypeError("every chunk must be a string")

    merged = [chunk.strip() for chunk in chunks if chunk.strip()]

    index = 0

    while index < len(merged):
        current = merged[index]

        # 첫 번째 청크가 아니면 앞 청크와 병합을 시도한다.
        if index > 0:
            left = merged[index - 1]
            overlap = _overlap_length(left, current)
            candidate = left + current[overlap:]

            if (
                overlap > 0 or len(current) < min_chunk_size
            ) and len(candidate) <= max_chunk_size:
                merged[index - 1] = candidate
                merged.pop(index)
                index = max(0, index - 1)
                continue

        # 앞 청크와 병합하지 못한 짧은 청크는 다음 청크와 병합한다.
        if len(current) < min_chunk_size and index + 1 < len(merged):
            right = merged[index + 1]
            overlap = _overlap_length(current, right)
            candidate = current + right[overlap:]

            if len(candidate) <= max_chunk_size:
                merged[index] = candidate
                merged.pop(index + 1)
                continue

        index += 1

    return merged