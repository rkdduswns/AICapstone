"""Client 진단 옵션이 실제 QtNetwork 결과로 성공/실패를 쓰고 종료하는지 확인한다."""

import io
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from docx import Document


@pytest.mark.parametrize("available", [True, False])
@pytest.mark.parametrize("reading", [False, True])
def test_client_diagnostic_exit_and_json(tmp_path, available, reading):
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
                    if reading:
                        # 임시 DB에 명시적으로 올린 두 문서만 실제 Client HTTP 경로로 읽는다.
                        for index in range(2):
                            document = Document()
                            document.add_paragraph(f"가상 읽기 진단 {index} · 반복 본문 반복")
                            content = io.BytesIO()
                            document.save(content)
                            response = client.post(
                                f"http://127.0.0.1:{port}/documents",
                                files={"file": (f"sample{index}.docx", content.getvalue(),
                                                 "application/octet-stream")},
                                headers={"X-ContextTrace-Client": "desktop"},
                            )
                            assert response.status_code == 201
                        paused = client.put(
                            f"http://127.0.0.1:{port}/privacy/paused", json={"paused": True},
                            headers={"X-ContextTrace-Client": "desktop"},
                        )
                        assert paused.status_code == 200
            result_path = tmp_path / "diagnostic.json"
            arguments = [sys.executable, "-m", "client", "--port", str(port),
                         "--smoke-test-result", str(result_path)]
            if reading:
                arguments.append("--smoke-test-reading")
            result = subprocess.run(arguments, capture_output=True,
                                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, timeout=15)
            assert result.returncode == (0 if available else 1), result.stderr.decode(errors="replace")
            diagnostic = json.loads(result_path.read_text(encoding="utf-8"))
            if reading:
                checks = diagnostic.pop("checks")
                assert set(checks) == {"health_confirmed", "activity_confirmed", "privacy_confirmed",
                                       "document_list", "document_find", "document_source_none",
                                       "management_return"}
                assert all(type(value) is bool for value in checks.values())
                assert all(checks.values()) is available
            assert diagnostic == {
                "ok": available, "frozen": False, "platform": "offscreen"}
        finally:
            if backend is not None:
                backend.terminate()
                try:
                    backend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait(timeout=5)
