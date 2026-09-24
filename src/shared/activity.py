"""Phase 2 현재 창 응답 규격. OS 감지나 UI 처리에 의존하지 않는다."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

ACTIVITY_PATH = "/activity/current"
CollectionStatus = Literal["collecting", "no_active_window", "unsupported", "error"]


@dataclass(frozen=True)
class ActiveWindow:
    """Backend가 감지·정규화한 현재 창 정보이며 저장 기록이나 작업 시간은 아니다."""

    application: str
    process_name: str
    process_id: int
    window_title: str


@dataclass(frozen=True)
class CurrentActivity:
    """감지 성공일 때만 window를 제공하고 나머지 상태에서는 None으로 비운다."""

    collection_status: CollectionStatus
    window: ActiveWindow | None
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class CurrentActivityResponse:
    """통신 성공과 실제 창 감지 상태를 구분하는 공통 응답 구조."""

    data: CurrentActivity
    ok: Literal[True] = True
    error: None = None
