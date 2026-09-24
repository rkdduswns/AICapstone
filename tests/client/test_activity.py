"""가상 HTTP 서버로 Phase 2 표시·전환·실패·취소를 검증한다. 실제 작업 정보는 사용하지 않는다."""

import json
import os
import socket
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

# Linux 테스트만 가상 화면을 사용하며 Windows는 기본 Qt 플랫폼을 사용한다.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from client.activity_client import read_activity
from client.window import MainWindow
from shared.activity import ACTIVITY_PATH, ActiveWindow, CurrentActivity, CurrentActivityResponse
from shared.protocol import HealthResponse, HealthStatus

HEALTH = asdict(HealthResponse(HealthStatus(version="test")))
GOOD = asdict(CurrentActivityResponse(CurrentActivity("collecting", ActiveWindow(
    application="Google Chrome", process_name="chrome.exe", process_id=1234,
    window_title="가상 자료 — ContextTrace",
))))


@pytest.fixture(scope="module")
def app():
    """모듈 동안 Qt 앱을 유지해 창 종료 후에도 다음 테스트를 실행한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=5):
    """동기 대기로 Qt 콜백을 막지 않도록 이벤트를 처리하며 조건을 기다린다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Qt operation timed out")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def fake_server():
    """각 요청 시작 시 응답을 고정하여 늦은 이전 응답도 재현할 수 있게 한다."""
    settings = {"body": deepcopy(GOOD), "status": 200, "delay": 0,
                "content_type": "application/json", "health": deepcopy(HEALTH), "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """실제 loopback HTTP를 통해 경로별 가상 응답을 돌려준다."""
            settings["paths"].append(self.path)
            if self.path == "/health":
                body, status, delay, content_type = settings["health"], 200, 0, "application/json"
            else:
                assert self.path == ACTIVITY_PATH
                body, status, delay, content_type = (
                    settings["body"], settings["status"], settings["delay"], settings["content_type"])
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            time.sleep(delay)
            if status == 0:
                # HTTP 응답 전에 소켓을 닫아 전송 실패와 자동 복구를 검증한다.
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # 요청 취소 테스트에서 연결이 먼저 닫히는 것은 정상이다.

        def log_message(self, *args):
            """가상 서버의 요청 로그가 테스트 결과를 가리지 않도록 한다."""
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
    """매 테스트마다 새 화면을 만들고 타이머와 요청을 반드시 정리한다."""
    instance = MainWindow(fake_server[0])
    instance.activity.poll_timer.setInterval(30)
    instance.show()
    try:
        yield instance
    finally:
        instance.close()
        app.processEvents()


@pytest.mark.parametrize("payload", [b"bad json", b"[]", b"null", b"{}", b"\xff"])
def test_reject_malformed_activity(payload):
    """파싱할 수 없는 응답이 UI 콜백 밖으로 전파되지 않게 ValueError로 거부한다."""
    with pytest.raises(ValueError):
        read_activity(payload)


@pytest.mark.parametrize("path,value", [
    (("ok",), 1), (("error",), {}), (("data",), []),
    (("data", "service"), "other"), (("data", "api_version"), True),
    (("data", "api_version"), "1"), (("data", "api_version"), 2),
    (("data", "collection_status"), "paused"), (("data", "collection_status"), []),
    (("data", "window"), None), (("data", "window", "application"), " "),
    (("data", "window", "process_name"), None),
    (("data", "window", "process_id"), True), (("data", "window", "process_id"), 0),
    (("data", "window", "process_id"), -1), (("data", "window", "process_id"), "1234"),
    (("data", "window", "window_title"), None),
])
def test_reject_incompatible_activity(path, value):
    """잘못된 타입과 상태 조합을 정상 감지로 오인하지 않는다."""
    body = deepcopy(GOOD)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_activity(json.dumps(body).encode())


@pytest.mark.parametrize("field", ["error", "window", "window_title"])
def test_required_fields_cannot_be_omitted(field):
    """null/빈 제목과 필드 자체 누락은 다르게 처리한다."""
    body = deepcopy(GOOD)
    target = body if field == "error" else (
        body["data"] if field == "window" else body["data"]["window"])
    del target[field]
    with pytest.raises(ValueError):
        read_activity(json.dumps(body).encode())


@pytest.mark.parametrize("status", ["no_active_window", "unsupported", "error"])
def test_noncollecting_states_require_no_window(status):
    """비수집 상태에 이전 창 정보가 남아 있으면 계약 오류로 처리한다."""
    body = deepcopy(GOOD)
    body["data"]["collection_status"] = status
    with pytest.raises(ValueError):
        read_activity(json.dumps(body).encode())
    body["data"]["window"] = None
    assert read_activity(json.dumps(body).encode()).window is None


def test_initial_state_and_health_gate(app, window, fake_server):
    """연결 확인 전이나 서비스 검증 실패 시 자동 조회를 시작하지 않는다."""
    settings = fake_server[1]
    assert window.application.text() == "—"
    assert not window.activity.active
    assert settings["paths"] == []
    settings["health"]["data"]["service"] = "other"
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    assert window.status.text() == "호환되지 않는 응답"
    assert not window.activity.active
    assert settings["paths"] == ["/health"]
    settings["health"] = HEALTH
    window.check()
    wait_for(app, lambda: window.application.text() == "Google Chrome")
    assert window.activity.active


def test_automatic_transitions_and_unchanged_window(app, window, fake_server):
    """Chrome→VS Code, Word→Explorer, 동일 창을 실제 HTTP 자동 갱신으로 확인한다."""
    settings = fake_server[1]
    window.button.click()
    wait_for(app, lambda: window.application.text() == "Google Chrome")
    for application, process_name, title in [
        ("Visual Studio Code", "Code.exe", "가상 작업.py — Visual Studio Code"),
        ("Microsoft Word", "WINWORD.EXE", "가상 보고서.docx"),
        ("Windows Explorer", "explorer.exe", "가상 폴더"),
    ]:
        body = deepcopy(GOOD)
        body["data"]["window"].update(application=application, process_name=process_name,
                                       window_title=title)
        settings["body"] = body
        wait_for(app, lambda: window.application.text() == application)
        assert window.window_title.toPlainText() == title
        assert process_name in window.process.text()
    before = settings["paths"].count(ACTIVITY_PATH)
    wait_for(app, lambda: settings["paths"].count(ACTIVITY_PATH) >= before + 2)
    assert window.application.text() == "Windows Explorer"
    assert window.activity_updated_at.text() != "마지막 정상 수신: 없음"


@pytest.mark.parametrize("status,expected", [
    ("no_active_window", "대기"), ("unsupported", "수집 불가"), ("error", "감지 오류"),
])
def test_collection_state_clears_previous_window(app, window, fake_server, status, expected):
    """바탕화면·미지원 창·감지 실패 상태에 이전 제목이 남지 않게 한다."""
    window.check()
    wait_for(app, lambda: window.application.text() == "Google Chrome")
    body = deepcopy(GOOD)
    body["data"].update(collection_status=status, window=None)
    fake_server[1]["body"] = body
    wait_for(app, lambda: window.collection_status.text().startswith(expected))
    assert window.application.text() == window.process.text() == "—"
    assert window.window_title.toPlainText() == "—"


@pytest.mark.parametrize("status,body,content_type,expected", [
    (404, b"{}", "application/json", "기능 준비 중"),
    (500, b"private server detail", "application/json", "수신 실패"),
    (302, b"{}", "application/json", "수신 실패"),
    (0, b"", "application/json", "수신 중단"),
    (200, b"not json", "application/json", "호환되지 않는"),
    (200, b"{}", "text/html", "호환되지 않는"),
])
def test_failure_clears_data_and_recovers_automatically(
    app, window, fake_server, status, body, content_type, expected,
):
    """서버 오류/연결 단절 뒤 버튼 조작 없이 다음 정상 응답으로 복구한다."""
    settings = fake_server[1]
    window.check()
    wait_for(app, lambda: window.application.text() == "Google Chrome")
    settings.update(status=status, body=body, content_type=content_type)
    wait_for(app, lambda: window.collection_status.text().startswith(expected))
    assert window.application.text() == "—"
    assert window.window_title.toPlainText() == "—"
    assert "private server detail" not in window.collection_status.text()
    settings.update(status=200, body=GOOD, content_type="application/json")
    wait_for(app, lambda: window.application.text() == "Google Chrome")


def test_timeout_single_request_and_recovery(app, window, fake_server):
    """느린 요청의 중복 방지, UI 이벤트 생존, timeout 후 복구를 확인한다."""
    settings = fake_server[1]
    settings["delay"] = 0.3
    window.activity.timer.setInterval(80)
    window.check()
    wait_for(app, lambda: window.activity.reply is not None)
    reply = window.activity.reply
    window.activity.start()
    window.activity.refresh()
    assert window.activity.reply is reply
    ticks = []
    QTimer.singleShot(10, lambda: ticks.append(True))
    wait_for(app, lambda: window.collection_status.text().startswith("수신 시간 초과"))
    assert ticks
    settings["delay"] = 0
    window.activity.timer.setInterval(3000)
    wait_for(app, lambda: window.application.text() == "Google Chrome")


def test_recheck_and_close_cancel_late_responses(app, window, fake_server):
    """이전 요청 취소 뒤 새 응답만 표시하고 창 종료 시 재예약을 차단한다."""
    settings = fake_server[1]
    settings["delay"] = 0.25
    window.check()
    wait_for(app, lambda: ACTIVITY_PATH in settings["paths"])
    settings["body"] = deepcopy(GOOD)
    settings["body"]["data"]["window"]["application"] = "새 창"
    settings["delay"] = 0
    window.check()
    wait_for(app, lambda: window.application.text() == "새 창")
    # 늦게 끝난 취소 응답이 새 화면을 덮지 않는지 이벤트 루프를 계속 실행한다.
    done = []
    QTimer.singleShot(350, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert window.application.text() == "새 창"
    settings["delay"] = 0.25
    wait_for(app, lambda: window.activity.reply is not None)
    window.close()
    assert window.activity.reply is None
    assert not window.activity.timer.isActive()
    assert not window.activity.poll_timer.isActive()
    assert not window.activity.active
    paths = len(settings["paths"])
    done.clear()
    QTimer.singleShot(350, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert len(settings["paths"]) == paths


@pytest.mark.parametrize("title", ["", "<b>가상 제목</b> & 한글\n둘째 줄", "긴제목" * 500])
def test_plain_text_and_empty_or_long_title(app, window, fake_server, title):
    """제목 원문과 한글을 보존하며 HTML을 해석하거나 창 폭을 늘리지 않는다."""
    fake_server[1]["body"]["data"]["window"]["window_title"] = title
    window.check()
    wait_for(app, lambda: window.application.text() == "Google Chrome")
    assert window.window_title.toPlainText() == (title or "(제목 없음)")
    assert window.application.textFormat() == Qt.TextFormat.PlainText
    assert window.width() == 620
