
"""Privacy-aware, on-demand clipboard collection for Windows."""

import ctypes
import sys
from datetime import datetime, timezone
from typing import Callable

from backend.activity_tracker import ActivityTracker
from backend.privacy import PrivacyPolicy
from shared.activity import CurrentActivity
from shared.clipboard import MAX_CLIPBOARD_TEXT_LENGTH


class ClipboardCollector:
    """Collect a clipboard text snapshot when explicitly enabled."""

    def __init__(
        self,
        activity_tracker: ActivityTracker,
        store: object | None = None,
        privacy_policy: PrivacyPolicy | None = None,
        enabled: bool = False,
        clipboard_reader: Callable[[], str | None] | None = None,
        now: Callable[[], datetime] | None = None,
        clipboard_stamp: Callable[[], tuple[int, int]] | None = None,
    ) -> None:
        self._activity_tracker = activity_tracker
        self._store = store
        self._privacy_policy = privacy_policy or PrivacyPolicy()
        self._enabled = enabled
        self._clipboard_reader = (
            clipboard_reader or self._read_windows_clipboard
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._stamp = clipboard_stamp or (
            self._windows_clipboard_stamp if clipboard_reader is None else None
        )
        self._last_sequence: int | None = None
        self._last_content: tuple[str, str, str] | None = None
        self.reset_baseline()

    def set_enabled(self, enabled: bool) -> None:
        """설정 변경 전의 오래된 복사 내용을 새 작업의 이벤트로 저장하지 않는다."""
        if enabled != self._enabled:
            self._enabled = enabled
            self.reset_baseline()

    def reset_baseline(self) -> None:
        """수집·정책 경계의 시퀀스를 기준으로 삼아 비활성 기간에 복사한 내용을 건너뛴다."""
        self._last_sequence = self._stamp()[0] if self._stamp is not None else None
        self._last_content = None

    @staticmethod
    def _windows_clipboard_stamp() -> tuple[int, int]:
        """텍스트를 읽지 않고 변경 번호와 소유 프로세스를 확인한다. 불명확하면 0이다."""
        if sys.platform != "win32":
            return (0, 0)
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetClipboardSequenceNumber.argtypes = []
        user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
        user32.GetClipboardOwner.argtypes = []
        user32.GetClipboardOwner.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        pid = wintypes.DWORD()
        owner = user32.GetClipboardOwner()
        if owner:
            user32.GetWindowThreadProcessId(owner, ctypes.byref(pid))
        return (int(user32.GetClipboardSequenceNumber()), int(pid.value))

    def _get_store(self):
        if self._store is None:
            # 주입된 추적기의 DB와 달라지면 작업과 복사 내용의 연결을 잃는다.
            self._store = self._activity_tracker.store
        return self._store

    @staticmethod
    def _read_windows_clipboard() -> str | None:
        """Read Unicode text from the Windows clipboard, if available."""
        if sys.platform != "win32":
            return None

        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        if not user32.OpenClipboard(None):
            return None

        handle = None
        pointer = None
        try:
            # CF_UNICODETEXT = 13
            handle = user32.GetClipboardData(13)
            if not handle:
                return None

            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return None

            return ctypes.wstring_at(pointer)
        finally:
            if pointer:
                kernel32.GlobalUnlock(handle)
            user32.CloseClipboard()

    def collect_once(self, activity: CurrentActivity | None = None) -> int | None:
        """허용된 작업의 새 복사 내용만 저장하고 ID를 반환한다. 건너뛰면 None이다."""
        if not self._enabled or self._privacy_policy.collection_paused:
            return None

        # 같은 폴링에서 감지한 스냅샷을 재사용해 다른 창의 시작 시각과 섞이지 않게 한다.
        activity = activity or self._activity_tracker.get_current_activity()
        if activity.collection_status != "collecting":
            return None

        window = activity.window
        timing = activity.timing
        if window is None or timing is None:
            return None

        if self._privacy_policy.is_blocked(
            window.application,
            window.process_name,
        ):
            return None

        stamp = self._stamp() if self._stamp is not None else None
        if stamp is not None:
            sequence, owner = stamp
            if not sequence or sequence == self._last_sequence:
                return None
            self._last_sequence = sequence
            if owner != window.process_id:
                return None
        content = self._clipboard_reader()
        if stamp is not None and self._stamp() != stamp:
            return None  # 읽는 동안 다른 앱이 바꾼 내용을 현재 작업에 연결하지 않는다.
        if not content or not content.strip() or len(content) > MAX_CLIPBOARD_TEXT_LENGTH:
            return None

        if self._privacy_policy.contains_sensitive_data(content):
            return None

        identity = (window.application, timing.started_at, content)
        if identity == self._last_content:
            return None

        record_id = self._get_store().save_clipboard_record(
            application=window.application,
            activity_started_at=timing.started_at,
            captured_at=self._now().isoformat(),
            content=content,
        )
        self._last_content = identity
        return record_id
