"""단일 EXE가 시작한 Windows worker의 종료·준비 신호와 부모 수명을 관리한다."""

import ctypes
import os
import sys
import threading
from ctypes import wintypes
from functools import lru_cache
from uuid import uuid4

_SYNCHRONIZE = 0x00100000
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_INFINITE = 0xFFFFFFFF


@lru_cache(maxsize=1)
def _kernel32():
    """다른 OS의 모듈 수집 시에는 WinDLL을 열지 않고 실제 Windows 실행에서만 준비한다."""
    if sys.platform != "win32":
        raise OSError("통합 실행의 프로세스 제어는 Windows에서만 지원합니다.")
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateEventW": ([ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR],
                         wintypes.HANDLE),
        "OpenEventW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "SetEvent": ([wintypes.HANDLE], wintypes.BOOL),
        "ResetEvent": ([wintypes.HANDLE], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "WaitForMultipleObjects": ([wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                                    wintypes.BOOL, wintypes.DWORD], wintypes.DWORD),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
    return library


def _handle(value):
    """실패한 핸들을 성공으로 해석하지 않도록 생성·열기 결과를 즉시 검사한다."""
    if not value:
        raise OSError(ctypes.get_last_error(), "Windows 실행 제어 핸들을 열지 못했습니다.")
    return value


class WindowsStopSignal:
    """부모가 만든 무작위 신호만 자식에게 전달하며 다른 서버의 프로세스를 제어하지 않는다."""

    def __init__(self) -> None:
        """종료·준비 이벤트는 개별 실행마다 분리하고 자식이 연 뒤에도 같은 수명을 유지한다."""
        self.name = "Local\\GangSearchStop-" + uuid4().hex
        self._library = _kernel32()
        self._stop = self._ready = None
        try:
            self._stop = _handle(self._library.CreateEventW(None, True, False, self.name))
            self._ready = _handle(self._library.CreateEventW(None, True, False, self.name + "-ready"))
        except OSError:
            self.close()
            raise

    def request_stop(self) -> None:
        """현재 실행이 소유한 worker에 정상 종료를 요청하며 반복 호출은 안전하다."""
        if self._stop is not None and not self._library.SetEvent(self._stop):
            raise OSError(ctypes.get_last_error(), "서버 종료 신호를 전달하지 못했습니다.")

    def is_ready(self) -> bool:
        """자식 서버가 실제 시작됐다고 알린 신호만 확인한다. health 응답 검사는 별도다."""
        return (self._ready is not None
                and self._library.WaitForSingleObject(self._ready, 0) == _WAIT_OBJECT_0)

    def close(self) -> None:
        """부모가 가진 핸들만 닫는다. 외부 서버나 다른 실행의 이벤트를 건드리지 않는다."""
        for name in ("_ready", "_stop"):
            handle = getattr(self, name, None)
            if handle is not None:
                self._library.CloseHandle(handle)
                setattr(self, name, None)


class WorkerLifetime:
    """worker 자신만 종료할 수 있는 부모 감시기로 orphan 수집과 종료 대기를 제한한다."""

    def __init__(self, owner_pid: int, stop_event: str, request_stop, *,
                 exit_process=os._exit, shutdown_timeout: float = 5.0) -> None:
        """부모 핸들과 두 이벤트를 먼저 열어 소유자 없는 worker가 DB를 만들지 않게 한다."""
        if (type(owner_pid) is not int or not 1 <= owner_pid <= 0xFFFFFFFF or owner_pid == os.getpid()
                or not isinstance(stop_event, str) or not stop_event.startswith("Local\\GangSearchStop-")):
            raise OSError("올바른 실행 소유자가 필요합니다.")
        self._library = _kernel32()
        self._owner = self._stop = self._ready = self._finished = None
        self._thread = None
        self._request_stop = request_stop
        self._exit_process = exit_process
        self._timeout_ms = max(1, int(shutdown_timeout * 1000))
        try:
            self._owner = _handle(self._library.OpenProcess(_SYNCHRONIZE, False, owner_pid))
            self._stop = _handle(self._library.OpenEventW(_SYNCHRONIZE, False, stop_event))
            self._ready = _handle(self._library.OpenEventW(
                _SYNCHRONIZE | _EVENT_MODIFY_STATE, False, stop_event + "-ready"))
            self._finished = _handle(self._library.CreateEventW(None, True, False, None))
            if (self._library.WaitForSingleObject(self._owner, 0) != _WAIT_TIMEOUT
                    or self._library.WaitForSingleObject(self._stop, 0) != _WAIT_TIMEOUT):
                raise OSError("실행 소유자가 이미 종료됐습니다.")
        except OSError:
            self.close()
            raise

    def start(self) -> None:
        """무거운 Backend import 전에 소유자 종료를 감시한다."""
        self._thread = threading.Thread(target=self._watch, name="gangsearch-owner", daemon=True)
        self._thread.start()

    def mark_ready(self) -> None:
        """본인 서버가 시작된 뒤에만 부모에게 포트 소유 준비를 알린다."""
        if self._ready is not None:
            self._library.SetEvent(self._ready)

    def _watch(self) -> None:
        """부모 충돌은 자신만 즉시 끝내고 정상 종료 요청은 기존 서버 정리를 먼저 기다린다."""
        handles = (wintypes.HANDLE * 3)(self._finished, self._stop, self._owner)
        result = self._library.WaitForMultipleObjects(3, handles, False, _INFINITE)
        if result == _WAIT_OBJECT_0:
            return
        if result == _WAIT_OBJECT_0 + 1:
            self._request_stop()
            finishing = (wintypes.HANDLE * 2)(self._finished, self._owner)
            if self._library.WaitForMultipleObjects(2, finishing, False, self._timeout_ms) == _WAIT_OBJECT_0:
                return
        # 이 코드의 유일한 강제 종료 대상은 현재 worker 자신이다.
        self._exit_process(4)

    def close(self) -> None:
        """기다리는 스레드를 깨워 완료한 뒤 핸들을 닫아 대기 중 핸들 해제를 피한다."""
        if self._finished is not None:
            self._library.SetEvent(self._finished)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                # 닫힌 핸들로 대기하게 만들지 않는다. 이 경우 프로세스 종료 때 OS가 회수한다.
                return
            self._thread = None
        if self._ready is not None:
            self._library.ResetEvent(self._ready)
        for name in ("_finished", "_ready", "_stop", "_owner"):
            handle = getattr(self, name, None)
            if handle is not None:
                self._library.CloseHandle(handle)
                setattr(self, name, None)
