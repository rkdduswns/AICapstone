"""별도 Backend 프로세스를 재시작하여 커밋된 보호 설정의 복원을 검증한다."""

import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx
import pytest

from backend.activity_store import ActivityStore
from backend.privacy_settings import StoredPrivacySettings

HEADERS = {"X-ContextTrace-Client": "desktop"}


@contextmanager
def running_backend(db_path, log_path):
    """지정한 검증 DB로 실제 CLI를 실행하고 정상 준비 후 HTTP 연결을 제공한다."""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "backend", "--port", str(port), "--db-path", str(db_path)],
            stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=1) as client:
                deadline = time.monotonic() + 15
                while True:
                    assert process.poll() is None, "Backend가 준비 전에 종료됐습니다."
                    try:
                        response = client.get("/health")
                        assert response.status_code == 200
                        break
                    except httpx.TransportError:
                        if time.monotonic() >= deadline:
                            pytest.fail("Backend가 제한 시간 안에 준비되지 않았습니다.")
                        time.sleep(0.05)
                yield client
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def test_committed_settings_survive_actual_process_restart(tmp_path):
    """강제 종료 뒤 새 프로세스도 수집 전에 같은 DB의 일시정지·차단·복사 설정을 복원한다."""
    db_path = tmp_path / "한글 검증 자료" / "activity.db"
    store = ActivityStore(db_path)
    defaults = StoredPrivacySettings(paused=False, blocked_processes=[], clipboard_enabled=False)
    # 실제 OS의 개인 작업은 읽지 않도록 첫 실행 이전부터 일시정지를 저장한다.
    store.update_privacy_settings({"paused": True}, defaults)

    with running_backend(db_path, tmp_path / "first.log") as client:
        assert client.get("/activity/current").json()["data"]["collection_status"] == "paused"
        response = client.put(
            "/privacy/blocked-processes", headers=HEADERS,
            json={"blocked_processes": ["chrome.exe", "winword.exe"]},
        )
        assert response.status_code == 200
        response = client.put(
            "/privacy/clipboard", headers=HEADERS, json={"clipboard_enabled": True},
        )
        assert response.status_code == 200
        expected = response.json()["data"]["settings"]

    with running_backend(db_path, tmp_path / "second.log") as client:
        assert client.get("/privacy").json()["data"]["settings"] == expected
        assert client.get("/activity/current").json()["data"]["collection_status"] == "paused"

    reopened = ActivityStore(db_path)
    assert reopened.get_recent_records() == []
    assert reopened.get_recent_clipboard_records() == []
