"""실제 Windows 소유 이벤트로 worker의 정상 종료·부모 충돌·시작 실패 경계를 검증한다."""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import httpx
import pytest

import desktop.backend_worker as worker_module
import desktop.windows_control as control_module
from desktop.backend_worker import _worker_streams
from desktop.windows_control import WindowsStopSignal, WorkerLifetime, _kernel32

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 소유 프로세스 제어 검증")
ROOT = Path(__file__).resolve().parents[1]


def source_environment():
    """별도 소스 프로세스도 현재 작업본의 모듈만 사용하고 사용자 프록시는 사용하지 않는다."""
    return {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8"}


def free_port():
    """외부 서비스의 고정 포트를 쓰지 않고 이번 시험용 loopback 포트를 고른다."""
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def wait_until(predicate, timeout=12):
    """짧게 양보하며 프로세스·소켓 상태를 확인하고 시간 초과를 명시적으로 실패한다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "worker 상태 확인 시간 초과"
        time.sleep(0.03)


def port_closed(port):
    """포트 바인딩 재사용 정책과 분리하여 실제 listener가 남지 않았는지 확인한다."""
    with socket.socket() as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture
def workers():
    """시험이 직접 시작한 프로세스만 종료하고 각 실행의 제어 핸들을 회수한다."""
    launched = []

    def start(db_path, *, port=None, owner_pid=None, signal=None, event_name=None):
        """일반 CLI 역할 분기를 거쳐 같은 source worker를 실행한다."""
        control = signal or WindowsStopSignal()
        port = port or free_port()
        command = [sys.executable, "-m", "desktop", "--backend-worker", "--port", str(port),
                   "--owner-pid", str(owner_pid if owner_pid is not None else os.getpid()),
                   "--stop-event", event_name or control.name, "--db-path", str(db_path)]
        process = subprocess.Popen(command, env=source_environment(), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        launched.append((process, control))
        return process, control, port

    yield start
    for process, control in launched:
        if process.poll() is None:
            control.request_stop()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        control.close()


def healthy(client, process, control, port):
    """살아 있는 본인 worker의 준비 이벤트와 실제 health 응답을 함께 요구한다."""
    assert process.poll() is None, f"worker가 준비 전에 종료됐습니다: {process.returncode}"
    if not control.is_ready():
        return False
    try:
        response = client.get(f"http://127.0.0.1:{port}/health")
    except httpx.TransportError:
        return False
    return response.status_code == 200 and response.json()["data"]["service"] == "contexttrace-backend"


def test_graceful_owned_worker_shutdown_preserves_settings_and_releases_port(tmp_path, workers):
    """종료 신호가 lifespan을 거쳐 끝나고 같은 DB·포트로 보호 설정을 복원한다."""
    database = tmp_path / "가상 검증.db"
    process, control, port = workers(database)
    assert not control.is_ready()
    with httpx.Client(trust_env=False, timeout=0.4) as client:
        wait_until(lambda: healthy(client, process, control, port))
        response = client.put(f"http://127.0.0.1:{port}/privacy/paused", json={"paused": True},
                              headers={"X-ContextTrace-Client": "desktop"})
        assert response.status_code == 200
    control.request_stop()
    assert process.wait(timeout=8) == 0
    assert not control.is_ready()
    wait_until(lambda: port_closed(port))
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    second, second_control, _ = workers(database, port=port)
    with httpx.Client(trust_env=False, timeout=0.4) as client:
        wait_until(lambda: healthy(client, second, second_control, port))
        assert client.get(f"http://127.0.0.1:{port}/privacy").json()["data"]["settings"]["paused"] is True


def test_busy_port_never_creates_database_or_publishes_ready(tmp_path, workers):
    """이미 점유된 listener는 건드리지 않고 DB 초기화 이전에 실패한다."""
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        database = tmp_path / "만들면 안 됨.db"
        process, control, _ = workers(database, port=port)
        assert process.wait(timeout=8) == 2
        assert not database.exists() and not control.is_ready()
        assert not port_closed(port)


@pytest.mark.parametrize("invalid", ["missing-event", "stopped", "dead-owner"])
def test_invalid_or_lost_ownership_fails_before_database(tmp_path, workers, invalid):
    """소유자나 제어 채널을 확인하지 못한 프로세스는 데이터를 만들거나 수집하지 않는다."""
    signal = WindowsStopSignal()
    event_name = None
    owner_pid = None
    owner = None
    if invalid == "missing-event":
        event_name = signal.name + "-missing"
    elif invalid == "stopped":
        signal.request_stop()
    else:
        owner = subprocess.Popen([sys.executable, "-c", "pass"], creationflags=subprocess.CREATE_NO_WINDOW)
        owner.wait(timeout=5)
        owner_pid = owner.pid
    database = tmp_path / "소유자 없는 검증.db"
    process, control, _ = workers(database, signal=signal, owner_pid=owner_pid, event_name=event_name)
    assert process.wait(timeout=8) == 3
    assert not database.exists() and not control.is_ready()


def test_windowed_worker_streams_are_usable_and_restored(monkeypatch):
    """windowed 런타임의 None 출력을 준비하고 사용한 버림 스트림만 회수한다."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    with _worker_streams():
        output, error = sys.stdout, sys.stderr
        output.write("가상 출력")
        error.write("가상 오류")
        assert not output.closed and not error.closed
    assert sys.stdout is None and sys.stderr is None
    assert output.closed and error.closed


def test_closed_parent_signal_is_idempotent():
    """이미 회수한 부모 이벤트를 다시 닫거나 종료 요청해도 다른 핸들을 건드리지 않는다."""
    control = WindowsStopSignal()
    control.close()
    control.close()
    control.request_stop()
    assert not control.is_ready()


@pytest.mark.parametrize("owner_pid", [True, 0, -1, 2**32])
def test_invalid_owner_pid_cannot_wrap_or_open_control(tmp_path, monkeypatch, owner_pid):
    """DWORD 범위를 벗어난 PID나 불리언은 Windows 핸들 열기와 DB 초기화 전에 거부한다."""
    database = tmp_path / "invalid-owner.db"
    monkeypatch.setattr(control_module, "_kernel32", lambda:
                        pytest.fail("잘못된 PID로 Windows 핸들을 열면 안 됩니다."))
    with pytest.raises(OSError):
        WorkerLifetime(owner_pid, "Local\\GangSearchStop-synthetic", lambda: None)
    monkeypatch.setattr(worker_module, "WorkerLifetime", lambda *_args:
                        pytest.fail("잘못된 PID로 worker 수명 제어를 만들면 안 됩니다."))
    assert worker_module.run_worker(8765, database, owner_pid, "invalid") == 3
    assert not database.exists()


_OWNER_PROGRAM = """
import json, os, subprocess, sys, time
from pathlib import Path
from desktop.windows_control import WindowsStopSignal
control = WindowsStopSignal()
process = subprocess.Popen([
    sys.executable, '-m', 'desktop', '--backend-worker', '--port', sys.argv[3],
    '--owner-pid', str(os.getpid()), '--stop-event', control.name, '--db-path', sys.argv[2],
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
Path(sys.argv[1]).write_text(json.dumps({'pid': process.pid}), encoding='utf-8')
while True:
    time.sleep(0.1)
"""


def test_abrupt_owner_death_cannot_leave_collection_worker(tmp_path):
    """부모를 강제 종료한 경우에도 실제 worker 프로세스와 listener가 남지 않는다."""
    metadata, database = tmp_path / "owner.json", tmp_path / "orphan.db"
    port = free_port()
    owner = subprocess.Popen([sys.executable, "-c", _OWNER_PROGRAM, str(metadata), str(database), str(port)],
                             env=source_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    library = _kernel32()
    worker_handle = None
    try:
        wait_until(metadata.exists)
        worker_pid = json.loads(metadata.read_text(encoding="utf-8"))["pid"]
        # 열어 둔 핸들은 PID 재사용과 분리된 이번 시험의 실제 자식만 가리킨다.
        worker_handle = library.OpenProcess(0x00100000 | 0x0001, False, worker_pid)
        assert worker_handle
        with httpx.Client(trust_env=False, timeout=0.4) as client:
            def ready():
                try:
                    return client.get(f"http://127.0.0.1:{port}/health").status_code == 200
                except httpx.TransportError:
                    return False
            wait_until(ready)
        owner.terminate()
        owner.wait(timeout=5)
        assert library.WaitForSingleObject(worker_handle, 5_000) == 0
        wait_until(lambda: port_closed(port), timeout=5)
    finally:
        if owner.poll() is None:
            owner.terminate()
            owner.wait(timeout=5)
        if worker_handle:
            if library.WaitForSingleObject(worker_handle, 0) != 0:
                library.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                library.TerminateProcess.restype = wintypes.BOOL
                library.TerminateProcess(worker_handle, 9)
                library.WaitForSingleObject(worker_handle, 5_000)
            library.CloseHandle(worker_handle)
