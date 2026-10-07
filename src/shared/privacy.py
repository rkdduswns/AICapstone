"""개인정보 설정과 저장 가능 여부의 조회 계약. 보호 판정은 Backend 책임이다."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

PRIVACY_PATH = "/privacy"
PAUSED_PATH = "/privacy/paused"
BLOCKED_PROCESSES_PATH = "/privacy/blocked-processes"
MAX_BLOCKED_PROCESSES = 100
RecordingReason = Literal[
    "allowed", "paused", "blocked_program", "sensitive_content",
    "no_active_window", "unsupported", "error",
]


@dataclass(frozen=True)
class PrivacySettings:
    """일시정지와 실행 파일 이름 목록. 개별 변경 요청은 다른 설정을 덮어쓰지 않는다."""

    paused: bool
    blocked_processes: list[str]


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
