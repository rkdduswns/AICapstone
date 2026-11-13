
"""활성 창을 추적하고 진행 중인 세션도 같은 작업 ID로 지속 저장한다."""

import logging
import sys
import time
from datetime import datetime, timezone
from typing import Callable

from backend.privacy import PrivacyPolicy
from shared.activity import (
    ActiveWindow,
    ActivityRecord,
    ActivityTiming,
    CollectionStatus,
    CurrentActivity,
)

logger = logging.getLogger(__name__)


class ActivityTracker:
    """활성 창·누적 시간을 수집하고 샘플 갱신과 세션 종료에 같은 저장 행을 사용한다."""

    def __init__(
        self,
        detector: object | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
        store: object | None = None,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> None:
        self._detector = detector
        self._clock = clock
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._store = store
        self._identity: tuple[str, str, int, str] | None = None
        self._window: ActiveWindow | None = None
        self._started_at: str | None = None
        self._start_tick: float | None = None
        self._record_id: int | None = None
        self._privacy_policy = privacy_policy or PrivacyPolicy()

    def configure(self, store=None, privacy_policy: PrivacyPolicy | None = None) -> None:
        """API·수집기가 동일한 저장소와 정책을 사용하도록 앱 시작 시 의존성을 연결한다."""
        if store is not None:
            self._store = store
        if privacy_policy is not None:
            self._privacy_policy = privacy_policy

    @property
    def privacy_policy(self) -> PrivacyPolicy:
        """주입된 추적기의 정책을 API에서도 공유하여 설정과 실제 판정이 어긋나지 않게 한다."""
        return self._privacy_policy

    @property
    def store(self):
        """필요할 때만 DB를 열고 모든 API에 같은 저장소 인스턴스를 제공한다."""
        return self._get_store()

    def finish(self) -> None:
        """종료 또는 설정 변경 경계까지 허용된 작업을 저장하고 다음 세션과 분리한다."""
        self._finish_current()

    def _get_detector(self) -> object | None:
        if self._detector is not None:
            return self._detector

        if sys.platform != "win32":
            return None

        from backend import window_detector

        self._detector = window_detector
        return self._detector

    def _get_store(self):
        if self._store is None:
            from backend.activity_store import ActivityStore

            self._store = ActivityStore()
        return self._store

    def _reset(self) -> None:
        self._identity = None
        self._window = None
        self._started_at = None
        self._start_tick = None
        self._record_id = None

    def _finish_current(self) -> None:
        """현재 세션의 마지막 시각·누적 시간을 갱신한 뒤 추적 상태를 비운다."""
        if (
            self._window is None
            or self._started_at is None
            or self._start_tick is None
        ):
            self._reset()
            return

        window = self._window
        started_at = self._started_at
        duration_ms = max(0, int((self._clock() - self._start_tick) * 1000))
        ended_at = self._now().isoformat()

        try:
            self._persist(window, started_at, ended_at, duration_ms)
        except Exception as exc:
            logger.warning("Activity persistence failed (%s)", type(exc).__name__)
        finally:
            self._reset()

    def _persist(self, window: ActiveWindow, started_at: str, ended_at: str,
                 duration_ms: int) -> None:
        """최초 감지에만 ID를 만들고 이후 샘플·종료는 같은 행을 갱신한다."""
        store = self._get_store()
        if self._record_id is None:
            self._record_id = store.save_record(window, started_at, ended_at, duration_ms)
        else:
            store.update_record(self._record_id, ended_at, duration_ms)

    def _empty_activity(self, status: CollectionStatus) -> CurrentActivity:
        self._finish_current()
        return CurrentActivity(collection_status=status, window=None, timing=None)

    def get_current_activity(self) -> CurrentActivity:
        """현재 창·활성 시간을 저장하고 출처 연결에 사용할 실제 작업 ID를 반환한다."""
        try:
            # Privacy pause must be checked before touching the detector.
            if self._privacy_policy.collection_paused:
                return self._empty_activity("paused")

            detector = self._get_detector()
            if detector is None:
                return self._empty_activity("unsupported")

            handle = detector.get_active_window_handle()
            if handle is None or handle == 0:
                return self._empty_activity("no_active_window")

            # Identify the process before reading its window title.
            process_id = detector.get_process_id(handle)
            if process_id is None or process_id <= 0:
                return self._empty_activity("error")

            process_name = detector.get_process_name(process_id)
            if not process_name:
                return self._empty_activity("error")

            application = detector.normalize_app_name(process_name)

            # Never read the title of a blocked application.
            if self._privacy_policy.is_blocked(application, process_name):
                return self._empty_activity("blocked")

            title = detector.get_window_title(handle)
            if not title or not title.strip():
                return self._empty_activity("no_active_window")

            title = self._privacy_policy.sanitize_title(title)

            window = ActiveWindow(
                application=application,
                process_name=process_name,
                process_id=process_id,
                window_title=title,
            )
            identity = (
                window.application,
                window.process_name,
                window.process_id,
                window.window_title,
            )

            if identity != self._identity:
                self._finish_current()
                self._identity = identity
                self._window = window
                self._started_at = self._now().isoformat()
                self._start_tick = self._clock()

            assert self._started_at is not None
            assert self._start_tick is not None

            elapsed_ms = max(
                0,
                int((self._clock() - self._start_tick) * 1000),
            )
            self._persist(window, self._started_at, self._now().isoformat(), elapsed_ms)
            return CurrentActivity(
                collection_status="collecting",
                window=window,
                timing=ActivityTiming(
                    started_at=self._started_at,
                    active_duration_ms=elapsed_ms,
                ),
                record_id=str(self._record_id),
            )
        except Exception:
            logger.exception("Failed to collect current activity")
            return self._empty_activity("error")

    def get_recent_records(self, limit: int = 50) -> list[ActivityRecord]:
        """Return persisted sessions, newest first."""
        return self._get_store().get_recent_records(limit)
