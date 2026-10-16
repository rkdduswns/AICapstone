"""작업에 연결된 저장 웹 본문의 조회 계약. 페이지 수집·정제·저장은 Backend 책임이다."""

from dataclasses import dataclass
from typing import Literal

from shared.browser import BrowserPage
from shared.protocol import API_VERSION, SERVICE_NAME

RECORD_WEB_CONTENT_PATH = "/records/web-content"
MAX_WEB_CONTENT_LENGTH = 50000


@dataclass(frozen=True)
class WebContent:
    """본문을 얻은 시점의 출처와 텍스트. 길이 제한으로 일부만 저장했으면 명시한다."""

    page: BrowserPage
    captured_at: str
    text: str
    truncated: bool


@dataclass(frozen=True)
class RecordWebContent:
    """작업의 최신 저장 본문 하나를 반환한다. None은 정상 조회했지만 본문이 없는 경우다."""

    record_id: str
    content: WebContent | None
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class RecordWebContentResponse:
    """기존 조회 API와 같은 성공 envelope. 미지원/거부는 HTTP 오류로 구분한다."""

    data: RecordWebContent
    ok: Literal[True] = True
    error: None = None
