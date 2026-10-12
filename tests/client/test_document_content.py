"""가상 HTTP로 파일 출처와 저장 문서 상세를 검증한다. 실제 문서를 열거나 추출하지 않는다."""

import json
import os
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication

from client.document_content_client import (
    DocumentSourceChangedError,
    read_record_document_content,
)
from client.document_values import read_document
from client.records_client import read_recent_records
from client.window import MainWindow
from shared.document import (
    DocumentContent,
    LocalDocument,
    RecordDocumentContent,
    RecordDocumentContentResponse,
)
from shared.protocol import HealthResponse, HealthStatus
from shared.records import ContextRecord, RecentRecords, RecentRecordsResponse

SPECIAL_ID = "가상/record?x=1&y=2#+%"
PDF = LocalDocument(r"C:\가상 자료\연구.PDF", "pdf")
DOCX = LocalDocument(r"\\example-server\share\가상 문서.docx", "docx")
TEXT = "  첫 페이지\n<b>태그도 일반 글자입니다.</b>\n\n두 번째 페이지의 가상 본문입니다.  "
CONTENT = DocumentContent(PDF, "2026-10-12T10:05:00+09:00", TEXT, False)
GOOD = asdict(RecordDocumentContentResponse(RecordDocumentContent("one", CONTENT)))


