"""검색 결과에서 확인된 출처와 본문을 일반 텍스트로 표현한다."""

from client.time_values import format_timestamp
from shared.search_data import DocumentChunk


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
    title, kind, address = chunk_source(chunk)
    source = chunk.source
    return (
        f"{title}\n출처 ({kind}) · {address}\n"
        f"프로그램 · {source.application} ({source.process_name})\n"
        f"열람 시작 · {format_timestamp(source.started_at)}\n"
        f"마지막 활성 · {format_timestamp(source.last_active_at)}\n"
        f"본문 확보 · {format_timestamp(source.captured_at)}\n"
        f"작업 ID · {chunk.context_id}\n\n{chunk.text}"
    )
