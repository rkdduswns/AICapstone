"""받은 검색 결과의 표시 순서와 출처 텍스트를 구성한다."""

from collections.abc import Sequence

from client.time_values import format_timestamp, parse_timestamp
from shared.search_data import DocumentChunk

RESULT_ORDERS = (
    ("관련도 순", "relevance"),
    ("최근 열람순", "recent"),
    ("오래된 열람순", "oldest"),
    ("본문 긴 순", "longest"),
    ("본문 짧은 순", "shortest"),
)


def ordered_chunks(
    chunks: Sequence[DocumentChunk], order: str,
) -> list[tuple[int, DocumentChunk]]:
    """정렬 키가 같으면 공급자 순서를 유지하고 원래 인덱스를 함께 반환한다."""
    indexed = list(enumerate(chunks))
    if order in ("recent", "oldest"):
        return sorted(indexed, key=lambda hit: parse_timestamp(hit[1].source.last_active_at),
                      reverse=order == "recent")
    if order in ("longest", "shortest"):
        return sorted(indexed, key=lambda hit: len(hit[1].text), reverse=order == "longest")
    return indexed


def chunk_source(chunk: DocumentChunk) -> tuple[str, str, str]:
    """확보 시점의 제목, 유형과 URL 또는 파일 경로를 반환한다."""
    source = chunk.source
    title = source.window_title or "(제목 없음)"
    if source.browser is not None:
        return source.browser.page_title or title, "웹", source.browser.url or ""
    if source.document is not None:
        return title, source.document.file_type.upper(), source.document.file_path
    return title, "", ""


def chunk_detail(chunk: DocumentChunk) -> str:
    """출처와 작업 시각, 본문 확보 시각, 관련 조각을 함께 표시한다."""
    return f"{chunk_metadata(chunk)}\n\n{chunk.text}"


def chunk_metadata(chunk: DocumentChunk) -> str:
    """본문과 분리해 펼칠 수 있는 확보 당시 출처와 시각을 구성한다."""
    title, kind, address = chunk_source(chunk)
    source = chunk.source
    return (
        f"{title}\n출처 ({kind}) · {address}\n"
        f"프로그램 · {source.application} ({source.process_name})\n"
        f"열람 시작 · {format_timestamp(source.started_at)}\n"
        f"마지막 활성 · {format_timestamp(source.last_active_at)}\n"
        f"본문 확보 · {format_timestamp(source.captured_at)}\n"
        f"조각 길이 · {len(chunk.text):,}자\n"
        f"작업 ID · {chunk.context_id}"
    )
