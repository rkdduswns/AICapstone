"""Phase 4 저장 기록 조회 계약. DB 형식과 저장 로직은 Backend에서 결정한다."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

RECENT_RECORDS_PATH = "/records/recent"
RECENT_RECORDS_LIMIT = 20


@dataclass(frozen=True)
class ContextRecord:
    """안정적인 기록 ID와 출처 맥락을 유지하는 저장 기록의 조회용 구조."""

    id: str
    application: str
    process_name: str
    window_title: str
    started_at: str
    last_active_at: str
    active_duration_ms: int
    foreground_count: int


@dataclass(frozen=True)
class RecentRecords:
    """마지막 활성 시각 기준으로 최근 20건 이하를 반환한다."""

    records: list[ContextRecord]
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class RecentRecordsResponse:
    """현재 상태 API와 동일한 성공 envelope를 사용하는 기록 응답."""

    data: RecentRecords
    ok: Literal[True] = True
    error: None = None
