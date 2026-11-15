"""통합 실행의 서버 소유·포트·준비·종료 경계를 실제 Client 창과 가상 프로세스로 검증한다."""

import json
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QLockFile, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

import desktop.launcher as launcher
from client.application_window import ApplicationWindow

HEALTH = json.dumps({
    "ok": True, "error": None,
    "data": {"service": "contexttrace-backend", "api_version": 1,
             "status": "running", "version": "0.1.0"},
}).encode()


class FakeProbe(QObject):
    """실제 loopback 요청 없이 성공·전송 실패·늦은 응답을 같은 Qt 신호로 전달한다."""

    received = Signal(bytes)
    failed = Signal(str, int)

    def __init__(self, port, parent):
        """상태 조회 횟수로 중복 준비 요청과 실패 뒤 숨은 재시도를 확인한다."""
        super().__init__(parent)
        self.port = port
        self.reply = None
        self.paths = []
        self.closed = 0
        self.timer = QTimer(self)

    def get(self, path):
        """기존 JsonRequest처럼 한 번에 하나의 응답만 기다린다."""
        assert self.reply is None
        self.paths.append(path)
        self.reply = object()

    def close(self):
        """취소 이후 늦은 응답은 supervisor의 상태 경계에서 거부된다."""
        self.closed += 1
        self.reply = None

    def deliver(self, payload=HEALTH):
        """파서 전에 실제 요청 객체가 비워지는 기존 신호 순서를 따른다."""
        self.reply = None
        self.received.emit(payload)

    def reject(self, reason="network", status=0):
        """구분된 실패 사유를 전달하고 현재 요청을 종료한다."""
        self.reply = None
        self.failed.emit(reason, status)


class FakeLock:
    """사용자 임시 파일을 만들지 않고 단일 실행과 잠금 해제를 관찰한다."""

    LockError = QLockFile.LockError

    def __init__(self, path):
        """포트별 경로를 받아 다른 서버의 잠금을 조작하지 않는지 확인한다."""
        self.path = path
        self.available = True
        self.error_code = self.LockError.LockFailedError
        self.unlocks = 0
        self.attempts = []

    def setStaleLockTime(self, value):
        """실행 중 잠금을 시간 경과만으로 지우지 않는 설정을 기록한다."""
        self.stale_time = value

    def tryLock(self, timeout):
        """화면을 멈추지 않는 즉시 잠금만 허용한다."""
        self.attempts.append(timeout)
        return self.available

    def error(self):
        """중복 실행과 권한 오류를 구분한다."""
        return self.error_code

    def unlock(self):
        """획득하지 않은 다른 창의 잠금은 해제하면 안 된다."""
        self.unlocks += 1


class FakeControl:
    """소유 worker의 준비·정상 종료 신호를 파일/OS 핸들 없이 재현한다."""

    def __init__(self):
        """준비 신호 전에는 같은 포트의 health를 소유 서버로 인정하지 않는다."""
        self.name = "Local\\SyntheticStop"
        self.ready = False
        self.stops = self.closes = 0

    def is_ready(self):
        """worker가 실제 서버 준비 뒤에만 설정하는 별도 신호다."""
        return self.ready

    def request_stop(self):
        """다른 프로세스를 검색하거나 종료하지 않고 현재 worker에게만 요청한다."""
        self.stops += 1

    def close(self):
        """중복 종료에서 같은 소유 채널을 다시 닫지 않는지 확인한다."""
        self.closes += 1


class FakeProcess:
    """UI 테스트가 실제 자식이나 외부 프로그램을 실행하지 않게 한다."""

    def __init__(self):
        """종료 코드와 정상/강제 종료 응답을 시험에서 제어한다."""
        self.pid = 987654
        self.returncode = None
        self.waits = []
        self.kills = 0
        self.stubborn = False

    def poll(self):
        """프로세스가 종료됐는지 읽기만 한다."""
        return self.returncode

    def wait(self, timeout):
        """기본은 정상 종료하며 응답 없는 worker만 제한 시간 예외를 만든다."""
        self.waits.append(timeout)
        if self.stubborn and self.returncode is None:
            raise subprocess.TimeoutExpired("synthetic worker", timeout)
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def kill(self):
        """자신이 만든 가상 프로세스만 강제로 종료한다."""
        self.kills += 1
        self.returncode = -9


