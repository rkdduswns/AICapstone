"""현재 창 응답의 검증과 자동 조회. Windows 감지는 Backend가 담당한다."""

import json

from PySide6.QtCore import QObject, QTimer, Signal

from client.json_request import JsonRequest
from shared.activity import ACTIVITY_PATH, ActiveWindow, CurrentActivity
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME


def read_activity(payload: bytes) -> CurrentActivity:
    """상태와 창 정보의 조합까지 검사해 불완전한 정보를 표시하지 않는다."""
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True
            or "error" not in body or body["error"] is not None):
        raise ValueError("Invalid response envelope")
    data = body.get("data")
    if (not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION):
        raise ValueError("Incompatible service")
    status = data.get("collection_status")
    if status not in ("collecting", "no_active_window", "unsupported", "error"):
        raise ValueError("Invalid collection status")
    if "window" not in data:
        raise ValueError("Missing window field")
    window = data["window"]
    if status != "collecting":
        if window is not None:
            raise ValueError("Unexpected window for collection status")
        return CurrentActivity(collection_status=status, window=None)
    if not isinstance(window, dict):
        raise ValueError("Missing active window")
    for field in ("application", "process_name", "window_title"):
        if not isinstance(window.get(field), str):
            raise ValueError("Invalid window text")
    # 제목 없는 창은 유효하지만 프로그램/프로세스 식별 정보는 필요하다.
    if not window["application"].strip() or not window["process_name"].strip():
        raise ValueError("Missing application or process name")
    if type(window.get("process_id")) is not int or window["process_id"] <= 0:
        raise ValueError("Invalid process ID")
    return CurrentActivity(collection_status=status, window=ActiveWindow(
        application=window["application"], process_name=window["process_name"],
        process_id=window["process_id"], window_title=window["window_title"],
    ))


class ActivityClient(JsonRequest):
    """응답 완료 1초 뒤 다시 조회해 느린 서버에도 요청이 쌓이지 않도록 한다."""

    activity_received = Signal(object)
    activity_failed = Signal(str)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(port, parent)
        self.poll_timer = QTimer(self)
        self.poll_timer.setSingleShot(True)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.refresh)
        self.active = False
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def start(self) -> None:
        """호환되는 Backend 연결을 확인한 뒤 최초 조회를 즉시 시작한다."""
        if self.active:
            return
        self.active = True
        self.refresh()

    def refresh(self) -> None:
        """진행 중 요청은 재사용하고 완료 후에만 다음 타이머를 예약한다."""
        if self.active:
            self.poll_timer.stop()
            self.get(ACTIVITY_PATH)

    def _received(self, payload: bytes) -> None:
        """잘못된 데이터는 표시하지 않으며 다음 조회에서 자동 복구를 시도한다."""
        try:
            activity = read_activity(payload)
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        self.activity_received.emit(activity)
        self._schedule()

    def _failed(self, reason: str, status: int) -> None:
        """아직 API가 없는 Phase 1 서버와 일시적인 연결 실패를 구분한다."""
        if reason == "http" and status == 404:
            message = "기능 준비 중 — Backend가 현재 창 조회를 지원하지 않습니다."
        else:
            message = {
                "timeout": "수신 시간 초과 — 자동 재시도 중",
                "http": "수신 실패 — 서버 오류, 자동 재시도 중",
                "network": "수신 중단 — Backend 연결을 확인해 주세요. 자동 재시도 중",
                "content_type": "호환되지 않는 현재 창 응답 — 자동 재시도 중",
            }[reason]
        self.activity_failed.emit(message)
        self._schedule()

    def _schedule(self) -> None:
        """오류도 정상 응답처럼 간격을 두되 종료 후에는 재예약하지 않는다."""
        if self.active:
            self.poll_timer.start()

    def stop(self) -> None:
        """자동 조회와 진행 중 HTTP 요청을 모두 취소한다."""
        self.active = False
        self.poll_timer.stop()
        self.close()
