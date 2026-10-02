"""최근 기록 조회와 검증. Client는 현재 창 정보를 자체 저장하지 않는다."""

import json

from PySide6.QtCore import QObject, Signal

from client.json_request import JsonRequest
from client.time_values import parse_timestamp
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME
from shared.records import RECENT_RECORDS_LIMIT, RECENT_RECORDS_PATH, ContextRecord


def read_recent_records(payload: bytes) -> list[ContextRecord]:
    """응답 전체를 검사한 뒤 실제 시각 기준 최신순으로 정렬해 전달한다."""
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True
            or "error" not in body or body["error"] is not None):
        raise ValueError("Invalid response envelope")
    data = body.get("data")
    if (not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION):
        raise ValueError("Incompatible service")
    rows = data.get("records")
    if not isinstance(rows, list) or len(rows) > RECENT_RECORDS_LIMIT:
        raise ValueError("Invalid records list")
    records = []
    identifiers = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid record")
        for field in ("id", "application", "process_name", "window_title"):
            if not isinstance(row.get(field), str):
                raise ValueError("Invalid record text")
        if any(not row[field].strip() for field in ("id", "application", "process_name")):
            raise ValueError("Missing record identity")
        if row["id"] in identifiers:
            raise ValueError("Duplicate record ID")
        identifiers.add(row["id"])
        started = parse_timestamp(row.get("started_at"))
        last_active = parse_timestamp(row.get("last_active_at"))
        if last_active < started:
            raise ValueError("Activity precedes record start")
        for field, minimum in (("active_duration_ms", 0), ("foreground_count", 1)):
            if type(row.get(field)) is not int or row[field] < minimum:
                raise ValueError("Invalid record count or duration")
        records.append(ContextRecord(**{field: row[field] for field in (
            "id", "application", "process_name", "window_title", "started_at",
            "last_active_at", "active_duration_ms", "foreground_count",
        )}))
    # 문자열 순서는 서로 다른 시간대를 비교할 수 없다. 동일 시각은 ID순으로 고정한다.
    records.sort(key=lambda record: record.id)
    records.sort(key=lambda record: parse_timestamp(record.last_active_at), reverse=True)
    return records


class RecordsClient(JsonRequest):
    """현재 창 자동 조회와 독립적으로 최근 기록을 수동 새로고침한다."""

    records_received = Signal(object)
    records_failed = Signal(str)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        """공통 비동기 전송 결과를 기록 계약 검증과 화면 안내에 연결한다."""
        super().__init__(port, parent)
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def refresh(self) -> None:
        """개수 제한이 있는 목록을 요청하며 중복 요청은 공통 전송 계층에서 막는다."""
        self.get(f"{RECENT_RECORDS_PATH}?limit={RECENT_RECORDS_LIMIT}")

    def _received(self, payload: bytes) -> None:
        """잘못된 행을 부분 표시하지 않고 응답 전체의 성공 또는 실패를 알린다."""
        try:
            records = read_recent_records(payload)
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        self.records_received.emit(records)

    def _failed(self, reason: str, status: int) -> None:
        """미구현 API와 전송 오류를 구분하고 서버 오류 본문은 표시하지 않는다."""
        if reason == "http" and status == 404:
            message = "기능 준비 중 — Backend가 최근 기록 조회를 지원하지 않습니다."
        else:
            message = {
                "timeout": "조회 시간 초과 — 새로고침으로 다시 확인해 주세요.",
                "http": "조회 실패 — 서버 오류입니다. 다시 확인해 주세요.",
                "network": "연결 안 됨 — Backend 실행 후 새로고침해 주세요.",
                "content_type": "호환되지 않는 기록 응답 — 다시 확인해 주세요.",
            }[reason]
        self.records_failed.emit(message)
