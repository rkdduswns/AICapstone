"""가상 HTTP로 개인정보 UI의 요청·확인·오류를 검사한다. 실제 저장 차단 테스트는 아니다."""

import json
import os
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from client.privacy_client import normalize_processes, read_privacy
from client.window import MainWindow
from shared.privacy import PrivacyResponse, PrivacySettings, PrivacyState, RecordingStatus
from shared.protocol import HealthResponse, HealthStatus

GOOD = asdict(PrivacyResponse(PrivacyState(PrivacySettings(False, []),
                                         RecordingStatus(True, "allowed"))))


@pytest.fixture(scope="module")
def app():
    """Qt 이벤트 루프를 테스트 사이에 공유한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=4):
    """비동기 응답을 처리하며 조건 완료까지 유한 시간만 기다린다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Privacy UI timed out")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def server():
    """설정 쓰기 적용과 응답 지연을 분리해 서버 성공/Client timeout도 재현한다."""
    settings = {"state": deepcopy(GOOD), "status": 200, "delay": 0, "body": None,
                "put_status": 200, "put_delay": 0, "apply": True, "writes": [], "gets": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """기록/감지 API는 미구현이고 보호 상태만 가상으로 제공한다."""
            if self.path == "/health":
                self.send_json(asdict(HealthResponse(HealthStatus("test"))), 200, 0)
            elif self.path == "/privacy":
                settings["gets"] += 1
                self.send_json(settings["body"] or settings["state"],
                               settings["status"], settings["delay"])
            else:
                self.send_error(404)

        def do_PUT(self):
            """전송된 필드와 전용 헤더를 기록하고 해당 필드만 가상 설정에 반영한다."""
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            settings["writes"].append((self.path, body, self.headers.get("X-ContextTrace-Client")))
            if settings["apply"] and settings["put_status"] == 200:
                data = settings["state"]["data"]
                data["settings"].update(body)
                reason = "paused" if data["settings"]["paused"] else "allowed"
                data["recording"] = {"allowed": reason == "allowed", "reason": reason}
            self.send_json(settings["state"], settings["put_status"], settings["put_delay"])

        def send_json(self, body, status, delay):
            """요청 시점 스냅샷을 지연 전송하며 취소된 연결은 정상 정리한다."""
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            time.sleep(delay)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # 취소/timeout 뒤 닫힌 Client 연결에 쓰는 경우다.

        def log_message(self, *args):
            """설정과 가상 요청을 로그에 남기지 않는다."""
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
    """전체 화면에서 상태 표시와 탭 밖 제어를 검사하고 종료 요청을 정리한다."""
    window = MainWindow(server[0])
    window.privacy.client.poll_timer.setInterval(10000)
    window.show()
    try:
        yield window
    finally:
        window.close()
        app.processEvents()


def connect(app, window):
    """연결 확인과 최초 보호 상태 응답을 기다린다."""
    window.check()
    wait_for(app, lambda: window.privacy.state is not None)
    return window.privacy


@pytest.mark.parametrize("reason", [
    "allowed", "paused", "blocked_program", "sensitive_content",
    "no_active_window", "unsupported", "error",
])
def test_valid_recording_reasons(reason):
    """저장 허용과 차단 사유를 감지 상태와 별개로 읽는다."""
    body = deepcopy(GOOD)
    body["data"]["settings"] = {"paused": reason == "paused", "blocked_processes": ["sample.exe"]}
    body["data"]["recording"] = {"allowed": reason == "allowed", "reason": reason}
    assert read_privacy(json.dumps(body).encode()).recording.reason == reason


@pytest.mark.parametrize("path,value", [
    (("ok",), 1), (("error",), {}), (("data",), None),
    (("data", "service"), "other"), (("data", "api_version"), True),
    (("data", "settings", "paused"), 0), (("data", "settings", "paused"), True),
    (("data", "settings", "blocked_processes"), "chrome.exe"),
    (("data", "settings", "blocked_processes"), ["CHROME.EXE"]),
    (("data", "settings", "blocked_processes"), ["a.exe", "a.exe"]),
    (("data", "recording", "allowed"), 1), (("data", "recording", "allowed"), False),
    (("data", "recording", "reason"), "unknown"), (("data", "recording", "reason"), []),
])
def test_invalid_or_inconsistent_state(path, value):
    """잘못된 타입·서비스·모순된 상태를 보호 성공으로 표시하지 않는다."""
    body = deepcopy(GOOD)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_privacy(json.dumps(body).encode())


@pytest.mark.parametrize("name", ["chrome", "*.exe", "C:\\app.exe", "a/b.exe", ".exe", "a\x00.exe"])
def test_invalid_process_name(name):
    """경로·패턴·제어 문자와 실행 파일명이 아닌 입력을 거부한다."""
    with pytest.raises(ValueError):
        normalize_processes([name])


def test_process_normalization_and_limit():
    """목록 중복/대소문자/빈 목록과 개수 제한을 일관되게 처리한다."""
    assert normalize_processes([" CHROME.EXE ", "chrome.exe", "가상 프로그램.exe"]) == [
        "chrome.exe", "가상 프로그램.exe"]
    assert normalize_processes([]) == []
    with pytest.raises(ValueError):
        normalize_processes([f"a{i}.exe" for i in range(101)])


def test_pause_resume_and_independent_draft(app, window, server):
    """서버 확인 전 상태를 반전하지 않고 일시정지 요청에 입력 중 목록을 섞지 않는다."""
    privacy = connect(app, window)
    assert privacy.toggle.isVisible()  # 현재 작업 탭에서도 일시정지할 수 있다.
    privacy.editor.setPlainText("draft.exe")
    server[1]["put_delay"] = 0.15
    privacy.toggle.click()
    privacy.toggle.click()
    assert privacy.state is None and not privacy.toggle.isEnabled()
    assert "요청 중" in privacy.summary.text()
    wait_for(app, lambda: privacy.state is not None)
    assert privacy.state.settings.paused and privacy.toggle.text() == "기록 재개"
    assert privacy.editor.toPlainText() == "draft.exe" and privacy.dirty
    assert server[1]["writes"] == [("/privacy/paused", {"paused": True}, "desktop")]
    privacy.toggle.click()
    wait_for(app, lambda: privacy.state is not None)
    assert not privacy.state.settings.paused


def test_draft_polling_apply_and_clear(app, window, server):
    """폴링은 초안을 보존하고 목록 적용/전체 해제는 확인된 응답으로만 반영한다."""
    privacy = connect(app, window)
    privacy.editor.setPlainText(" CHROME.EXE \nchrome.exe\n가상.exe")
    count = server[1]["gets"]
    privacy.client.refresh()
    wait_for(app, lambda: server[1]["gets"] > count and privacy.client.reply is None)
    assert privacy.editor.toPlainText().startswith(" CHROME")
    privacy.apply_button.click()
    wait_for(app, lambda: privacy.state is not None)
    assert privacy.editor.toPlainText() == "chrome.exe\n가상.exe"
    assert not privacy.dirty
    assert server[1]["writes"][0][:2] == (
        "/privacy/blocked-processes", {"blocked_processes": ["chrome.exe", "가상.exe"]})
    privacy.editor.setPlainText("bad/path.exe")
    privacy.apply_button.click()
    assert privacy.validation.text() and len(server[1]["writes"]) == 1
    privacy.reset_button.click()
    assert privacy.editor.toPlainText() == "chrome.exe\n가상.exe"
    privacy.editor.clear()
    privacy.apply_button.click()
    wait_for(app, lambda: privacy.state is not None)
    assert privacy.state.settings.blocked_processes == []


@pytest.mark.parametrize("status,body", [(404, None), (500, None), (200, b"bad json")])
def test_read_failure_clears_status_and_recovers(app, window, server, status, body):
    """구형 Backend/전송 오류에서 보호 중이라고 주장하지 않고 초안과 수동 복구를 지원한다."""
    privacy = connect(app, window)
    privacy.editor.setPlainText("draft.exe")
    server[1].update(status=status, body=body)
    privacy.client.refresh()
    wait_for(app, lambda: privacy.state is None)
    assert "미확인" in privacy.summary.text() and not privacy.toggle.isEnabled()
    assert privacy.editor.toPlainText() == "draft.exe"
    server[1].update(status=200, body=None)
    privacy.refresh_button.click()
    wait_for(app, lambda: privacy.state is not None)
    assert privacy.dirty


def test_write_timeout_does_not_retry_and_reconciles(app, window, server):
    """서버가 적용했어도 응답을 못 받으면 미확인으로 표시하고 GET으로만 복구한다."""
    privacy = connect(app, window)
    privacy.client.timer.setInterval(60)
    server[1]["put_delay"] = 0.2
    privacy.toggle.click()
    wait_for(app, lambda: "적용 여부 미확인" in privacy.notice.text())
    assert privacy.state is None and not privacy.toggle.isEnabled()
    privacy.client.timer.setInterval(3000)
    privacy.refresh_button.click()
    wait_for(app, lambda: privacy.state is not None)
    assert privacy.state.settings.paused and len(server[1]["writes"]) == 1


def test_write_must_echo_applied_value(app, window, server):
    """정상 HTTP라도 요청한 필드가 반영되지 않았으면 성공으로 처리하지 않는다."""
    privacy = connect(app, window)
    server[1]["apply"] = False
    privacy.toggle.click()
    wait_for(app, lambda: "적용 여부 미확인" in privacy.notice.text())
    assert privacy.state is None and "호환되지 않는" in privacy.notice.text()


def test_recheck_and_close_cancel_late_privacy(app, window, server):
    """이전 연결의 지연 응답과 종료 후 콜백이 보호 상태를 복원하지 못하게 한다."""
    privacy = connect(app, window)
    server[1]["delay"] = 0.2
    count = server[1]["gets"]
    privacy.client.refresh()
    wait_for(app, lambda: server[1]["gets"] > count)
    server[1].update(delay=0, status=404)
    window.check()
    wait_for(app, lambda: "기능 준비 중" in privacy.notice.text())
    assert privacy.state is None
    window.close()
    assert privacy.client.reply is None and not privacy.client.poll_timer.isActive()
    assert not privacy.toggle.isEnabled()
