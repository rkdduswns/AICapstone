"""현재 활동 추적 및 관련 데이터의 공통 규격을 정의한다."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

ACTIVITY_PATH = "/activity/current"
ACTIVITY_HISTORY_PATH = "/activity/history"
BROWSER_SOURCE_PATH = "/browser/source"
BROWSER_CONTENT_PATH = "/browser/content"

CollectionStatus = Literal[
    "collecting",
    "no_active_window",
    "unsupported",
    "error",
    "paused",
    "blocked",
]


@dataclass(frozen=True)
class ActiveWindow:
    """현재 활성화된 애플리케이션 창의 정보를 나타낸다."""

    application: str
    process_name: str
    process_id: int
    window_title: str


@dataclass(frozen=True)
class ActivityTiming:
    """현재 활동의 시작 시각과 누적 활성 시간을 나타낸다."""

    started_at: str
    active_duration_ms: int


@dataclass(frozen=True)
class CurrentActivity:
    """백엔드가 반환하는 현재 활동 상태를 나타낸다."""

    collection_status: CollectionStatus
    window: ActiveWindow | None
    service: str = SERVICE_NAME
    api_version: int = API_VERSION
    timing: ActivityTiming | None = None
    # 수집 중에도 유지되는 실제 저장 ID. 구형 응답과 비수집 상태에서는 None이다.
    record_id: str | None = None


@dataclass(frozen=True)
class CurrentActivityResponse:
    """현재 활동 조회 API의 공통 성공 응답 구조를 정의한다."""

    data: CurrentActivity
    ok: Literal[True] = True
    error: None = None


@dataclass(frozen=True)
class ActivityRecord:
    """데이터베이스에 저장된 하나의 활동 기록을 나타낸다."""

    id: int
    application: str
    process_name: str
    process_id: int
    window_title: str
    started_at: str
    ended_at: str
    active_duration_ms: int


@dataclass(frozen=True)
class ClipboardRecord:
    """특정 활동과 연결된 클립보드 수집 기록을 나타낸다."""

    id: int
    application: str
    activity_started_at: str
    captured_at: str
    content: str


@dataclass(frozen=True)
class BrowserSourceRecord:
    """브라우저 탭에서 수집한 페이지 정보를 나타낸다."""

    id: int
    browser: str
    url: str
    page_title: str
    captured_at: str


@dataclass(frozen=True)
class BrowserContentRecord:
    """수집한 브라우저 페이지의 텍스트 내용을 나타낸다."""

    id: int
    browser_source_id: int
    content_text: str
    captured_at: str


@dataclass(frozen=True)
class DocumentRecord:
    """로컬 문서의 메타데이터와 추출한 텍스트를 나타낸다."""

    id: int
    file_path: str
    file_name: str
    file_type: str
    extracted_text: str
    captured_at: str
