"""Exercise the installed entrypoint and real loopback HTTP, not an ASGI mock."""

import signal
import socket
import subprocess
import sys
import time

import httpx
import pytest


def run_backend(*args):
    return subprocess.run(
        [sys.executable, "-m", "backend", *args], capture_output=True, text=True, timeout=10
    )


@pytest.mark.parametrize("port", ["0", "65536", "abc", "-1"])
def test_invalid_port(port):
    result = run_backend("--port", port)
    assert result.returncode == 2
    assert "1 to 65535" in result.stderr


def test_port_conflict():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        result = run_backend("--port", str(occupied.getsockname()[1]))
    assert result.returncode != 0
    assert "bind" in result.stderr.lower()


def test_standalone_http_and_shutdown(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    # The short gap between reservation and child bind is unavoidable for this CLI test.
    with (tmp_path / "server.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "backend", "--port", str(port)], stdout=log, stderr=log
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}",
                              trust_env=False, timeout=0.5) as client:
                deadline = time.monotonic() + 10
                while True:
                    assert process.poll() is None, "backend exited before readiness"
                    try:
                        response = client.get("/health")
                        break
                    except httpx.TransportError:
                        if time.monotonic() >= deadline:
                            pytest.fail("backend did not become ready within 10 seconds")
                        time.sleep(0.05)
                assert response.status_code == 200
                assert response.json()["data"]["service"] == "contexttrace-backend"
                assert client.post("/health").status_code == 405
                assert client.get("/missing").status_code == 404
                assert client.get("/health").json()["ok"] is True
            if sys.platform != "win32":
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=10)
                log.flush()
                log.seek(0)
                assert "Application shutdown complete" in log.read()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
