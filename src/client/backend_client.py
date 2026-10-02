"""Backend 연결 응답을 검증하고 화면에 표시할 연결 상태로 바꾼다."""

import json

from PySide6.QtCore import QObject, Signal

from client.json_request import JsonRequest
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME


def read_version(payload: bytes) -> str:
    """다른 서비스나 호환되지 않는 API를 정상 연결로 오인하지 않도록 검사한다."""
    body = json.loads(payload)
    if not isinstance(body, dict) or body.get("ok") is not True or body.get("error") is not None:
        raise ValueError("Invalid response envelope")
    if "error" not in body:
        raise ValueError("Missing error field")
    status = body.get("data")
    if not isinstance(status, dict):
        raise ValueError("Missing health status")
    if (status.get("service") != SERVICE_NAME or status.get("status") != "running"
            or type(status.get("api_version")) is not int
            or status["api_version"] != API_VERSION):
        raise ValueError("Incompatible service")
    version = status.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Missing version")
    return version


class BackendClient(JsonRequest):
    """Phase 1의 수동 연결 확인을 유지하고 성공 여부를 별도 신호로 전달한다."""

    result = Signal(str)
    connection_changed = Signal(bool)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(port, parent)
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def check(self) -> None:
        """UI 이벤트 루프를 막지 않고 서비스 상태를 요청한다."""
        self.get("/health")

    def _received(self, payload: bytes) -> None:
        """검증된 응답일 때만 현재 창 정보 조회를 시작할 수 있게 한다."""
        try:
            version = read_version(payload)
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        self.result.emit(f"연결됨 — Backend {version}")
        self.connection_changed.emit(True)

    def _failed(self, reason: str, status: int) -> None:
        """서버 원문이나 내부 예외를 노출하지 않는 기존 연결 안내를 유지한다."""
        message = {
            "timeout": "시간 초과 — 다시 확인해 주세요.",
            "http": "상태 확인 실패 — HTTP 오류",
            "network": "연결 안 됨 — Backend 실행 후 다시 확인해 주세요.",
            "content_type": "호환되지 않는 응답",
        }[reason]
        self.result.emit(message)
        self.connection_changed.emit(False)
