"""최근 기록의 HTTP 조회·표시·갱신·실패를 가상 데이터로 검증한다."""

import json
import os
import socket
import sys
import threading
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QAbstractItemView, QApplication

from client.records_client import read_recent_records
from client.window import MainWindow

HEALTH = {"ok": True, "error": None, "data": {
    "service": "contexttrace-backend", "api_version": 1, "version": "test", "status": "running"}}
ACTIVITY = {"ok": True, "error": None, "data": {
    "service": "contexttrace-backend", "api_version": 1,
    "collection_status": "collecting", "window": {
        "application": "현재 창", "process_name": "current.exe", "process_id": 99,
        "window_title": "현재 창은 기록 조회와 독립적이다"}}}
RECORD = {"id": "old", "application": "Google Chrome", "process_name": "chrome.exe",
          "window_title": "가상 자료", "started_at": "2026-10-01T10:00:00+09:00",
          "last_active_at": "2026-10-01T10:05:00+09:00", "active_duration_ms": 65000,
          "foreground_count": 1}
NEWER = {**RECORD, "id": "new", "application": "Visual Studio Code",
         "process_name": "Code.exe", "last_active_at": "2026-10-01T01:10:00Z",
         "foreground_count": 3}
GOOD = {"ok": True, "error": None, "data": {
    "service": "contexttrace-backend", "api_version": 1, "records": [RECORD, NEWER]}}
PATH = "/records/recent?limit=20"


