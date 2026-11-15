"""단일 실행 파일의 화면과 소유 Backend 프로세스 수명을 비동기로 연결한다."""

import getpass
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QEventLoop,
    QLockFile,
    QObject,
    QStandardPaths,
    QTimer,
)
from PySide6.QtWidgets import QApplication

from client.backend_client import read_version
from client.json_request import JsonRequest
from desktop.windows_control import WindowsStopSignal

_REQUEST_TYPE = JsonRequest


def _lock_path(port: int) -> str:
    """같은 사용자·포트의 화면만 중복 실행을 막고 작업 자료나 표시 설정은 저장하지 않는다."""
    user = hashlib.sha256(getpass.getuser().encode("utf-8")).hexdigest()[:16]
    directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    return str(Path(directory) / f"gangsearch-desktop-{user}-{port}.lock")


def worker_command(port: int, stop_event: str, db_path: Path | None = None) -> list[str]:
    """배포본은 같은 EXE의 worker 역할, 소스 실행은 같은 Python의 desktop 모듈을 쓴다."""
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command += ["-m", "desktop"]
    command += ["--backend-worker", "--port", str(port), "--owner-pid", str(os.getpid()),
                "--stop-event", stop_event]
    if db_path is not None:
        command += ["--db-path", str(db_path)]
    return command


