"""Client 진단 옵션이 실제 QtNetwork 결과로 성공/실패를 쓰고 종료하는지 확인한다."""

import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.parametrize("available", [True, False])
def test_client_diagnostic_exit_and_json(tmp_path, available):
    """정상 Backend와 연결 거부를 구분하며 소스 실행을 frozen 실행으로 보고하지 않는다."""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    backend = None
    with (tmp_path / "backend.log").open("w") as log:
        if available:
            backend = subprocess.Popen([sys.executable, "-m", "backend", "--port", str(port),
                                        "--db-path", str(tmp_path / "test.db")],
                                       stdout=log, stderr=log)
        try:
            if backend is not None:
                with httpx.Client(trust_env=False, timeout=0.5) as client:
                    deadline = time.monotonic() + 10
                    while True:
                        assert backend.poll() is None
                        try:
                            assert client.get(f"http://127.0.0.1:{port}/health").status_code == 200
                            break
                        except httpx.TransportError:
                            assert time.monotonic() < deadline
                            time.sleep(0.05)
            result_path = tmp_path / "diagnostic.json"
            result = subprocess.run([sys.executable, "-m", "client", "--port", str(port),
                                     "--smoke-test-result", str(result_path)], capture_output=True,
                                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, timeout=15)
            assert result.returncode == (0 if available else 1), result.stderr.decode(errors="replace")
            assert json.loads(result_path.read_text(encoding="utf-8")) == {
                "ok": available, "frozen": False, "platform": "offscreen"}
        finally:
            if backend is not None:
                backend.terminate()
                try:
                    backend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait(timeout=5)
