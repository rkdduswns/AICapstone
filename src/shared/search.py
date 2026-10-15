"""Phase 11 명시적 조건 검색 계약. 필터 적용·조회·정렬은 Backend가 담당한다."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME
from shared.records import ContextRecord

SEARCH_PATH = "/records/search"
SEARCH_LIMIT = 20
MAX_SEARCH_KEYWORD = 200
MAX_SEARCH_PROCESS = 100


@dataclass(frozen=True)
class SearchRequest:
    """제목 부분 일치·프로세스 일치·출처·마지막 활성 시각 범위를 AND로 결합한다.

    active_from은 포함, active_before는 제외다. None은 해당 경계 제한 없음이며
    날짜 입력은 Client에서 PC 현지 날짜의 자정 경계로 바꿔 시간대를 함께 보낸다.
    """

    keyword: str = ""
    process_name: str = ""
    source_type: Literal["all", "web", "document", "pdf", "docx"] = "all"
    active_from: str | None = None
    active_before: str | None = None
    sort: Literal["recent", "oldest"] = "recent"
    limit: int = SEARCH_LIMIT


@dataclass(frozen=True)
class SearchResults:
    """확인된 검색 조건과 최대 limit건의 작업 메타데이터. 본문/조각은 포함하지 않는다."""

    request: SearchRequest
    records: list[ContextRecord]
    has_more: bool
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class SearchResponse:
    """기존 조회와 같은 성공 envelope. 실제 검색 미지원·실패는 HTTP 오류로 구분한다."""

    data: SearchResults
    ok: Literal[True] = True
    error: None = None
