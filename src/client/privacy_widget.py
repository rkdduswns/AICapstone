"""개인정보 설정 입력과 서버에서 확인한 보호 상태를 분리해 표시한다."""

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from client.privacy_client import PrivacyClient, normalize_processes
from client.url_rules_widget import UrlRulesWidget
from shared.privacy import PrivacyState


def plain_label(text: str) -> QLabel:
    """서버/입력 관련 문구를 일반 텍스트로 표시하고 창 너비를 유지한다."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


class PrivacyWidget(QWidget):
    """입력 초안은 자동 조회로 덮어쓰지 않고 실제 적용된 상태만 제어 버튼에 사용한다."""

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """항상 보이는 상태/일시정지 버튼과 탭 안의 목록 편집 화면을 준비한다."""
        super().__init__(parent)
        self.connected = False
        self.state: PrivacyState | None = None
        self.dirty = False
        self.applied_text = ""
        self.client = PrivacyClient(port, self)
        self.client.state_received.connect(self._show_state)
        self.client.state_failed.connect(self._show_error)
        self.client.changing.connect(self._changing)
        # MainWindow가 이 두 위젯을 탭 바깥에 배치해 어느 화면에서든 제어하게 한다.
        self.summary = plain_label("기록 상태 미확인")
        self.toggle = QPushButton("기록 일시정지")
        self.toggle.setEnabled(False)
        self.toggle.clicked.connect(self._toggle)
        layout = QVBoxLayout(self)
        layout.addWidget(plain_label(
            "차단 목록과 기록 상태는 Backend에서 적용·판정합니다.\n"
            "현재 창 감지 표시는 기록 저장 여부와 별개입니다."))
        self.checked_at = plain_label("마지막 상태 확인: 없음")
        layout.addWidget(self.checked_at)
        self.refresh_button = QPushButton("보호 상태 다시 확인")
        self.refresh_button.clicked.connect(self.client.refresh)
        layout.addWidget(self.refresh_button)
        clipboard_row = QHBoxLayout()
        self.clipboard_status = plain_label("클립보드 기록 · 미확인")
        self.clipboard_toggle = QPushButton("클립보드 기록 켜기")
        self.clipboard_toggle.clicked.connect(self._toggle_clipboard)
        clipboard_row.addWidget(self.clipboard_status, 1)
        clipboard_row.addWidget(self.clipboard_toggle)
        layout.addLayout(clipboard_row)
        layout.addWidget(plain_label("클립보드 기록을 켜도 전체 일시정지와 차단 설정이 우선합니다."))
        # 프로그램과 URL 초안은 독립적으로 적용한다. 안쪽 탭으로 나눠 창 높이를 유지한다.
        self.rule_tabs = QTabWidget()
        programs = QWidget()
        program_layout = QVBoxLayout(programs)
        self.rule_tabs.addTab(programs, "프로그램 차단")
        self.urls = UrlRulesWidget()
        self.urls.apply_requested.connect(self.client.set_blocked_urls)
        self.rule_tabs.addTab(self.urls, "URL 차단")
        layout.addWidget(self.rule_tabs, 1)
        program_layout.addWidget(plain_label("차단 프로그램 · 실행 파일 이름을 한 줄에 하나씩 입력"))
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("예: chrome.exe\n비밀번호관리자.exe")
        self.editor.setTabChangesFocus(True)
        self.editor.setMaximumHeight(180)
        self.editor.textChanged.connect(self._edited)
        program_layout.addWidget(self.editor, 1)
        self.draft_status = plain_label("서버 설정을 확인한 뒤 적용할 수 있습니다.")
        self.validation = plain_label("")
        program_layout.addWidget(self.draft_status)
        program_layout.addWidget(self.validation)
        buttons = QHBoxLayout()
        self.apply_button = QPushButton("차단 목록 적용")
        self.apply_button.clicked.connect(self._apply)
        self.reset_button = QPushButton("입력 되돌리기")
        self.reset_button.clicked.connect(self._reset_draft)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.reset_button)
        program_layout.addLayout(buttons)
        self.notice = plain_label("Backend 연결을 확인해 주세요.")
        layout.addWidget(self.notice)
        self._update_controls()

    def set_connected(self, connected: bool) -> None:
        """재연결 때 이전 확인값을 버리되 아직 적용하지 않은 입력은 유지한다."""
        self.client.stop()
        self.connected = connected
        self.state = None
        if not self.dirty:
            self._set_editor("")
        self.applied_text = ""
        self.summary.setText("기록 상태 미확인")
        self.checked_at.setText("마지막 상태 확인: 없음")
        self.notice.setText("보호 상태 확인 중" if connected else "Backend 연결을 확인해 주세요.")
        self._update_controls()
        if connected:
            self.client.start()

    def _toggle(self) -> None:
        """서버가 확인한 일시정지 값의 반대값만 전송하고 입력 중 목록은 보내지 않는다."""
        if self.state is not None:
            self.client.set_paused(not self.state.settings.paused)

    def _toggle_clipboard(self) -> None:
        """지원되는 서버에서 확인한 값만 반전하며 실제 OS 클립보드를 읽지 않는다."""
        if self.state is not None and self.state.settings.clipboard_enabled is not None:
            self.client.set_clipboard_enabled(not self.state.settings.clipboard_enabled)

    def _apply(self) -> None:
        """빈 목록도 명시적으로 적용하며 잘못된 실행 파일 이름은 전송 전에 안내한다."""
        if self.state is None or self.client.operation != "read":
            return
        try:
            names = normalize_processes([
                line for line in self.editor.toPlainText().splitlines() if line.strip()
            ])
        except ValueError as error:
            self.validation.setText(str(error))
            return
        self.validation.clear()
        self.client.set_blocked_processes(names)

    def _edited(self) -> None:
        """입력과 적용값을 비교하며 폴링 도중에도 사용자의 초안을 보존한다."""
        self.dirty = self.editor.toPlainText() != self.applied_text
        self.validation.clear()
        self._update_controls()

    def _set_editor(self, text: str) -> None:
        """서버 값을 채울 때 사용자 편집 신호와 커서 초기화를 불필요하게 반복하지 않는다."""
        if self.editor.toPlainText() != text:
            self.editor.blockSignals(True)
            self.editor.setPlainText(text)
            self.editor.blockSignals(False)

    def _reset_draft(self) -> None:
        """현재 확인된 서버 목록으로만 입력을 복원하며 서버에는 쓰지 않는다."""
        if self.state is not None:
            self._set_editor(self.applied_text)
            self.dirty = False
            self.validation.clear()
            self._update_controls()

    def _changing(self) -> None:
        """서버 응답 전에는 일시정지나 차단이 성공했다고 표시하지 않는다."""
        self.state = None
        self.summary.setText("기록 상태 확인 중 · 설정 적용 요청 중")
        self.notice.setText("설정 적용 요청 중 — 서버 확인을 기다리고 있습니다.")
        self._update_controls()

    def _show_state(self, state: PrivacyState, operation: str) -> None:
        """확인된 설정·판정만 표시하고 별도 필드 변경 중의 입력 초안은 보존한다."""
        self.state = state
        self.urls.show_rules(state.settings.blocked_urls, operation)
        self.applied_text = "\n".join(state.settings.blocked_processes)
        if not self.dirty or operation == "blocked":
            self._set_editor(self.applied_text)
        self.dirty = self.editor.toPlainText() != self.applied_text
        messages = {
            "allowed": "기록 가능", "paused": "기록 일시정지됨",
            "blocked_program": "기록 차단 · 차단 프로그램",
            "blocked_url": "기록 차단 · 차단 URL",
            "sensitive_content": "기록 차단 · 민감 문자열",
            "no_active_window": "기록 대기 · 활성 창 없음",
            "unsupported": "기록 불가 · 미지원 환경", "error": "기록 불가 · 보호 검사 오류",
        }
        self.summary.setText(messages[state.recording.reason] + " · 마지막 확인 결과")
        self.toggle.setText("기록 재개" if state.settings.paused else "기록 일시정지")
        self.checked_at.setText("마지막 상태 확인: "
                               + QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))
        self.notice.setText("서버 설정을 확인했습니다." if operation == "read"
                            else "설정 적용을 확인했습니다.")
        self._update_controls()

    def _show_error(self, message: str) -> None:
        """통신 실패를 보호 성공으로 오인하지 않도록 기존 판정을 즉시 무효화한다."""
        self.state = None
        self.summary.setText("기록 상태 미확인 · 개인정보 보호 탭에서 확인")
        self.notice.setText(message)
        self._update_controls()

    def _update_controls(self) -> None:
        """설정 쓰기 중 입력을 잠그고 유효한 서버 상태가 있을 때만 변경을 허용한다."""
        writing = self.client.operation != "read"
        confirmed = self.connected and self.state is not None and not writing
        self.urls.set_availability(confirmed,
                                   self.state is not None and self.state.settings.blocked_urls is not None)
        self.toggle.setEnabled(confirmed)
        self.editor.setEnabled(self.connected and not writing)
        self.refresh_button.setEnabled(self.connected and not writing)
        self.apply_button.setEnabled(confirmed and self.dirty)
        self.reset_button.setEnabled(confirmed and self.dirty)
        enabled = self.state.settings.clipboard_enabled if self.state else None
        self.clipboard_toggle.setEnabled(confirmed and enabled is not None)
        self.clipboard_toggle.setText("클립보드 기록 끄기" if enabled else "클립보드 기록 켜기")
        clipboard_status = ("미확인" if self.state is None else "기능 미지원")
        if enabled is not None:
            clipboard_status = "켜짐" if enabled else "꺼짐"
        self.clipboard_status.setText("클립보드 기록 · " + clipboard_status)
        if self.state is None:
            self.toggle.setText("기록 일시정지")
        count = len(self.state.settings.blocked_processes) if self.state else None
        self.draft_status.setText(
            ("미적용 입력 있음 · " if self.dirty else "")
            + (f"서버 차단 목록 {count}개" if count is not None else "서버 설정 확인 필요"))