@pytest.fixture(scope="module")
def app():
    """기존 Client 위젯을 사용하되 실제 사용자 설정을 읽지 않는다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def make_supervisor(app, monkeypatch):
    """운영체제 잠금·자식 실행·HTTP만 바꾸고 화면과 Qt 상태 전달은 그대로 둔다."""
    monkeypatch.setattr(launcher, "QLockFile", FakeLock)
    monkeypatch.setattr(launcher, "JsonRequest", FakeProbe)
    monkeypatch.setattr(launcher, "WindowsStopSignal", FakeControl)
    processes, launches, checks, windows = [], [], [], []

    def popen(command, **kwargs):
        """명령의 역할·포트·소유 정보만 기록하고 실제 EXE를 실행하지 않는다."""
        process = FakeProcess()
        processes.append(process)
        launches.append((command, kwargs))
        return process

    monkeypatch.setattr(launcher.subprocess, "Popen", popen)

    def create(db_path=None):
        """같은 기본 포트의 실제 관리 화면과 supervisor를 만든다."""
        window = ApplicationWindow(9123)
        monkeypatch.setattr(window.management.backend, "check", lambda: checks.append(9123))
        window.show()
        supervisor = launcher.BackendSupervisor(window, 9123, db_path)
        windows.append(window)
        return window, supervisor

    yield create, processes, launches, checks
    for window in windows:
        window.close()
    app.processEvents()


def spawn(supervisor):
    """비어 있는 포트의 연결 거부 뒤에만 새 worker가 시작되는 실제 순서를 따른다."""
    supervisor.start()
    supervisor.probe.reject()
    assert supervisor.state == "starting"
    return supervisor.process, supervisor.control


def test_existing_compatible_server_is_reused_and_never_stopped(make_supervisor):
    """외부 서버 연결은 API 확인만 하며 창 종료가 외부 프로세스 종료로 이어지지 않는다."""
    create, processes, launches, checks = make_supervisor
    window, supervisor = create()
    supervisor.start()
    assert checks == [] and not window.management.button.isEnabled()
    window.management.check()
    assert checks == []
    supervisor.probe.deliver()
    assert supervisor.state == "ready_external" and checks == [9123]
    assert not supervisor.owns_backend and processes == launches == []
    window.close()
    supervisor.stop()
    assert supervisor.state == "stopped" and supervisor.lock.unlocks == 1
    assert processes == []


def test_explicit_db_does_not_silently_attach_to_unknown_existing_database(make_supervisor):
    """health에 DB 식별이 없으므로 지정 경로를 무시한 기존 서버 연결을 성공으로 표시하지 않는다."""
    create, processes, _, checks = make_supervisor
    window, supervisor = create(Path("C:/synthetic/check.db"))
    results = []
    window.management.backend.connection_changed.connect(results.append)
    supervisor.start()
    supervisor.probe.deliver()
    assert supervisor.state == "failed" and results == [False] and processes == checks == []
    assert "지정한 데이터 경로" in window.management.connection_message.text()
    window.management.check()
    window.management.button.click()
    assert checks == [] and not window.recheck_action.isEnabled()


@pytest.mark.parametrize("reason", ["http", "content_type"])
def test_occupied_or_unresponsive_service_does_not_start_another_server(make_supervisor, reason):
    """점유 포트는 다른 임의 포트나 새 서버로 조용히 우회하지 않는다."""
    create, processes, launches, checks = make_supervisor
    window, supervisor = create()
    supervisor.start()
    supervisor.probe.reject(reason, 404 if reason == "http" else 0)
    assert supervisor.state == "failed" and processes == launches == checks == []
    assert "포트" in window.management.connection_message.text()


def test_initial_timeout_can_start_worker_but_cannot_skip_port_ownership(make_supervisor):
    """Windows의 연결 거부 전 제한 시간도 시도하되 준비 이벤트 없는 health는 채택하지 않는다."""
    create, processes, _, checks = make_supervisor
    window, supervisor = create()
    supervisor.start()
    supervisor.probe.reject("timeout")
    assert supervisor.state == "starting" and len(processes) == 1 and checks == []
    supervisor.probe.deliver()
    assert supervisor.state == "starting" and checks == []
    supervisor.process.returncode = 2
    supervisor._tick()
    assert supervisor.state == "failed" and "포트" in window.management.connection_message.text()


def test_wrong_service_identity_cannot_report_connected(make_supervisor):
    """모양이 같은 JSON도 기존 API 식별자가 다르면 실패하고 새로운 수집기를 만들지 않는다."""
    create, processes, _, checks = make_supervisor
    window, supervisor = create()
    supervisor.start()
    supervisor.probe.deliver(HEALTH.replace(b"contexttrace-backend", b"other-service"))
    assert supervisor.state == "failed" and not checks and not processes
    assert "서버 버전" in window.management.connection_message.text()


def test_owned_backend_needs_worker_ready_event_and_valid_health(make_supervisor):
    """압축 해제 중 살아 있는 PID와 다른 서버의 정상 health만으로 연결하지 않는다."""
    create, processes, launches, checks = make_supervisor
    window, supervisor = create(Path("C:/가상 자료/검증.db"))
    process, control = spawn(supervisor)
    supervisor._tick()
    assert supervisor.probe.paths == ["/health"]
    supervisor.probe.deliver()
    assert supervisor.state == "starting" and checks == []
    control.ready = True
    supervisor._tick()
    assert supervisor.probe.paths == ["/health", "/health"]
    supervisor.probe.deliver()
    assert supervisor.state == "ready_owned" and checks == [9123] and len(processes) == 1
    assert supervisor.owns_backend
    command, options = launches[0]
    assert command[command.index("--port") + 1] == "9123"
    assert command[-2:] == ["--db-path", str(Path("C:/가상 자료/검증.db"))]
    assert "--backend-worker" in command and "--owner-pid" in command
    assert options["stdin"] == options["stdout"] == options["stderr"] == subprocess.DEVNULL
    assert options["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    window.close()
    assert control.stops == control.closes == 1 and process.returncode == 0
    supervisor.stop()
    assert control.stops == 1 and supervisor.lock.unlocks == 1


def test_health_from_dead_or_not_ready_owned_worker_does_not_attach(make_supervisor):
    """준비 신호가 있었어도 worker가 먼저 끝났으면 다른 포트 점유자의 health를 채택하지 않는다."""
    create, _, _, checks = make_supervisor
    _, supervisor = create()
    process, control = spawn(supervisor)
    control.ready = True
    process.returncode = 2
    supervisor.probe.deliver()
    assert supervisor.state == "starting" and checks == []
    supervisor._tick()
    assert supervisor.state == "failed" and control.stops == control.closes == 1


def test_startup_timeout_stops_only_owned_process_and_does_not_retry(make_supervisor, monkeypatch):
    """정해진 준비 시간을 넘기면 소유 서버를 정리하고 늦은 신호로 성공을 복원하지 않는다."""
    create, processes, _, checks = make_supervisor
    window, supervisor = create()
    process, control = spawn(supervisor)
    monkeypatch.setattr(launcher.time, "monotonic", lambda: supervisor._deadline + 1)
    supervisor._tick()
    assert supervisor.state == "failed" and control.stops == 1 and process.returncode == 0
    assert "시간이 초과" in window.management.connection_message.text()
    supervisor.probe.deliver()
    supervisor.probe.reject()
    supervisor.start()
    assert checks == [] and len(processes) == 1 and supervisor.state == "failed"


def test_owned_process_exit_invalidates_existing_client_state(make_supervisor):
    """연결 후 서버가 종료돼도 마지막 기록 가능 상태를 정상 연결처럼 유지하지 않는다."""
    create, _, _, checks = make_supervisor
    window, supervisor = create()
    process, control = spawn(supervisor)
    control.ready = True
    supervisor.probe.deliver()
    process.returncode = 4
    supervisor._tick()
    assert supervisor.state == "failed" and checks == [9123]
    assert not supervisor.shutdown_clean and process.kills == 0
    assert "서버가 종료" in window.management.connection_message.text()
    assert not window.management.privacy.toggle.isEnabled()


def test_duplicate_gui_does_not_unlock_or_start_a_worker(app, make_supervisor):
    """다른 화면이 잡은 잠금은 지우지 않고 중복 화면만 닫는다."""
    create, processes, launches, checks = make_supervisor
    window, supervisor = create()
    supervisor.lock.available = False
    supervisor.start()
    assert supervisor.state == "failed" and "이미 실행 중" in window.management.connection_message.text()
    app.processEvents()
    assert not window.isVisible() and supervisor.state == "stopped"
    assert supervisor.lock.unlocks == 0 and processes == launches == checks == []


def test_lock_permission_error_is_not_reported_as_another_running_gui(make_supervisor):
    """잠금 파일을 만들 수 없는 오류를 이미 실행 중이라는 안내로 잘못 설명하지 않는다."""
    create, processes, _, _ = make_supervisor
    window, supervisor = create()
    supervisor.lock.available = False
    supervisor.lock.error_code = QLockFile.LockError.PermissionError
    supervisor.start()
    assert supervisor.state == "failed" and "쓰기 권한" in window.management.connection_message.text()
    assert window.isVisible() and processes == [] and supervisor.lock.unlocks == 0


def test_spawn_failure_closes_control_without_running_a_health_handshake(make_supervisor, monkeypatch):
    """실행 파일을 시작하지 못한 경우 소유 채널을 닫고 기존 연결 성공을 만들지 않는다."""
    create, _, _, checks = make_supervisor
    window, supervisor = create()
    control = FakeControl()
    monkeypatch.setattr(launcher, "WindowsStopSignal", lambda: control)

    def fail(*_args, **_kwargs):
        """Windows의 파일/권한 오류를 실제 프로세스 실행 없이 재현한다."""
        raise OSError("synthetic launch failure")

    monkeypatch.setattr(launcher.subprocess, "Popen", fail)
    supervisor.start()
    supervisor.probe.reject()
    assert supervisor.state == "failed" and checks == []
    assert control.stops == control.closes == 1
    assert "실행 권한" in window.management.connection_message.text()


def test_stop_clears_client_connection_caches_before_worker_signal(make_supervisor, monkeypatch):
    """정상 종료 전에 유휴 HTTP 연결을 닫아 배타적으로 바인딩한 포트의 재사용을 방해하지 않는다."""
    create, _, _, _ = make_supervisor
    _, supervisor = create()
    _, control = spawn(supervisor)
    events = []
    requests = supervisor.window.findChildren(launcher._REQUEST_TYPE)
    for request in requests:
        monkeypatch.setattr(request.manager, "clearConnectionCache", lambda: events.append("cache"))
    monkeypatch.setattr(control, "request_stop", lambda: events.append("stop"))
    supervisor.stop()
    assert events == ["cache"] * len(requests) + ["stop"]


def test_unresponsive_owned_worker_uses_bounded_own_tree_fallback(make_supervisor, monkeypatch):
    """정상 종료에 응답하지 않는 소유 프로세스만 제한 시간 후 정리한다."""
    create, _, _, _ = make_supervisor
    _, supervisor = create()
    process, control = spawn(supervisor)
    process.stubborn = True
    calls = []

    def taskkill(command, **kwargs):
        """실제 taskkill을 실행하지 않고 PID·숨김 실행·범위만 확인한다."""
        calls.append((command, kwargs))
        process.returncode = -9

    monkeypatch.setattr(launcher.subprocess, "run", taskkill)
    supervisor.stop()
    assert not supervisor.shutdown_clean and process.returncode == -9
    assert control.stops == control.closes == 1
    if launcher.os.name == "nt":
        assert calls[0][0] == ["taskkill", "/PID", str(process.pid), "/T", "/F"]
        assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW
    else:
        assert calls == [] and process.kills == 1


@pytest.mark.parametrize("frozen", [False, True])
def test_worker_command_keeps_one_binary_and_literal_arguments(monkeypatch, frozen):
    """공백·한글 경로도 shell 문자열로 만들지 않고 같은 역할·소유 인자로 전달한다."""
    monkeypatch.setattr(launcher.sys, "frozen", frozen, raising=False)
    path = Path("C:/가상 자료/기록.db")
    command = launcher.worker_command(9123, "Local\\SyntheticStop", path)
    assert command[0] == launcher.sys.executable
    assert (command[1:3] == ["-m", "desktop"]) is not frozen
    assert command[-2:] == ["--db-path", str(path)]
    assert command[command.index("--owner-pid") + 1] == str(launcher.os.getpid())
    assert command.count("--port") == 1 and not any("Backend.exe" in argument for argument in command)


def test_force_stop_race_still_releases_control_and_own_lock(make_supervisor, monkeypatch):
    """강제 정리 직전 프로세스가 끝나는 경합도 이벤트 핸들과 실행 잠금을 남기지 않는다."""
    create, _, _, _ = make_supervisor
    _, supervisor = create()
    process, control = spawn(supervisor)
    process.stubborn = True

    def failed_tree_stop(*_args, **_kwargs):
        """실제 프로세스 명령을 실행하지 않고 정리 명령 실패를 전달한다."""
        raise OSError("synthetic tree cleanup race")

    def exited_before_kill():
        """kill 직전 자연 종료된 프로세스의 오류를 재현한다."""
        process.returncode = 0
        raise OSError("synthetic process already exited")

    monkeypatch.setattr(launcher.subprocess, "run", failed_tree_stop)
    monkeypatch.setattr(process, "kill", exited_before_kill)
    supervisor.stop()
    assert supervisor.state == "stopped" and not supervisor.shutdown_clean
    assert supervisor.lock.unlocks == 1 and control.stops == control.closes == 1
