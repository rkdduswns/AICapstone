"""개인정보 설정과 저장 가능 여부의 조회 계약. 보호 판정은 Backend 책임이다."""

from dataclasses import dataclass
from typing import Literal

from shared.browser import UrlBlockRule
from shared.protocol import API_VERSION, SERVICE_NAME

PRIVACY_PATH = "/privacy"
PAUSED_PATH = "/privacy/paused"
BLOCKED_PROCESSES_PATH = "/privacy/blocked-processes"
CLIPBOARD_SETTING_PATH = "/privacy/clipboard"
BLOCKED_URLS_PATH = "/privacy/blocked-urls"
MAX_BLOCKED_PROCESSES = 100
RecordingReason = Literal[
    "allowed", "paused", "blocked_program", "sensitive_content",
    "no_active_window", "unsupported", "error", "blocked_url",
]


@dataclass(frozen=True)
class PrivacySettings:
    """일시정지와 실행 파일 이름 목록. 개별 변경 요청은 다른 설정을 덮어쓰지 않는다."""

    paused: bool
    blocked_processes: list[str]
    # None은 기존 Backend의 기능 미지원이다. 미지원과 명시적인 꺼짐을 구분한다.
    clipboard_enabled: bool | None = None
    # None은 미지원, []는 지원되지만 설정된 규칙 없음이다. 둘을 같은 상태로 표시하지 않는다.
    blocked_urls: list[UrlBlockRule] | None = None


@dataclass(frozen=True)
class RecordingStatus:
    """Backend가 저장 직전에 판단한 현재 기록 가능 여부와 공개 가능한 사유 코드."""

    allowed: bool
    reason: RecordingReason


@dataclass(frozen=True)
class PrivacyState:
    """같은 시점에 읽은 설정과 기록 상태. 실제 민감 문자열을 포함하지 않는다."""

    settings: PrivacySettings
    recording: RecordingStatus
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class PrivacyResponse:
    """조회와 설정 적용 모두 적용된 전체 상태를 같은 envelope로 반환한다."""

    data: PrivacyState
    ok: Literal[True] = True
    error: None = None
