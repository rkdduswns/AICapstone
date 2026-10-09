"""개인정보 설정 응답을 검증한다. 저장 허용 여부를 Client에서 추측하지 않는다."""

import json

from PySide6.QtCore import QObject, QTimer, Signal

from client.json_request import JsonRequest
from shared.privacy import (
    BLOCKED_PROCESSES_PATH,
    CLIPBOARD_SETTING_PATH,
    MAX_BLOCKED_PROCESSES,
    PAUSED_PATH,
    PRIVACY_PATH,
    PrivacySettings,
    PrivacyState,
    RecordingStatus,
)
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME


def normalize_processes(names: list[str]) -> list[str]:
    """실행 파일 이름만 허용하고 앞뒤 공백·대소문자·중복을 정리한다."""
    normalized = set()
    for name in names:
        if not isinstance(name, str):
            raise ValueError("실행 파일 이름은 문자열이어야 합니다.")
        name = name.strip().lower()
        if (not name.endswith(".exe") or not name[:-4].strip() or len(name) > 255
                or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in name)):
            raise ValueError("경로나 패턴 대신 실행 파일 이름을 입력해 주세요. 예: chrome.exe")
        normalized.add(name)
    if len(normalized) > MAX_BLOCKED_PROCESSES:
        raise ValueError(f"차단 프로그램은 최대 {MAX_BLOCKED_PROCESSES}개입니다.")
    return sorted(normalized)


def read_privacy(payload: bytes) -> PrivacyState:
    """설정과 판정이 모순되거나 타입이 잘못된 응답은 미확인 상태로 처리한다."""
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True
            or "error" not in body or body["error"] is not None):
        raise ValueError("Invalid envelope")
    data = body.get("data")
    if (not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION):
        raise ValueError("Incompatible service")
    settings, recording = data.get("settings"), data.get("recording")
    if not isinstance(settings, dict) or not isinstance(recording, dict):
        raise ValueError("Missing privacy state")
    paused, blocked = settings.get("paused"), settings.get("blocked_processes")
    if type(paused) is not bool or not isinstance(blocked, list):
        raise ValueError("Invalid settings")
    if len(blocked) > MAX_BLOCKED_PROCESSES or normalize_processes(blocked) != blocked:
        raise ValueError("Noncanonical blocked processes")
    clipboard_enabled = settings.get("clipboard_enabled")
    if clipboard_enabled is not None and type(clipboard_enabled) is not bool:
        raise ValueError("Invalid clipboard setting")
    allowed, reason = recording.get("allowed"), recording.get("reason")
    if type(allowed) is not bool or reason not in (
        "allowed", "paused", "blocked_program", "sensitive_content",
        "no_active_window", "unsupported", "error",
    ):
        raise ValueError("Invalid recording status")
    if allowed != (reason == "allowed") or paused != (reason == "paused"):
        raise ValueError("Inconsistent recording status")
    if reason == "blocked_program" and not blocked:
        raise ValueError("Missing blocked program")
    return PrivacyState(PrivacySettings(paused, blocked, clipboard_enabled),
                        RecordingStatus(allowed, reason))


class PrivacyClient(JsonRequest):
    """조회는 반복하되 설정 변경은 한 번만 전송하고 서버 확인 결과를 표시한다."""

    state_received = Signal(object, str)
    state_failed = Signal(str)
    changing = Signal()

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        """단일 요청을 사용하여 조회 응답이 설정 변경 결과를 뒤덮지 않게 한다."""
        super().__init__(port, parent)
        self.active = False
        self.operation = "read"
        self.expected: dict | None = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setSingleShot(True)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.refresh)
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def start(self) -> None:
        """서비스 호환성을 확인한 뒤 보호 상태를 즉시 조회한다."""
        self.active = True
        self.refresh()

    def refresh(self) -> None:
        """요청 하나만 유지하며 조회 완료 뒤 다음 조회를 예약한다."""
        if self.active and self.reply is None:
            self.poll_timer.stop()
            self.operation, self.expected = "read", None
            self.get(PRIVACY_PATH)

    def set_paused(self, paused: bool) -> None:
        """토글 명령 대신 목표값을 보내 재시도/중복 전달로 반전되지 않게 한다."""
        self._change("pause", PAUSED_PATH, {"paused": paused})

    def set_blocked_processes(self, names: list[str]) -> None:
        """차단 목록만 변경하여 아직 입력 중인 값이나 일시정지 설정을 섞지 않는다."""
        self._change("blocked", BLOCKED_PROCESSES_PATH,
                     {"blocked_processes": normalize_processes(names)})

    def set_clipboard_enabled(self, enabled: bool) -> None:
        """클립보드 기록 목표값만 보내며 전체 일시정지나 차단 목록을 변경하지 않는다."""
        self._change("clipboard", CLIPBOARD_SETTING_PATH, {"clipboard_enabled": enabled})

    def _change(self, operation: str, path: str, value: dict) -> None:
        """진행 중 조회는 취소하되 진행 중 쓰기는 중복 실행하지 않는다."""
        if not self.active or (self.reply is not None and self.operation != "read"):
            return
        self.poll_timer.stop()
        self.close()
        self.operation, self.expected = operation, value
        self.changing.emit()
        self.put(path, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def _received(self, payload: bytes) -> None:
        """HTTP 성공만으로 완료하지 않고 변경한 필드가 응답에 반영됐는지도 확인한다."""
        try:
            state = read_privacy(payload)
            if self.expected is not None and any(
                getattr(state.settings, key) != value for key, value in self.expected.items()
            ):
                raise ValueError("Unconfirmed settings")
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        operation = self.operation
        self.operation, self.expected = "read", None
        self.state_received.emit(state, operation)
        if self.active:
            self.poll_timer.start()

    def _failed(self, reason: str, status: int) -> None:
        """쓰기는 재전송하지 않고 조회로 실제 적용 여부를 다시 확인한다."""
        writing = self.operation != "read"
        self.operation, self.expected = "read", None
        if reason == "http" and status in (404, 405):
            message = "기능 준비 중 — Backend가 개인정보 설정을 지원하지 않습니다."
        else:
            message = {
                "timeout": "응답 시간 초과 — 상태를 다시 확인합니다.",
                "http": "서버 오류 — 상태를 다시 확인합니다.",
                "network": "연결 실패 — Backend 실행 후 상태를 확인해 주세요.",
                "content_type": "호환되지 않는 개인정보 응답 — 상태를 다시 확인합니다.",
            }[reason]
        if writing:
            message = "설정 적용 여부 미확인. " + message
        self.state_failed.emit(message)
        # 미구현 API에는 계속 요청하지 않는다. 사용자 재확인 또는 재연결로 복구한다.
        if self.active and not (reason == "http" and status in (404, 405)):
            self.poll_timer.start()

    def stop(self) -> None:
        """재연결/종료 시 조회와 응답을 취소하며 서버 설정을 되돌리지는 않는다."""
        self.active = False
        self.poll_timer.stop()
        self.close()
        self.operation, self.expected = "read", None