@pytest.fixture(scope="module")
def app():
    """Qt 이벤트 루프를 공유하고 테스트 창 종료 뒤에도 후속 테스트를 진행한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=4):
    """이벤트를 처리하면서 비동기 결과를 기다리되 시간 제한을 둔다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Document content UI timed out")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def server():
    """작업별 파일 출처·본문·오류·지연을 바꿔 실제 통신 경계를 검사한다."""
    settings = {
        "requests": [], "delay": {}, "status": 200, "override": None, "legacy": False,
        "sources": {"one": PDF, SPECIAL_ID: DOCX, "plain": None},
        "contents": {"one": CONTENT, SPECIAL_ID: DocumentContent(
            DOCX, "2026-10-12T10:01:00Z", "다른 DOCX의 저장 본문", False)},
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """지연 전 응답을 고정해 선택 전환 뒤 도착하는 옛 본문을 재현한다."""
            url = urlsplit(self.path)
            delay, status = 0, 200
            if url.path == "/health":
                body = asdict(HealthResponse(HealthStatus("document-test")))
            elif url.path == "/records/recent":
                records = [ContextRecord(
                    identifier, "가상 문서 앱", "sample.exe", "가상 문서 창",
                    "2026-10-12T10:00:00+09:00", f"2026-10-12T10:{20-index:02d}:00+09:00",
                    10000, 1, document=document,
                ) for index, (identifier, document) in enumerate(settings["sources"].items())]
                body = asdict(RecentRecordsResponse(RecentRecords(records)))
                if settings["legacy"]:
                    for row in body["data"]["records"]:
                        del row["document"]
            elif url.path == "/records/document-content":
                query = parse_qs(url.query)
                identifier = query["record_id"][0]
                settings["requests"].append(query)
                body = asdict(RecordDocumentContentResponse(RecordDocumentContent(
                    identifier, settings["contents"].get(identifier))))
                if settings["override"] is not None:
                    body = settings["override"]
                delay, status = settings["delay"].get(identifier, 0), settings["status"]
            else:
                self.send_error(404)
                return
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            time.sleep(delay)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # 선택 전환·timeout·종료로 Client가 취소한 연결은 정상 정리한다.

        def log_message(self, *args):
            """가상 파일 경로와 본문도 로그에 남기지 않는다."""
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_port, settings
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


@pytest.fixture
def window(app, server):
    """최근 기록과 문서 상세가 연결된 실제 앱 화면을 검사하고 요청을 정리한다."""
    instance = MainWindow(server[0])
    instance.show()
    try:
        yield instance
    finally:
        instance.close()
        # 순환 Python 참조가 Qt 콜백 도중 GC되는 일을 피하고 창·네트워크 객체를 정리한다.
        instance.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def open_records(app, window):
    """목록만 먼저 조회하여 상세 탭 진입 전 본문 요청이 없는지도 확인한다."""
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    window.tabs.setCurrentWidget(window.recent)
    wait_for(app, lambda: window.recent.loaded)
    return window.recent.document_content


def select_record(window, identifier):
    """정렬 순서 대신 작업 ID로 원하는 기록을 선택한다."""
    row = next(i for i, record in enumerate(window.recent.records) if record.id == identifier)
    window.recent.table.selectRow(row)


@pytest.mark.parametrize("source", [
    [], {}, {"file_path": None, "file_type": "pdf"},
    {"file_path": r"relative\file.pdf", "file_type": "pdf"},
    {"file_path": r"C:file.pdf", "file_type": "pdf"},
    {"file_path": r"\file.pdf", "file_type": "pdf"},
    {"file_path": "https://example.com/file.pdf", "file_type": "pdf"},
    {"file_path": "file:///C:/file.pdf", "file_type": "pdf"},
    {"file_path": r"\\?\C:\file.pdf", "file_type": "pdf"},
    {"file_path": r"\\.\C:\file.pdf", "file_type": "pdf"},
    {"file_path": r"C:\folder\..\file.pdf", "file_type": "pdf"},
    {"file_path": "C:\\file\n.pdf", "file_type": "pdf"},
    {"file_path": r"C:\file.pdf:stream", "file_type": "pdf"},
    {"file_path": r"C:\file.exe", "file_type": "pdf"},
    {"file_path": r"C:\file.docx", "file_type": "pdf"},
    {"file_path": r"C:\file.pdf", "file_type": "PDF"},
    {"file_path": r"C:\file?.pdf", "file_type": "pdf"},
    {"file_path": r"\\bad?\share\file.pdf", "file_type": "pdf"},
    {"file_path": r"\\server\..\file.pdf", "file_type": "pdf"},
    {"file_path": r"C:\folder \file.pdf", "file_type": "pdf"},
    {"file_path": r"C:\folder.\file.pdf", "file_type": "pdf"},
])
def test_invalid_file_source(source):
    """웹 주소·상대/장치 경로·확장자 불일치를 파일 출처로 표시하지 않는다."""
    with pytest.raises(ValueError):
        read_document(source)


def test_windows_sources_and_legacy_records_without_files():
    """Windows 드라이브·UNC·한글 경로를 원문으로 유지하고 구형 기록도 호환한다."""
    assert read_document(asdict(PDF)) == PDF
    assert read_document(asdict(DOCX)) == DOCX
    assert read_document({"file_path": "C:/가상 자료/a.docx", "file_type": "docx"}).file_path == (
        "C:/가상 자료/a.docx")
    record = ContextRecord("old", "앱", "sample.exe", "", "2026-10-12T00:00:00Z",
                           "2026-10-12T00:00:00Z", 0, 1)
    body = asdict(RecentRecordsResponse(RecentRecords([record])))
    del body["data"]["records"][0]["document"]
    assert read_recent_records(json.dumps(body).encode())[0].document is None
    body["data"]["records"][0]["document"] = asdict(PDF)
    assert read_recent_records(json.dumps(body).encode())[0].document == PDF
    body["data"]["records"][0]["document"]["file_type"] = "docx"
    with pytest.raises(ValueError):
        read_recent_records(json.dumps(body).encode())


@pytest.mark.parametrize("path,value", [
    (("ok",), 1), (("error",), "error"), (("data",), []),
    (("data", "service"), "other"), (("data", "api_version"), True),
    (("data", "record_id"), "other"), (("data", "content"), []),
    (("data", "content", "document"), None),
    (("data", "content", "text"), None), (("data", "content", "text"), " \n "),
    pytest.param(("data", "content", "text"), "한" * 50001, id="text-too-long"),
    (("data", "content", "truncated"), 1),
    (("data", "content", "captured_at"), "2026-10-12T10:00:00"),
    (("data", "content", "captured_at"), "2026-02-30T10:00:00Z"),
])
def test_invalid_document_content_contract(path, value):
    """잘못된 타입·ID·출처·시각·본문 길이는 일부라도 정상 표시하지 않는다."""
    body = deepcopy(GOOD)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_record_document_content(json.dumps(body).encode(), "one", PDF)


@pytest.mark.parametrize("field", ["document", "captured_at", "text", "truncated"])
def test_missing_snapshot_fields(field):
    """필수 본문 정보의 누락을 정상 빈 결과로 오인하지 않는다."""
    body = deepcopy(GOOD)
    del body["data"]["content"][field]
    with pytest.raises(ValueError):
        read_record_document_content(json.dumps(body).encode(), "one", PDF)


def test_empty_snapshot_limit_and_source_mismatch():
    """빈 결과와 누락을 구분하고 Unicode 최대 길이와 파일 출처 대조를 검증한다."""
    body = deepcopy(GOOD)
    body["data"]["content"] = None
    assert read_record_document_content(json.dumps(body).encode(), "one", PDF).content is None
    del body["data"]["content"]
    with pytest.raises(ValueError):
        read_record_document_content(json.dumps(body).encode(), "one", PDF)
    body = deepcopy(GOOD)
    body["data"]["content"].update(text="한🙂" * 25000, truncated=True)
    result = read_record_document_content(json.dumps(body).encode(), "one", PDF)
    assert len(result.content.text) == 50000 and result.content.truncated
    body["data"]["content"]["document"] = asdict(DOCX)
    with pytest.raises(DocumentSourceChangedError):
        read_record_document_content(json.dumps(body).encode(), "one", PDF)


def test_lazy_plain_text_file_path_refresh_and_empty(app, window, server):
    """파일 목록·상세·본문의 출처를 유지하고 지연 조회·일부 본문·빈 결과를 구분한다."""
    widget = open_records(app, window)
    assert server[1]["requests"] == [] and PDF.file_path in window.recent.detail.toPlainText()
    assert window.recent.table.item(0, 4).text() == PDF.file_path
    assert window.recent.table.item(0, 4).toolTip() == PDF.file_path
    window.recent.detail_tabs.setCurrentWidget(widget)
    wait_for(app, lambda: widget.loaded)
    assert widget.text.toPlainText() == TEXT and widget.text.isReadOnly()
    assert PDF.file_path in widget.source.toPlainText() and "추출 시각:" in widget.source.toPlainText()
    assert window.width() == 620
    window.recent.detail_tabs.setCurrentIndex(0)
    window.recent.detail_tabs.setCurrentWidget(widget)
    assert len(server[1]["requests"]) == 1
    server[1]["contents"]["one"] = replace(CONTENT, text="한" * 50000, truncated=True)
    widget.button.click()
    assert not widget.source.toPlainText() and not widget.text.toPlainText()
    wait_for(app, lambda: widget.loaded)
    assert "일부만 저장" in widget.status.text() and len(widget.text.toPlainText()) == 50000
    server[1]["contents"]["one"] = None
    widget.button.click()
    wait_for(app, lambda: widget.loaded)
    assert "없습니다" in widget.status.text() and not widget.text.toPlainText()


def test_selection_cancels_late_response_and_encodes_id(app, window, server):
    """늦은 PDF 응답이 DOCX를 덮지 않고 특수문자 ID를 쿼리 값 하나로 전송한다."""
    widget = open_records(app, window)
    server[1]["delay"]["one"] = 0.2
    window.recent.detail_tabs.setCurrentWidget(widget)
    wait_for(app, lambda: len(server[1]["requests"]) == 1)
    select_record(window, SPECIAL_ID)
    wait_for(app, lambda: widget.loaded)
    done = []
    QTimer.singleShot(300, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert widget.text.toPlainText() == "다른 DOCX의 저장 본문"
    assert DOCX.file_path in widget.source.toPlainText()
    assert server[1]["requests"][-1] == {"record_id": [SPECIAL_ID]}
    select_record(window, "plain")
    assert not widget.text.toPlainText() and not widget.button.isEnabled()
    assert "파일 출처가 없습니다" in widget.status.text()
    assert len(server[1]["requests"]) == 2


@pytest.mark.parametrize("status,override,message", [
    (403, None, "허용되지"), (404, None, "조회 불가"), (410, None, "이동·삭제"),
    (500, None, "서버 오류"), (200, b"not json", "호환되지"),
])
def test_errors_clear_and_manual_retry(app, window, server, status, override, message):
    """실패·이동/삭제 안내를 정상 빈 결과와 구분하고 새로고침으로 복구한다."""
    widget = open_records(app, window)
    window.recent.detail_tabs.setCurrentWidget(widget)
    wait_for(app, lambda: widget.loaded)
    server[1].update(status=status, override=override)
    widget.button.click()
    wait_for(app, lambda: widget.button.isEnabled())
    assert message in widget.status.text() and not widget.loaded
    assert not widget.text.toPlainText() and not widget.source.toPlainText()
    server[1].update(status=200, override=None)
    widget.button.click()
    wait_for(app, lambda: widget.loaded)
    assert widget.text.toPlainText() == TEXT


def test_source_changed_requires_recent_refresh(app, window, server):
    """동일 ID의 파일 출처 변경을 감지하고 목록 갱신 후 새 문서만 표시한다."""
    widget = open_records(app, window)
    server[1]["contents"]["one"] = DocumentContent(
        DOCX, "2026-10-12T10:01:00Z", "새 문서 본문", False)
    window.recent.detail_tabs.setCurrentWidget(widget)
    wait_for(app, lambda: widget.button.isEnabled())
    assert "파일 출처가 변경" in widget.status.text() and not widget.text.toPlainText()
    server[1]["sources"]["one"] = DOCX
    window.recent.button.click()
    wait_for(app, lambda: widget.loaded)
    assert widget.text.toPlainText() == "새 문서 본문"
    assert DOCX.file_path in window.recent.detail.toPlainText()


def test_timeout_duplicate_reconnect_and_close(app, window, server):
    """timeout·재연결·종료 시 요청과 옛 본문을 정리하고 중복 조회를 막는다."""
    widget = open_records(app, window)
    server[1]["delay"]["one"] = 0.25
    widget.client.timer.setInterval(50)
    window.recent.detail_tabs.setCurrentWidget(widget)
    widget.refresh()
    wait_for(app, lambda: widget.button.isEnabled())
    assert "시간 초과" in widget.status.text() and len(server[1]["requests"]) == 1
    server[1]["delay"].clear()
    widget.client.timer.setInterval(3000)
    widget.button.click()
    wait_for(app, lambda: widget.loaded)
    window.check()
    assert not widget.text.toPlainText() and widget.record_id is None
    wait_for(app, lambda: window.recent.loaded)
    wait_for(app, lambda: widget.loaded)
    server[1]["delay"]["one"] = 0.3
    widget.button.click()
    assert widget.client.reply is not None
    window.close()
    assert widget.client.reply is None and not widget.client.timer.isActive()
    assert not widget.text.toPlainText() and not widget.source.toPlainText()


def test_legacy_record_does_not_request_document(app, window, server):
    """파일 필드가 없는 구형 목록에서도 기존 화면을 유지하고 문서 상세 요청을 생략한다."""
    server[1]["legacy"] = True
    widget = open_records(app, window)
    window.recent.detail_tabs.setCurrentWidget(widget)
    assert server[1]["requests"] == []
    assert "파일 출처가 없습니다" in widget.status.text() and not widget.button.isEnabled()
