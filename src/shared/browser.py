"""브라우저 출처와 URL 차단 설정의 데이터 계약. 수집·차단 판정은 포함하지 않는다."""

from dataclasses import dataclass
from typing import Literal

MAX_BLOCKED_URLS = 100
MAX_URL_LENGTH = 8192
UrlRuleKind = Literal["domain", "exact", "prefix"]


@dataclass(frozen=True)
class BrowserPage:
    """작업에 연결된 브라우저 출처. 내부/빈 탭은 제목을 유지하고 URL만 None이다."""

    browser: Literal["chrome", "edge"]
    page_title: str
    url: str | None


@dataclass(frozen=True)
class UrlBlockRule:
    """도메인, 전체 URL, URL 시작 부분 중 사용자가 선택한 차단 범위."""

    kind: UrlRuleKind
    value: str
