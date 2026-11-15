"""단일 앱의 실제 UI·worker 프로세스와 외부 서버 경계를 격리된 DB로 검증한다."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from desktop.windows_control import WindowsStopSignal

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 단일 앱 수명 검증")


def free_port():
    """이 테스트의 loopback 포트만 선택한다."""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def wait_for(condition, timeout=35):
    """프로세스·파일·포트의 실제 변화만 제한된 시간 안에서 기다린다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.03)
    raise AssertionError("단일 앱 수명 검증 시간 초과")


def closed(port):
    """정상 종료와 부모 충돌 후 실제 listener가 없어졌는지 확인한다."""
    with socket.socket() as connection:
        connection.settimeout(0.1)
        return connection.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture
def processes(tmp_path):
    """자신이 만든 프로세스와 제어 신호만 정리하고 사용자 서버에는 접근하지 않는다."""
    running, controls, logs = [], [], []

    def start(arguments, label):
        log = (tmp_path / f"{label}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen([sys.executable, "-m", "desktop", *arguments],
                                   stdout=log, stderr=log,
                                   env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                                        "PYTHONIOENCODING": "utf-8"},
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        running.append(process)
        return process

    def worker(port, database):
        control = WindowsStopSignal()
        controls.append(control)
        process = start(["--backend-worker", "--port", str(port), "--db-path", str(database),
                         "--owner-pid", str(os.getpid()), "--stop-event", control.name], "worker")
        wait_for(lambda: control.is_ready() or process.poll() is not None)
        assert process.poll() is None and control.is_ready()
        return process

    def diagnostic(port, label, database=None, hold=0):
        path = tmp_path / f"{label}.json"
        arguments = ["--port", str(port), "--smoke-test-result", str(path)]
        if database is not None:
            arguments += ["--db-path", str(database)]
        if hold:
            arguments += ["--smoke-test-hold-ms", str(hold)]
        process = start(arguments, label)
        wait_for(lambda: (path.exists() and path.stat().st_size > 0) or process.poll() is not None)
        assert path.exists(), (tmp_path / f"{label}.log").read_text(encoding="utf-8")
        return process, json.loads(path.read_text(encoding="utf-8"))

    yield worker, diagnostic
    for control in controls:
        control.request_stop()
    for process in running:
        if process.poll() is None:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=5)
    for control in controls:
        control.close()
    for log in logs:
        log.close()


def test_managed_app_starts_and_stops_same_port_without_separate_server(tmp_path, processes):
    """앱 실행 한 번으로 DB와 서버를 준비하고 종료 뒤 같은 포트로 다시 실행한다."""
    _, diagnostic = processes
    port, database = free_port(), tmp_path / "자동 시작.db"
    for index in range(2):
        process, result = diagnostic(port, f"managed-{index}", database)
        assert process.wait(timeout=15) == 0
        assert result == {"ok": True, "frozen": False, "platform": "offscreen"}
        assert database.exists()
        wait_for(lambda: closed(port), timeout=10)


@pytest.mark.parametrize("explicit_path", [False, True])
def test_existing_server_is_preserved_and_explicit_database_is_not_ignored(tmp_path, processes,
                                                                          explicit_path):
    """호환 외부 서버는 재사용하되 DB를 지정한 실행은 다른 서버에 조용히 연결하지 않는다."""
    worker, diagnostic = processes
    port = free_port()
    server = worker(port, tmp_path / "외부 서버.db")
    different = tmp_path / "연결하면 안 되는 DB.db"
    process, result = diagnostic(port, "external", different if explicit_path else None)
    assert process.wait(timeout=15) == (1 if explicit_path else 0)
    assert result["ok"] is (not explicit_path) and server.poll() is None
    with httpx.Client(trust_env=False, timeout=1) as client:
        assert client.get(f"http://127.0.0.1:{port}/health").status_code == 200
    assert not different.exists()


def test_wrong_service_port_does_not_create_database_or_stop_listener(tmp_path, processes):
    """다른 서비스의 포트에서는 원치 않는 DB 생성·다른 포트 우회·외부 종료를 하지 않는다."""
    class Handler(BaseHTTPRequestHandler):
        """호환되지 않는 health 응답만 반환한다."""

        def do_GET(self):
            body = b'{"ok":true,"data":{"service":"unrelated"},"error":null}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            """가상 서버의 요청은 사용자 로그에 기록하지 않는다."""

    _, diagnostic = processes
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        database = tmp_path / "만들면 안 되는 DB.db"
        process, result = diagnostic(server.server_port, "wrong", database)
        assert process.wait(timeout=15) == 1 and result["ok"] is False
        assert not database.exists() and not closed(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_duplicate_gui_is_rejected_and_owner_crash_releases_backend(tmp_path, processes):
    """둘째 창이 서버 소유권을 가져가지 않고 첫째 창 충돌 뒤에도 수집 서버가 남지 않는다."""
    _, diagnostic = processes
    port = free_port()
    first, result = diagnostic(port, "first", tmp_path / "충돌 검증.db", hold=30_000)
    owner_pid = result["process_id"]
    assert result["ok"] is True and type(owner_pid) is int and owner_pid > 0
    assert owner_pid != os.getpid()  # venv/onefile 부모와 실제 GUI PID는 다를 수 있다.
    second, rejected = diagnostic(port, "duplicate")
    assert second.wait(timeout=15) == 1 and rejected["ok"] is False
    assert first.poll() is None and not closed(port)
    os.kill(owner_pid, signal.SIGTERM)
    first.wait(timeout=10)
    wait_for(lambda: closed(port), timeout=10)
