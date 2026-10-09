"""저장된 복사 텍스트의 가상 HTTP 조회를 검사한다. OS 클립보드는 읽지 않는다."""

import json
import os
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.clipboard_client import read_record_clipboard
from client.window import MainWindow
from shared.clipboard import ClipboardEntry, RecordClipboard, RecordClipboardResponse
from shared.protocol import HealthResponse, HealthStatus
from shared.records import ContextRecord, RecentRecords, RecentRecordsResponse

SPECIAL_ID = "가상/record?x=1&y=2#+%"
TEXT = "  <b>가상 복사 자료</b>\n" + "줄바꿈과 한글 원문 " * 100
ENTRIES = [ClipboardEntry("older", "2026-10-08T09:00:00+09:00", "이전 복사"),
           ClipboardEntry("newer", "2026-10-08T00:05:00Z", TEXT)]
GOOD = asdict(RecordClipboardResponse(RecordClipboard("one", ENTRIES, False)))


@pytest.fixture(scope="module")
def app():
    """Qt 화면 테스트에서 같은 이벤트 루프를 사용한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=4):
    """이벤트를 처리하면서 비동기 상태 완료를 기다린다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Clipboard detail timed out")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def server():
    """작업별 응답을 지연할 수 있어 빠른 선택 전환과 늦은 응답을 재현한다."""
    settings = {"requests": [], "delay": {}, "status": 200, "override": None,
                "entries": ENTRIES, "has_more": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """실제 쿼리를 해석하고 요청 순간의 본문을 고정해 보낸다."""
            url = urlsplit(self.path)
            delay, status = 0, 200
            if url.path == "/health":
                body = asdict(HealthResponse(HealthStatus("test")))
            elif url.path == "/records/recent":
                body = asdict(RecentRecordsResponse(RecentRecords([
                    ContextRecord(identifier, "가상 앱", "sample.exe", identifier,
                                  "2026-10-08T08:00:00+09:00", "2026-10-08T09:10:00+09:00",
                                  10000, 1) for identifier in ("one", SPECIAL_ID)
                ])))
            elif url.path == "/records/clipboard":
                query = parse_qs(url.query)
                identifier = query["record_id"][0]
                settings["requests"].append(query)
                entries = (settings["entries"] if identifier == "one" else [
                    ClipboardEntry("special-copy", "2026-10-08T09:01:00+09:00", "다른 작업의 복사")])
                body = asdict(RecordClipboardResponse(RecordClipboard(
                    identifier, entries, settings["has_more"])))
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
                return  # 선택 전환이나 창 종료에 따른 요청 취소다.

        def log_message(self, *args):
            """가상 복사 텍스트나 요청을 로그에 기록하지 않는다."""
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
    """일반 최근 기록 화면에서 복사 상세까지 연결해 확인한다."""
    instance = MainWindow(server[0])
    instance.show()
    try:
        yield instance
    finally:
        instance.close()
        app.processEvents()


def open_records(app, window):
    """최근 기록만 먼저 열어 복사 내용이 지연 조회되는지 확인할 수 있게 한다."""
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    window.tabs.setCurrentWidget(window.recent)
    wait_for(app, lambda: window.recent.loaded)
    return window.recent.clipboard


@pytest.mark.parametrize("field,value", [
    ("id", ""), ("id", None), ("text", None), ("text", " "), ("text", "a" * 10001),
    ("copied_at", "2026-10-08T09:00:00"), ("copied_at", "2026-02-30T09:00:00Z"),
])
def test_invalid_entry(field, value):
    """원문·복사 시각·식별자를 검증하며 잘못된 행을 부분 표시하지 않는다."""
    body = deepcopy(GOOD)
    body["data"]["entries"][0][field] = value
    with pytest.raises(ValueError):
        read_record_clipboard(json.dumps(body).encode(), "one")


@pytest.mark.parametrize("path,value", [
    (("ok",), 1), (("error",), "error"), (("data",), None),
    (("data", "service"), "other"), (("data", "api_version"), True),
    (("data", "record_id"), "wrong-record"), (("data", "has_more"), 1),
    (("data", "entries"), None), (("data", "entries"), [None]),
    (("data", "entries"), [asdict(ENTRIES[0])] * 2),
    (("data", "entries"), [{**asdict(ENTRIES[0]), "id": str(i)} for i in range(21)]),
])
def test_invalid_list_or_other_record(path, value):
    """다른 작업 응답·중복 ID·개수 초과를 정상적인 복사 목록으로 수용하지 않는다."""
    body = deepcopy(GOOD)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_record_clipboard(json.dumps(body).encode(), "one")


@pytest.mark.parametrize("field", ["record_id", "entries", "has_more"])
def test_missing_required_fields(field):
    """필드 누락을 빈 목록이나 잘못된 작업 연결로 처리하지 않는다."""
    body = deepcopy(GOOD)
    del body["data"][field]
    with pytest.raises(ValueError):
        read_record_clipboard(json.dumps(body).encode(), "one")


def test_sort_and_exact_text():
    """서로 다른 시간대는 실제 시각순으로 정렬하고 원문 공백/내용은 바꾸지 않는다."""
    body = deepcopy(GOOD)
    body["data"]["entries"].append({**asdict(ENTRIES[1]), "id": "aaa"})
    body["data"]["entries"][0]["text"] = "한" * 10000
    result = read_record_clipboard(json.dumps(body).encode(), "one")
    assert [entry.id for entry in result.entries] == ["aaa", "newer", "older"]
    assert result.entries[0].text == TEXT
    assert len(result.entries[-1].text) == 10000


def test_lazy_detail_display_refresh_and_empty(app, window, server):
    """본문은 상세 탭에서만 가져오고 항목 선택·새로고침·빈 목록을 표시한다."""
    clipboard = open_records(app, window)
    assert server[1]["requests"] == []
    window.recent.detail_tabs.setCurrentWidget(clipboard)
    wait_for(app, lambda: clipboard.loaded)
    assert clipboard.text.toPlainText() == TEXT
    assert clipboard.text.isReadOnly() and window.width() == 620
    clipboard.selector.setCurrentIndex(1)
    assert clipboard.text.toPlainText() == "이전 복사"
    assert server[1]["requests"] == [{"record_id": ["one"], "limit": ["20"]}]
    window.recent.detail_tabs.setCurrentIndex(0)
    window.recent.detail_tabs.setCurrentWidget(clipboard)
    assert len(server[1]["requests"]) == 1
    server[1]["has_more"] = True
    clipboard.button.click()
    wait_for(app, lambda: clipboard.loaded)
    assert "이전 항목 더 있음" in clipboard.status.text()
    server[1].update(entries=[], has_more=False)
    clipboard.button.click()
    wait_for(app, lambda: clipboard.loaded)
    assert "없습니다" in clipboard.status.text() and clipboard.text.toPlainText() == ""


def test_selection_change_cancels_old_response_and_encodes_id(app, window, server):
    """늦은 A 응답이 B의 본문을 덮지 못하며 특수문자 ID를 정확히 전달한다."""
    clipboard = open_records(app, window)
    server[1]["delay"]["one"] = 0.2
    window.recent.detail_tabs.setCurrentWidget(clipboard)
    wait_for(app, lambda: len(server[1]["requests"]) == 1)
    window.recent.table.selectRow(1)
    assert clipboard.text.toPlainText() == ""
    wait_for(app, lambda: clipboard.loaded)
    done = []
    QTimer.singleShot(300, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert clipboard.record_id == SPECIAL_ID and clipboard.text.toPlainText() == "다른 작업의 복사"
    assert server[1]["requests"][-1] == {"record_id": [SPECIAL_ID], "limit": ["20"]}
    window.recent.refresh()
    assert clipboard.text.toPlainText() == "" and clipboard.record_id is None


@pytest.mark.parametrize("status,body", [(404, None), (500, None), (200, b"bad json"),
                                       (200, {**GOOD, "data": {**GOOD["data"], "record_id": "other"}})])
def test_error_clears_text_and_manual_recovery(app, window, server, status, body):
    """실패를 빈 목록과 구분하고 기존 복사 내용을 제거한 뒤 수동 복구한다."""
    clipboard = open_records(app, window)
    window.recent.detail_tabs.setCurrentWidget(clipboard)
    wait_for(app, lambda: clipboard.loaded)
    server[1].update(status=status, override=body)
    clipboard.refresh()
    wait_for(app, lambda: clipboard.button.isEnabled())
    assert clipboard.text.toPlainText() == "" and not clipboard.loaded
    assert clipboard.status.text() and "없습니다" not in clipboard.status.text()
    server[1].update(status=200, override=None)
    clipboard.button.click()
    wait_for(app, lambda: clipboard.loaded)
    assert clipboard.text.toPlainText() == TEXT


def test_timeout_single_flight_and_close(app, window, server):
    """중복 요청·timeout을 처리하고 창 종료 후 응답과 타이머를 정리한다."""
    clipboard = open_records(app, window)
    server[1]["delay"]["one"] = 0.2
    clipboard.client.timer.setInterval(60)
    window.recent.detail_tabs.setCurrentWidget(clipboard)
    reply = clipboard.client.reply
    clipboard.refresh()
    assert clipboard.client.reply is reply
    wait_for(app, lambda: clipboard.button.isEnabled())
    assert "시간 초과" in clipboard.status.text()
    clipboard.client.timer.setInterval(3000)
    clipboard.refresh()
    window.close()
    done = []
    QTimer.singleShot(300, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert clipboard.client.reply is None and not clipboard.client.timer.isActive()
    assert clipboard.record_id is None and clipboard.text.toPlainText() == ""
