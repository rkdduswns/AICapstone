"""기존 데스크톱 Client 계약과 실제 추적기·SQLite 저장소를 연결한다."""

from dataclasses import asdict

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, ConfigDict, field_validator
from starlette.exceptions import HTTPException

from shared.clipboard import (
    CLIPBOARD_ENTRIES_LIMIT,
    RECORD_CLIPBOARD_PATH,
    ClipboardEntry,
    RecordClipboard,
    RecordClipboardResponse,
)
from shared.privacy import (
    BLOCKED_PROCESSES_PATH,
    CLIPBOARD_SETTING_PATH,
    MAX_BLOCKED_PROCESSES,
    PAUSED_PATH,
    PRIVACY_PATH,
    PrivacyResponse,
    PrivacySettings,
    PrivacyState,
    RecordingStatus,
)


class PausedRequest(BaseModel):
    """문자열/숫자를 bool로 강제 변환하거나 다른 설정을 함께 쓰지 않는다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    paused: bool


class ClipboardSettingRequest(BaseModel):
    """수집 사용 여부만 변경하여 프로그램 차단과 일시정지를 보존한다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    clipboard_enabled: bool


class BlockedProcessesRequest(BaseModel):
    """실행 파일 이름만 정규화하며 경로나 패턴을 차단 규칙으로 해석하지 않는다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    blocked_processes: list[str]

    @field_validator("blocked_processes")
    @classmethod
    def normalize(cls, names: list[str]) -> list[str]:
        """Client와 같은 정규형을 반환하고 최대 개수와 잘못된 문자를 검사한다."""
        normalized = set()
        for name in names:
            name = name.strip().lower()
            if (not name.endswith(".exe") or not name[:-4].strip() or len(name) > 255
                    or any(c in '<>:"/\\|?*' or ord(c) < 32 for c in name)):
                raise ValueError("실행 파일 이름을 입력해 주세요.")
            normalized.add(name)
        if len(normalized) > MAX_BLOCKED_PROCESSES:
            raise ValueError("차단 프로그램 개수를 초과했습니다.")
        return sorted(normalized)


def install_client_routes(app: FastAPI) -> None:
    """별도 가상 응답 없이 실제 Backend 상태와 저장 내용을 Client 규격으로 반환한다."""
    def state() -> dict:
        """설정과 같은 정책으로 현재 창을 판정하고 미지원 URL 설정은 None으로 남긴다."""
        policy = app.state.browser_privacy_policy
        activity = app.state.activity_tracker.get_current_activity()
        reason = {
            "collecting": "allowed", "paused": "paused", "blocked": "blocked_program",
            "no_active_window": "no_active_window", "unsupported": "unsupported", "error": "error",
        }[activity.collection_status]
        return asdict(PrivacyResponse(PrivacyState(
            PrivacySettings(policy.collection_paused, sorted(policy.blocked_applications),
                            app.state.clipboard_enabled, None),
            RecordingStatus(reason == "allowed", reason),
        )))

    async def desktop_write(request: Request) -> None:
        """브라우저 Origin 요청과 전용 JSON 헤더 없는 설정 변경은 적용 전에 거부한다."""
        if (request.headers.get("origin") is not None
                or request.headers.get("x-contexttrace-client") != "desktop"
                or request.headers.get("content-type", "").split(";")[0].strip().lower()
                != "application/json"):
            raise HTTPException(403)

    @app.get(PRIVACY_PATH)
    async def privacy_state():
        """현재 설정과 서버가 확인한 기록 가능 상태를 한 응답으로 제공한다."""
        return state()

    @app.put(PAUSED_PATH, dependencies=[Depends(desktop_write)])
    async def change_paused(payload: PausedRequest):
        """허용된 이전 세션을 닫은 뒤 목표 상태를 적용한다. 중복 요청은 재토글하지 않는다."""
        policy = app.state.browser_privacy_policy
        if payload.paused != policy.collection_paused:
            app.state.activity_tracker.finish()
            policy.collection_paused = payload.paused
            app.state.clipboard_collector.reset_baseline()
        return state()

    @app.put(BLOCKED_PROCESSES_PATH, dependencies=[Depends(desktop_write)])
    async def change_processes(payload: BlockedProcessesRequest):
        """기존 세션 경계에서 목록을 교체하고 이후 감지부터 새 정책을 사용한다."""
        policy = app.state.browser_privacy_policy
        names = set(payload.blocked_processes)
        if names != policy.blocked_applications:
            app.state.activity_tracker.finish()
            policy.blocked_applications = names
            app.state.clipboard_collector.reset_baseline()
        return state()

    @app.put(CLIPBOARD_SETTING_PATH, dependencies=[Depends(desktop_write)])
    async def change_clipboard(payload: ClipboardSettingRequest):
        """기본 꺼짐인 수집기의 사용 여부를 바꾸며 기존 복사 기록은 삭제하지 않는다."""
        app.state.clipboard_enabled = payload.clipboard_enabled
        app.state.clipboard_collector.set_enabled(payload.clipboard_enabled)
        return state()

    @app.get(RECORD_CLIPBOARD_PATH)
    async def record_clipboard(
        record_id: int = Query(ge=1, le=2**63 - 1),
        limit: int = Query(default=CLIPBOARD_ENTRIES_LIMIT, ge=1, le=CLIPBOARD_ENTRIES_LIMIT),
    ):
        """작업이 없으면 404, 연결된 항목이 없으면 빈 배열로 구분하고 초과 여부를 제공한다."""
        store = app.state.activity_tracker.store
        record = store.get_record(record_id)
        if record is None:
            raise HTTPException(404)
        entries = store.get_record_clipboard(record, limit + 1)
        return asdict(RecordClipboardResponse(RecordClipboard(
            str(record_id), [ClipboardEntry(str(row.id), row.captured_at, row.content)
                             for row in entries[:limit]], len(entries) > limit,
        )))
