import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

# Windows uses its native platform plugin; Linux CI has no display server.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.backend_client import read_version
from client.window import MainWindow

GOOD = {
    "ok": True,
    "error": None,
    "data": {
        "service": "contexttrace-backend",
        "status": "running",
        "version": "0.1.0",
        "api_version": 1,
    },
}


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout

    while not predicate():
        app.processEvents()

        if time.monotonic() >= deadline:
            pytest.fail("Qt operation timed out")

        time.sleep(0.005)

    app.processEvents()


@pytest.fixture
def fake_server():
    settings = {
        "body": json.dumps(GOOD).encode(),
        "status": 200,
        "delay": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(settings["delay"])
            self.send_response(settings["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            try:
                self.wfile.write(settings["body"])
            except (BrokenPipeError, ConnectionResetError):
                # Expected when the client cancels a delayed request.
                return

        def log_message(self, *args):
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


@pytest.mark.parametrize("version", [True, "1", 2, None])
def test_reject_incompatible_api_version(version):
    body = json.loads(json.dumps(GOOD))
    body["data"]["api_version"] = version

    with pytest.raises(ValueError):
        read_version(json.dumps(body).encode())


@pytest.mark.parametrize("body", [b"not json", b"[]", b"null", b"{}"])
def test_reject_malformed_response(body):
    with pytest.raises(ValueError):
        read_version(body)


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, json.dumps(GOOD).encode(), "연결됨"),
        (500, b"{}", "상태 확인 실패"),
        (200, b"bad json", "호환되지 않는 응답"),
        (
            200,
            json.dumps(
                {
                    **GOOD,
                    "data": {
                        **GOOD["data"],
                        "service": "other",
                    },
                }
            ).encode(),
            "호환되지 않는 응답",
        ),
    ],
)
def test_window_response(app, fake_server, status, body, expected):
    port, settings = fake_server
    settings.update(status=status, body=body)
    window = MainWindow(port)

    try:
        window.show()
        assert window.isVisible()
        assert window.status.text() == "미확인"

        window.button.click()
        assert not window.button.isEnabled()

        reply = window.backend.reply
        window.check()
        assert window.backend.reply is reply

        wait_for(app, lambda: window.button.isEnabled())

        assert window.status.text().startswith(expected)
        assert window.checked_at.text() != "마지막 확인: 없음"
    finally:
        window.close()


def test_timeout_and_close_during_request(app, fake_server):
    port, settings = fake_server
    settings["delay"] = 0.4
    window = MainWindow(port)

    try:
        window.show()
        window.backend.timer.setInterval(50)

        ticks = []
        QTimer.singleShot(10, lambda: ticks.append(True))

        window.check()
        wait_for(app, lambda: window.button.isEnabled())

        assert ticks
        assert window.status.text().startswith("시간 초과")

        window.check()
        window.close()

        assert window.backend.reply is None
        assert not window.backend.timer.isActive()
    finally:
        window.close()


def test_real_backend_failure_connection_and_recovery(app, tmp_path):
    """실제 백엔드의 연결 복구와 현재 창 및 최근 기록 조회를 확인한다."""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    window = MainWindow(port)
    process = None

    with (tmp_path / "backend.log").open("w") as log:
        try:
            window.show()
            window.check()
            wait_for(app, lambda: window.button.isEnabled())

            # Connection refusal timing can vary on Windows.
            assert window.status.text().startswith(
                ("연결 안 됨", "시간 초과")
            )

            for _ in range(2):
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "backend",
                        "--port",
                        str(port),
                    ],
                    stdout=log,
                    stderr=log,
                )

                with httpx.Client(
                    trust_env=False,
                    timeout=0.2,
                ) as client:

                    def ready():
                        if process.poll() is not None:
                            pytest.fail(
                                "Backend process exited before becoming ready."
                            )

                        try:
                            response = client.get(
                                f"http://127.0.0.1:{port}/health"
                            )
                            return response.status_code == 200
                        except httpx.TransportError:
                            return False

                    wait_for(app, ready, timeout=10)

                window.button.click()
                wait_for(app, lambda: window.button.isEnabled())
                assert window.status.text().startswith("연결됨")

                # The current activity API is implemented.
                wait_for(
                    app,
                    lambda: window.collection_status.text().startswith(
                        (
                            "감지 중",
                            "대기",
                            "수집 불가",
                            "감지 오류",
                        )
                    ),
                )

                # Recent records should load even when the list is empty.
                window.tabs.setCurrentWidget(window.recent)
                wait_for(app, lambda: window.recent.loaded)

                assert window.recent.status.text().startswith(
                    (
                        "최근 기록",
                        "저장된 작업 기록이 없습니다.",
                    )
                )

                process.terminate()
                process.wait(timeout=10)
                process = None

                window.button.click()
                wait_for(app, lambda: window.button.isEnabled())

                assert window.status.text().startswith(
                    ("연결 안 됨", "시간 초과")
                )
        finally:
            window.close()

            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)

