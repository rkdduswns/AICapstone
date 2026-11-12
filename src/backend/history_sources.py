"""실제 작업 ID를 기준으로 출처를 투영하고 현재 브라우저에만 새 출처를 연결한다."""

from dataclasses import asdict

from fastapi import FastAPI, Query
from starlette.exceptions import HTTPException

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from shared.browser import BrowserPage
from shared.document import (
    MAX_DOCUMENT_CONTENT_LENGTH,
    RECORD_DOCUMENT_CONTENT_PATH,
    DocumentContent,
    RecordDocumentContent,
    RecordDocumentContentResponse,
    read_document,
)
from shared.records import ContextRecord
from shared.web_content import (
    MAX_WEB_CONTENT_LENGTH,
    RECORD_WEB_CONTENT_PATH,
    RecordWebContent,
    RecordWebContentResponse,
    WebContent,
)


def context_record(store: ActivityStore, record) -> ContextRecord:
    """제목/시간 근접도로 추측하지 않고 저장된 외래 키에 연결된 출처만 목록에 넣는다."""
    page = store.get_record_browser(record.id)
    document = store.get_record_document(record.id)
    return ContextRecord(
        str(record.id), record.application, record.process_name, record.window_title,
        record.started_at, record.ended_at, record.active_duration_ms, 1,
        BrowserPage(page.browser, page.page_title, page.url) if page else None,
        read_document({"file_path": document.file_path, "file_type": document.file_type[1:]})
        if document else None,
    )


def require_browser_activity(tracker: ActivityTracker, record_id: int, browser: str):
    """요청이 관측한 작업과 현재 활성 브라우저가 같아야 연결/본문 저장을 허용한다."""
    activity = tracker.get_current_activity()
    expected_process = {"chrome": "chrome.exe", "edge": "msedge.exe"}[browser]
    if (activity.collection_status != "collecting" or activity.record_id != str(record_id)
            or activity.window is None or activity.window.process_name.casefold() != expected_process):
        raise HTTPException(409, detail="Active browser activity changed")
    return activity


def save_linked_browser(tracker: ActivityTracker, record_id: int, browser: str,
                        url: str, title: str, captured_at: str) -> tuple[int, int]:
    """같은 URL 재전송은 재사용하고 같은 제목의 URL 이동도 별도 작업 이력으로 보존한다."""
    require_browser_activity(tracker, record_id, browser)
    store = tracker.store
    previous = store.get_record_browser(record_id)
    if previous and (previous.browser, previous.url) != (browser, url):
        tracker.finish()
        activity = tracker.get_current_activity()
        if activity.record_id is None:
            raise HTTPException(409)
        record_id = int(activity.record_id)
        require_browser_activity(tracker, record_id, browser)
    elif previous and previous.page_title == title:
        return previous.id, record_id
    source_id = store.save_browser_source_record(browser, url, title, captured_at, record_id)
    return source_id, record_id


def install_source_routes(app: FastAPI) -> None:
    """기존 Client의 작업별 저장 본문 조회 계약을 실제 SQLite 출처 연결에 적용한다."""
    def store_and_record(record_id: int):
        """존재하지 않는 작업과 본문이 아직 없는 작업을 구분한다."""
        store = app.state.activity_tracker.store
        if store.get_record(record_id) is None:
            raise HTTPException(404)
        return store

    @app.get(RECORD_WEB_CONTENT_PATH)
    async def web_content(record_id: int = Query(ge=1, le=2**63 - 1)):
        """작업의 최신 출처와 그 출처에 속한 본문만 같은 응답으로 반환한다."""
        store = store_and_record(record_id)
        page = store.get_record_browser(record_id)
        body = store.get_browser_content_record(page.id) if page else None
        content = WebContent(
            BrowserPage(page.browser, page.page_title, page.url), body.captured_at,
            body.content_text[:MAX_WEB_CONTENT_LENGTH], len(body.content_text) > MAX_WEB_CONTENT_LENGTH,
        ) if body else None
        return asdict(RecordWebContentResponse(RecordWebContent(str(record_id), content)))

    @app.get(RECORD_DOCUMENT_CONTENT_PATH)
    async def document_content(record_id: int = Query(ge=1, le=2**63 - 1)):
        """원본 파일을 다시 열지 않고 연결 당시의 경로·시각·저장 본문을 반환한다."""
        store = store_and_record(record_id)
        row = store.get_record_document(record_id)
        content = None
        if row:
            document = read_document({"file_path": row.file_path, "file_type": row.file_type[1:]})
            content = DocumentContent(document, row.captured_at,
                                      row.extracted_text[:MAX_DOCUMENT_CONTENT_LENGTH],
                                      len(row.extracted_text) > MAX_DOCUMENT_CONTENT_LENGTH)
        return asdict(RecordDocumentContentResponse(RecordDocumentContent(str(record_id), content)))