class BackendSupervisor(QObject):
    """기존 서비스는 조회만 하고 직접 시작한 프로세스만 정상 종료·강제 정리한다."""

    def __init__(self, window, port: int, db_path: Path | None = None) -> None:
        """화면을 먼저 표시한 뒤 준비 상태를 확인하며 창 종료와 중복 실행을 감시한다."""
        super().__init__(window)
        self.window = window
        self.port = port
        self.db_path = db_path
        self.state = "new"
        self.process: subprocess.Popen | None = None
        self.control: WindowsStopSignal | None = None
        self.shutdown_clean = True
        self._locked = False
        self._deadline = 0.0
        self._original_check = window.management.check
        self.lock = QLockFile(_lock_path(port))
        self.lock.setStaleLockTime(0)
        self.probe = JsonRequest(port, self)
        self.probe.timer.setInterval(1000)
        self.probe.received.connect(self._health_received)
        self.probe.failed.connect(self._health_failed)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(250)
        self.poll_timer.timeout.connect(self._tick)
        window.installEventFilter(self)
        application = QApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.stop)
        # F5와 메뉴도 준비 전에는 우회 연결을 만들지 않는다. 버튼의 기존 슬롯도 같은 경계로 모은다.
        window.management.check = self._request_check
        window.management.button.clicked.disconnect(self._original_check)
        window.management.button.clicked.connect(self._request_check)

    @property
    def owns_backend(self) -> bool:
        """외부 서버를 프로세스 정리 대상으로 오인하지 않도록 소유 여부를 노출한다."""
        return self.process is not None

    def start(self) -> None:
        """중복 화면을 차단하고 현재 포트의 서비스부터 읽기 전용으로 확인한다."""
        if self.state != "new":
            return
        if not self.lock.tryLock(0):
            if self.lock.error() == QLockFile.LockError.LockFailedError:
                self._fail("이미 실행 중입니다. 열려 있는 강써치 창을 사용해 주세요.")
                QTimer.singleShot(0, self.window.close)
            else:
                self._fail("실행 상태를 확인할 수 없습니다. 임시 폴더의 쓰기 권한을 확인해 주세요.")
            return
        self._locked = True
        self.state = "probing"
        self._show_status("서버 확인 중", "실행 중인 서버가 있는지 확인하고 있습니다.", busy=True)
        self.probe.get("/health")

    def _request_check(self, _checked: bool = False) -> None:
        """시작·실패 중 수동 연결이 명시한 DB나 서버 소유 검증을 건너뛰지 못하게 한다."""
        if self.state == "ready_external":
            self._original_check()
        elif self.state == "ready_owned":
            if (self.process is not None and self.process.poll() is None
                    and self.control is not None and self.control.is_ready()):
                self._original_check()
            else:
                self._fail("서버가 종료되었습니다. 강써치를 다시 실행해 주세요.")

    def _health_received(self, payload: bytes) -> None:
        """같은 API의 엄격한 식별 검증을 사용하고 준비 신호가 없는 worker는 신뢰하지 않는다."""
        if self.state not in {"probing", "starting"}:
            return
        try:
            read_version(payload)
        except (ValueError, UnicodeDecodeError):
            self._fail("연결 포트를 다른 프로그램이 사용 중이거나 서버 버전이 맞지 않습니다.")
            return
        if self.state == "probing":
            if self.db_path is not None:
                self._fail("이 포트에 이미 서버가 실행 중입니다. 지정한 데이터 경로를 사용하려면 "
                           "기존 서버를 종료하거나 다른 포트로 다시 실행해 주세요.")
                return
            self._ready(owned=False)
        elif (self.process is not None and self.process.poll() is None
              and self.control is not None and self.control.is_ready()):
            self._ready(owned=True)

    def _health_failed(self, reason: str, _status: int) -> None:
        """비어 있는 포트에서만 시작을 시도하고 점유·비호환 응답을 임의 포트로 우회하지 않는다."""
        if self.state == "probing":
            if reason in {"network", "timeout"}:
                # Windows의 연결 거부보다 Qt 제한 시간이 먼저 끝날 수 있다.
                # 실제 포트 선점 여부는 worker가 DB를 열기 전에 배타적 bind로 다시 확인한다.
                self._spawn()
            else:
                self._fail("연결 포트의 응답을 확인하지 못했습니다. 이미 실행 중인 프로그램과 "
                           "포트 설정을 확인한 뒤 강써치를 다시 실행해 주세요.")
        elif self.state == "starting" and reason not in {"network", "timeout"}:
            self._fail("시작한 서버의 응답이 맞지 않습니다. 포트와 설치 파일을 확인해 주세요.")

    def _spawn(self) -> None:
        """숨김 프로세스로 같은 EXE를 실행하고 정상 종료용 소유 채널을 함께 전달한다."""
        if self.state != "probing":
            return
        try:
            self.control = WindowsStopSignal()
            environment = dict(os.environ)
            # 소유 worker는 부모 실행 파일의 압축 해제 자료를 공유하고 부모보다 오래 실행하지 않는다.
            environment.pop("PYINSTALLER_RESET_ENVIRONMENT", None)
            self.process = subprocess.Popen(
                worker_command(self.port, self.control.name, self.db_path),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, RuntimeError):
            self._fail("서버를 시작하지 못했습니다. 설치 파일과 실행 권한을 확인한 뒤 다시 실행해 주세요.")
            return
        self.state = "starting"
        self._deadline = time.monotonic() + 20.0
        self._show_status("서버 시작 중", "서버가 준비되면 자동으로 연결합니다.", busy=True)
        self.poll_timer.start()

    def _tick(self) -> None:
        """소유 worker의 종료와 준비 상태를 살피며 HTTP 응답을 기다리는 동안 UI를 막지 않는다."""
        if self.state not in {"starting", "ready_owned"}:
            return
        return_code = self.process.poll()
        if return_code is not None:
            message = ("연결 포트를 다른 프로그램이 사용 중입니다. 포트 설정을 확인해 주세요."
                       if return_code == 2 else "서버가 종료되었습니다. 강써치를 다시 실행해 주세요.")
            self._fail(message)
        elif self.state == "starting":
            if time.monotonic() >= self._deadline:
                self._fail("서버 시작 시간이 초과되었습니다. 강써치를 다시 실행해 주세요.")
            elif self.control.is_ready() and self.probe.reply is None:
                self.probe.get("/health")
        elif not self.control.is_ready():
            self._fail("서버가 중지되었습니다. 강써치를 다시 실행해 주세요.")

    def _ready(self, *, owned: bool) -> None:
        """검증된 준비 상태에서만 기존 Client 연결 흐름과 현재 작업·보호 조회를 시작한다."""
        self.state = "ready_owned" if owned else "ready_external"
        self.probe.close()
        if not owned:
            self.poll_timer.stop()
        self.window.management.button.setEnabled(True)
        self.window.recheck_action.setEnabled(True)
        self._original_check()

    def _show_status(self, title: str, message: str, *, busy: bool) -> None:
        """시작·실패 이유를 같은 창에서 보여 주고 내부 실행 인자나 파일 경로는 노출하지 않는다."""
        self.window.management.status.setText(title)
        self.window.management.connection_message.setText(message)
        self.window.search.connection_button.setText(title)
        self.window.search.connection_button.setToolTip(message + " 현재 작업과 연결 설정을 엽니다.")
        self.window.management.button.setEnabled(not busy)
        self.window.recheck_action.setEnabled(not busy)

    def _fail(self, message: str) -> None:
        """실패는 한 번만 표시하고 이전 연결·기록 가능 상태와 소유 worker를 함께 무효화한다."""
        if self.state in {"failed", "stopped"}:
            return
        self.state = "failed"
        self.poll_timer.stop()
        self.probe.close()
        self._close_client_connections()
        self._stop_owned()
        # 기존 진단도 실패 JSON을 기록하도록 동일한 연결 실패 신호를 전달한다.
        self.window.management.backend.connection_changed.emit(False)
        self._show_status("서버 시작 실패", message, busy=True)

    def _stop_owned(self) -> None:
        """자신이 시작한 프로세스에 정상 종료를 먼저 요청하고 응답하지 않을 때만 정리한다."""
        process = self.process
        if self.control is not None:
            try:
                self.control.request_stop()
            except OSError:
                self.shutdown_clean = False
        if process is not None:
            try:
                if process.wait(timeout=8) != 0:
                    self.shutdown_clean = False
            except subprocess.TimeoutExpired:
                self.shutdown_clean = False
                # Popen이 보유한 자신의 프로세스만 대상으로 하며 외부 서버 PID를 검색하지 않는다.
                if os.name == "nt" and process.poll() is None:
                    try:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       capture_output=True, check=False,
                                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=3)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError:
                        self.shutdown_clean = False
                try:
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    self.shutdown_clean = False
            except OSError:
                self.shutdown_clean = False
        if self.control is not None:
            self.control.close()
            self.control = None

    def _close_client_connections(self) -> None:
        """읽기 폴링과 Qt의 유휴 연결을 먼저 닫아 같은 포트로 정상 재실행할 수 있게 한다."""
        self.window.management.activity.stop()
        self.window.management.privacy.client.stop()
        for request in self.window.findChildren(_REQUEST_TYPE):
            request.close()
            request.manager.clearConnectionCache()
        # 큐에 남은 소켓 정리는 처리하되 종료 중 새 사용자 입력은 실행하지 않는다.
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 50)

    def stop(self) -> None:
        """창 닫힘·앱 종료가 겹쳐도 한 번만 소유 프로세스와 단일 실행 잠금을 정리한다."""
        if self.state == "stopped":
            return
        self.state = "stopped"
        self.poll_timer.stop()
        self.probe.close()
        self._close_client_connections()
        self._stop_owned()
        if self._locked:
            self.lock.unlock()
            self._locked = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Client 창을 닫기 시작하면 소유 서버도 먼저 정상 종료시킨다."""
        if watched is self.window and event.type() == QEvent.Type.Close:
            self.stop()
        return super().eventFilter(watched, event)
