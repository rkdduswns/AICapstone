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
from client.theme import set_role
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
        self.server_summary = plain_label("서버 확인 설정 · 미확인")
        layout.addWidget(self.server_summary)
        self.checked_at = plain_label("마지막 상태 확인: 없음")
        self.refresh_button = QPushButton("보호 상태 다시 확인")
        self.refresh_button.clicked.connect(self.client.refresh)
        confirmation_row = QHBoxLayout()
        confirmation_row.addWidget(self.checked_at, 1)
        confirmation_row.addWidget(self.refresh_button)
        layout.addLayout(confirmation_row)
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
        self.applied_details_button = QPushButton("서버 적용 목록 보기")
        self.applied_details_button.setCheckable(True)
        self.applied_details_button.setAccessibleName("확인된 차단 프로그램 목록 표시")
        program_layout.addWidget(self.applied_details_button)
        self.applied_programs = QPlainTextEdit()
        self.applied_programs.setReadOnly(True)
        self.applied_programs.setTabChangesFocus(True)
        self.applied_programs.setMaximumHeight(90)
        self.applied_programs.setAccessibleName("서버가 확인한 차단 프로그램 목록")
        self.applied_programs.hide()
        self.applied_details_button.toggled.connect(self.applied_programs.setVisible)
        program_layout.addWidget(self.applied_programs)
        program_layout.addWidget(plain_label("편집할 차단 목록 · 실행 파일 이름을 한 줄에 하나씩 입력"))
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
        self.reset_button = QPushButton("확인된 목록으로 되돌리기")
        self.reset_button.setToolTip("편집 중인 입력만 확인된 목록으로 되돌립니다. 서버 설정은 바꾸지 않습니다.")
        self.reset_button.clicked.connect(self._reset_draft)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.reset_button)
        program_layout.addLayout(buttons)
        self.notice = plain_label("Backend 연결을 확인해 주세요.")
        layout.addWidget(self.notice)
        set_role(self.apply_button, "primary")
        for button in (self.refresh_button, self.reset_button, self.applied_details_button):
            set_role(button, "quiet")
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
        self._show_confirmed_settings(confirmed, writing)
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
        self._show_draft_summary(confirmed)

    def _show_confirmed_settings(self, confirmed: bool, writing: bool) -> None:
        """현재 확인값만 개요·접힌 목록으로 표시하며 감지나 일시정지 해제를 저장 허용으로 해석하지 않는다."""
        self.applied_details_button.setEnabled(confirmed)
        self.applied_programs.setEnabled(confirmed)
        if not confirmed:
            self.server_summary.setText("서버 확인 설정 · 적용 결과 확인 중" if writing
                                        else "서버 확인 설정 · 미확인")
            self.applied_programs.clear()
            self.applied_programs.setPlaceholderText("서버 설정을 확인한 뒤 목록을 볼 수 있습니다.")
            self.applied_details_button.setChecked(False)
            self.applied_programs.hide()
            return
        settings = self.state.settings
        paused = "켜짐" if settings.paused else "꺼짐"
        clipboard = ("미지원" if settings.clipboard_enabled is None else
                     "켜짐" if settings.clipboard_enabled else "꺼짐")
        urls = ("미지원" if settings.blocked_urls is None
                else f"서버 규칙 {len(settings.blocked_urls)}개")
        self.server_summary.setText(
            f"서버 확인 설정 · 일시정지 설정 {paused} · 클립보드 기록 {clipboard}\n"
            f"차단 프로그램 {len(settings.blocked_processes)}개 · URL 차단 {urls}")
        if self.applied_programs.toPlainText() != self.applied_text:
            self.applied_programs.setPlainText(self.applied_text)
        self.applied_programs.setPlaceholderText("현재 확인된 차단 프로그램이 없습니다.")
        self.applied_programs.setVisible(self.applied_details_button.isChecked())

    def _show_draft_summary(self, confirmed: bool) -> None:
        """현재 적용 목록과 편집 입력의 차이를 알리되 초안을 저장된 보호 설정으로 표시하지 않는다."""
        prefix = "미적용 입력 있음 · " if self.dirty else ""
        if not confirmed:
            self.draft_status.setText(prefix + "서버 적용값 미확인")
            return
        count = len(self.state.settings.blocked_processes)
        if not self.dirty:
            self.draft_status.setText(f"서버 적용 목록 {count}개 · 미적용 변경 없음")
            return
        try:
            draft = normalize_processes([
                line for line in self.editor.toPlainText().splitlines() if line.strip()
            ])
        except ValueError:
            self.draft_status.setText(prefix + "입력 형식 확인 필요")
            return
        applied = set(self.state.settings.blocked_processes)
        added, removed = len(set(draft) - applied), len(applied - set(draft))
        difference = (f"추가 {added}개 · 제외 {removed}개" if added or removed
                      else "목록 내용 같음 · 표기 차이 있음")
        self.draft_status.setText(prefix + difference + f" · 서버 적용 {count}개")
