
"""Privacy-aware, on-demand clipboard collection for Windows."""

import ctypes
import sys
from datetime import datetime, timezone
from typing import Callable

from backend.activity_tracker import ActivityTracker
from backend.privacy import PrivacyPolicy


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
    ) -> None:
        self._activity_tracker = activity_tracker
        self._store = store
        self._privacy_policy = privacy_policy or PrivacyPolicy()
        self._enabled = enabled
        self._clipboard_reader = (
            clipboard_reader or self._read_windows_clipboard
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._last_content: str | None = None

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable clipboard collection."""
        self._enabled = enabled

    def _get_store(self):
        if self._store is None:
            from backend.activity_store import ActivityStore

            self._store = ActivityStore()
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

    def collect_once(self) -> int | None:
        """Collect and persist one permitted clipboard snapshot.

        Returns the saved record ID, or None when collection is skipped.
        """
        if not self._enabled or self._privacy_policy.collection_paused:
            return None

        activity = self._activity_tracker.get_current_activity()
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

        content = self._clipboard_reader()
        if not content or not content.strip():
            return None

        if self._privacy_policy.contains_sensitive_data(content):
            return None

        if content == self._last_content:
            return None

        record_id = self._get_store().save_clipboard_record(
            application=window.application,
            activity_started_at=timing.started_at,
            captured_at=self._now().isoformat(),
            content=content,
        )
        self._last_content = content
        return record_id