@pytest.fixture(scope="module")
def app():
    """모든 화면 테스트에서 같은 Qt 이벤트 루프를 사용한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=5):
    """이벤트를 처리하며 비동기 완료를 기다리고 무한 대기를 막는다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Qt operation timed out")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def fake_server():
    """기존 상태/현재 창 API와 지연 가능한 기록 API를 독립적으로 제공한다."""
    settings = {"body": deepcopy(GOOD), "status": 200, "delay": 0,
                "content_type": "application/json", "health": deepcopy(HEALTH), "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """요청 도착 시 응답을 고정하여 재확인 이후 늦은 응답을 재현한다."""
            settings["paths"].append(self.path)
            body, status, delay, content_type = None, 200, 0, "application/json"
            if self.path == "/health":
                body = settings["health"]
            elif self.path == "/activity/current":
                body = ACTIVITY
            elif self.path == PATH:
                body, status, delay, content_type = (
                    settings["body"], settings["status"], settings["delay"], settings["content_type"])
            else:
                self.send_error(404)
                return
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            time.sleep(delay)
            if status == 0:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # 취소/timeout 시 Client가 먼저 소켓을 닫는 것은 정상이다.

        def log_message(self, *args):
            """가상 요청 로그를 테스트 출력에 남기지 않는다."""
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, settings
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def window(app, fake_server):
    """각 테스트에 새 창을 주고 HTTP 요청과 타이머를 정리한다."""
    instance = MainWindow(fake_server[0])
    instance.activity.poll_timer.setInterval(50)
    instance.show()
    try:
        yield instance
    finally:
        instance.close()
        app.processEvents()


def open_records(app, window):
    """호환되는 서비스 확인 후 탭을 열어 초기 목록 조회를 기다린다."""
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    window.tabs.setCurrentWidget(window.recent)
    wait_for(app, lambda: window.recent.button.isEnabled())


@pytest.mark.parametrize("payload", [b"bad", b"[]", b"null", b"\xff", b"{}"])
def test_malformed_records_rejected(payload):
    """형식 오류가 비동기 화면 처리까지 전달되지 않게 거부한다."""
    with pytest.raises(ValueError):
        read_recent_records(payload)


@pytest.mark.parametrize("field,value", [
    ("id", ""), ("id", 1), ("application", " "), ("process_name", None),
    ("window_title", None), ("started_at", "2026-10-01T10:00:00"),
    ("last_active_at", "2026-02-30T10:00:00Z"),
    ("last_active_at", "2026-10-01T00:00:00Z"),
    ("last_active_at", "2026-10-01T10:00:00+09:60"),
    ("active_duration_ms", True), ("active_duration_ms", -1),
    ("active_duration_ms", 1.5), ("active_duration_ms", "1000"),
    ("foreground_count", True), ("foreground_count", 0), ("foreground_count", "1"),
])
def test_invalid_record_fields(field, value):
    """형식·시간 순서·누적값·활성화 횟수를 검사하고 일부 행만 성공 처리하지 않는다."""
    body = deepcopy(GOOD)
    body["data"]["records"][1][field] = value
    with pytest.raises(ValueError):
        read_recent_records(json.dumps(body).encode())


@pytest.mark.parametrize("field", list(RECORD))
def test_missing_record_field_rejected(field):
    """필수 저장 필드 누락과 합법적인 0 또는 빈 제목을 구분한다."""
    body = deepcopy(GOOD)
    del body["data"]["records"][0][field]
    with pytest.raises(ValueError):
        read_recent_records(json.dumps(body).encode())


@pytest.mark.parametrize("path,value", [
    (("ok",), 1), (("error",), {}), (("data",), None),
    (("data", "service"), "other"), (("data", "api_version"), True),
    (("data", "api_version"), 2), (("data", "api_version"), "1"),
    (("data", "records"), None), (("data", "records"), [None]),
    (("data", "records"), [RECORD, RECORD]),
    (("data", "records"), [{**RECORD, "id": str(i)} for i in range(21)]),
])
def test_invalid_envelope_and_list(path, value):
    """잘못된 서비스, 중복 ID, 조회 개수 초과를 정상 목록으로 표시하지 않는다."""
    body = deepcopy(GOOD)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_recent_records(json.dumps(body).encode())


def test_timezone_sort_and_empty_title():
    """문자열 순서와 다른 시간대 순서, 빈 제목·0밀리초·동일 순간의 ID순을 확인한다."""
    body = deepcopy(GOOD)
    body["data"]["records"][0].update(window_title="", active_duration_ms=0)
    body["data"]["records"].append({**NEWER, "id": "aaa"})
    records = read_recent_records(json.dumps(body).encode())
    assert [record.id for record in records] == ["aaa", "new", "old"]
    assert records[2].window_title == ""
    assert records[2].active_duration_ms == 0


def test_lazy_load_and_health_gate(app, window, fake_server):
    """연결 확인 전이나 호환성 실패 시 조회하지 않고 탭 최초 진입 시만 요청한다."""
    settings = fake_server[1]
    assert not window.recent.button.isEnabled()
    window.recent.refresh()
    assert settings["paths"] == []
    settings["health"]["data"]["service"] = "other"
    window.tabs.setCurrentWidget(window.recent)
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    assert PATH not in settings["paths"]
    settings["health"] = HEALTH
    window.tabs.setCurrentIndex(0)
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    assert PATH not in settings["paths"]
    window.tabs.setCurrentWidget(window.recent)
    wait_for(app, lambda: window.recent.loaded)
    assert settings["paths"].count(PATH) == 1
    window.tabs.setCurrentIndex(0)
    window.tabs.setCurrentWidget(window.recent)
    assert settings["paths"].count(PATH) == 1


def test_records_display_refresh_replace_and_empty(app, window, fake_server):
    """최신순 표시·서버 값·선택 유지·새로고침 갱신·빈 목록을 실제 HTTP로 확인한다."""
    open_records(app, window)
    recent = window.recent
    assert recent.table.rowCount() == 2
    assert recent.table.item(0, 0).text() == "Visual Studio Code"
    assert recent.table.item(0, 3).text() == "00:01:05"
    assert "재방문: 2회" in recent.detail.toPlainText()
    assert recent.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    recent.table.selectRow(1)
    body = deepcopy(GOOD)
    body["data"]["records"][0].update(window_title="갱신된 가상 제목", active_duration_ms=90061000)
    fake_server[1]["body"] = body
    recent.button.click()
    assert not recent.button.isEnabled()
    wait_for(app, lambda: recent.button.isEnabled())
    assert recent.table.rowCount() == 2
    assert recent.table.currentRow() == 1
    assert recent.table.item(1, 1).text() == "갱신된 가상 제목"
    assert recent.table.item(1, 3).text() == "25:01:01"
    assert "갱신된 가상 제목" in recent.detail.toPlainText()
    body["data"]["records"] = []
    recent.button.click()
    wait_for(app, lambda: recent.button.isEnabled())
    assert recent.status.text() == "저장된 작업 기록이 없습니다."
    assert recent.table.rowCount() == 0
    assert recent.detail.toPlainText() == ""
    assert recent.updated_at.text() != "마지막 정상 조회: 없음"


@pytest.mark.parametrize("status,body,content_type,expected", [
    (404, b"{}", "application/json", "기능 준비 중"),
    (500, b"private detail", "application/json", "조회 실패"),
    (302, b"{}", "application/json", "조회 실패"),
    (0, b"", "application/json", "연결 안 됨"),
    (200, b"bad", "application/json", "호환되지 않는"),
    (200, b"{}", "text/html", "호환되지 않는"),
])
def test_failure_clear_and_manual_recovery(app, window, fake_server, status, body, content_type,
                                         expected):
    """오류를 빈 목록으로 오인하지 않고 이전 기록을 제거한 뒤 수동 재시도로 복구한다."""
    open_records(app, window)
    recent = window.recent
    settings = fake_server[1]
    settings.update(status=status, body=body, content_type=content_type)
    recent.refresh()
    wait_for(app, lambda: recent.button.isEnabled())
    assert recent.status.text().startswith(expected)
    assert recent.table.rowCount() == 0
    assert recent.detail.toPlainText() == ""
    assert "private detail" not in recent.status.text()
    settings.update(status=200, body=GOOD, content_type="application/json")
    recent.refresh()
    wait_for(app, lambda: recent.button.isEnabled())
    assert recent.table.rowCount() == 2
    assert window.application.text() == "현재 창"


def test_timeout_keeps_current_window_and_prevents_overlap(app, window, fake_server):
    """기록 응답 지연 중에도 현재 창과 Qt 이벤트가 살아 있고 요청이 중복되지 않는다."""
    open_records(app, window)
    recent = window.recent
    fake_server[1]["delay"] = 0.3
    recent.client.timer.setInterval(80)
    ticks = []
    QTimer.singleShot(10, lambda: ticks.append(True))
    recent.refresh()
    reply = recent.client.reply
    recent.refresh()
    assert recent.client.reply is reply
    wait_for(app, lambda: recent.button.isEnabled())
    assert recent.status.text().startswith("조회 시간 초과")
    assert ticks and window.application.text() == "현재 창"
    fake_server[1]["delay"] = 0
    recent.client.timer.setInterval(3000)
    recent.refresh()
    wait_for(app, lambda: recent.button.isEnabled())
    assert recent.table.rowCount() == 2


def test_recheck_and_close_cancel_late_history(app, window, fake_server):
    """연결 재확인과 종료 이후 예전 기록 응답이 화면을 다시 채우지 못하게 한다."""
    open_records(app, window)
    recent = window.recent
    settings = fake_server[1]
    settings["delay"] = 0.25
    count = settings["paths"].count(PATH)
    recent.refresh()
    wait_for(app, lambda: settings["paths"].count(PATH) > count)
    settings.update(delay=0, body={**GOOD, "data": {**GOOD["data"], "records": []}})
    window.check()
    wait_for(app, lambda: recent.status.text() == "저장된 작업 기록이 없습니다.")
    done = []
    QTimer.singleShot(350, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert recent.table.rowCount() == 0
    settings.update(delay=0.25, body=GOOD)
    count = settings["paths"].count(PATH)
    recent.refresh()
    wait_for(app, lambda: settings["paths"].count(PATH) > count)
    window.close()
    assert recent.client.reply is None
    assert not recent.client.timer.isActive()
    assert not recent.button.isEnabled()
    done.clear()
    QTimer.singleShot(350, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert recent.table.rowCount() == 0


def test_long_plain_text_title(app, window, fake_server):
    """한글·HTML 형태·여러 줄 제목을 실행하지 않고 상세란에 원문으로 보존한다."""
    title = "<b>가상 자료</b>\n" + "긴 한글 제목 " * 200
    fake_server[1]["body"]["data"]["records"][1]["window_title"] = title
    open_records(app, window)
    assert window.recent.table.item(0, 1).text() == title
    assert title in window.recent.detail.toPlainText()
    assert window.width() == 620
