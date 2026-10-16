"""Backend에 저장된 복사 텍스트를 조회한다. 시스템 클립보드는 사용하지 않는다."""

import json
from urllib.parse import quote

from PySide6.QtCore import QObject, Signal

from client.json_request import JsonRequest
from client.time_values import parse_timestamp
from shared.clipboard import (
    CLIPBOARD_ENTRIES_LIMIT,
    MAX_CLIPBOARD_TEXT_LENGTH,
    RECORD_CLIPBOARD_PATH,
    ClipboardEntry,
    RecordClipboard,
)
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME


def read_record_clipboard(payload: bytes, record_id: str) -> RecordClipboard:
    """요청한 작업과 일치하는 유효한 전체 응답만 시간순으로 정렬해 전달한다."""
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True
            or "error" not in body or body["error"] is not None):
        raise ValueError("Invalid clipboard envelope")
    data = body.get("data")
    if (not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION
            or data.get("record_id") != record_id or type(data.get("has_more")) is not bool):
        raise ValueError("Incompatible clipboard response")
    rows = data.get("entries")
    if not isinstance(rows, list) or len(rows) > CLIPBOARD_ENTRIES_LIMIT:
        raise ValueError("Invalid clipboard list")
    entries, identifiers = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid clipboard entry")
        identifier, value = row.get("id"), row.get("text")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ValueError("Invalid clipboard ID")
        if (not isinstance(value, str) or not value.strip()
                or len(value) > MAX_CLIPBOARD_TEXT_LENGTH):
            raise ValueError("Invalid clipboard text")
        parse_timestamp(row.get("copied_at"))
        identifiers.add(identifier)
        entries.append(ClipboardEntry(identifier, row["copied_at"], value))
    entries.sort(key=lambda entry: entry.id)
    entries.sort(key=lambda entry: parse_timestamp(entry.copied_at), reverse=True)
    return RecordClipboard(record_id, entries, data["has_more"])


class ClipboardClient(JsonRequest):
    """선택 변경 시 이전 요청을 취소하고 응답의 작업 ID도 대조한다."""

    entries_received = Signal(object)
    entries_failed = Signal(str)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        """기존 비동기 전송의 timeout/취소와 응답 검증을 연결한다."""
        super().__init__(port, parent)
        self.record_id: str | None = None
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def fetch(self, record_id: str) -> None:
        """작업 ID를 쿼리 값으로 인코딩해 경로나 추가 파라미터로 해석하지 않는다."""
        self.close()
        self.record_id = record_id
        self.get(f"{RECORD_CLIPBOARD_PATH}?record_id={quote(record_id, safe='')}"
                 f"&limit={CLIPBOARD_ENTRIES_LIMIT}")

    def _received(self, payload: bytes) -> None:
        """불완전하거나 다른 작업의 항목은 일부라도 표시하지 않는다."""
        if self.record_id is None:
            return
        try:
            result = read_record_clipboard(payload, self.record_id)
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        self.entries_received.emit(result)

    def _failed(self, reason: str, status: int) -> None:
        """본문 대신 공개 가능한 실패 사유만 알리고 수동 새로고침으로 복구한다."""
        if reason == "http" and status == 404:
            message = "조회 불가 — 기능 미지원 또는 삭제된 기록입니다. 최근 기록을 새로고침해 주세요."
        else:
            message = {
                "timeout": "복사 텍스트 조회 시간 초과 — 다시 확인해 주세요.",
                "http": "복사 텍스트 조회 실패 — 서버 오류입니다.",
                "network": "연결 안 됨 — Backend 실행 후 다시 확인해 주세요.",
                "content_type": "호환되지 않는 복사 텍스트 응답 — 다시 확인해 주세요.",
            }[reason]
        self.entries_failed.emit(message)

    def close(self) -> None:
        """선택 해제/재연결/종료 시 요청 ID와 진행 중 응답을 함께 비운다."""
        super().close()
        self.record_id = None
