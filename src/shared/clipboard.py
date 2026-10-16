"""작업에 연결되어 저장된 복사 텍스트의 조회 계약. 실제 감지는 Backend에서 수행한다."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

RECORD_CLIPBOARD_PATH = "/records/clipboard"
CLIPBOARD_ENTRIES_LIMIT = 20
MAX_CLIPBOARD_TEXT_LENGTH = 10000


@dataclass(frozen=True)
class ClipboardEntry:
    """하나의 복사 이벤트. 정규화되지 않은 텍스트와 시간대가 있는 복사 시각을 유지한다."""

    id: str
    copied_at: str
    text: str


@dataclass(frozen=True)
class RecordClipboard:
    """선택 작업 ID와 최근 복사 항목을 함께 반환하여 다른 작업과 섞이지 않게 한다."""

    record_id: str
    entries: list[ClipboardEntry]
    has_more: bool
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class RecordClipboardResponse:
    """기존 API와 같은 성공 envelope를 유지한다."""

    data: RecordClipboard
    ok: Literal[True] = True
    error: None = None
