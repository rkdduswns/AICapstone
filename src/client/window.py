"""Backend 연결과 현재 프로그램·창 제목·수집 상태를 표시하는 화면."""

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from client.activity_client import ActivityClient
from client.backend_client import BackendClient
from shared.activity import CurrentActivity
from shared.protocol import DEFAULT_PORT


def display_label(text: str) -> QLabel:
    """외부 문자열을 HTML로 해석하지 않고 긴 문자열도 창 너비 안에서 표시한다."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


class MainWindow(QWidget):
    """감지 로직 없이 검증된 현재 상태만 표시하고 실패 시 이전 창 정보를 비운다."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        super().__init__()
        self.setWindowTitle("ContextTrace — 현재 작업")
        self.resize(620, 440)
        layout = QVBoxLayout(self)
        connection = QGroupBox("Backend 연결 · 마지막 확인 결과")
        connection_layout = QVBoxLayout(connection)
        self.status = display_label("미확인")
        self.checked_at = display_label("마지막 확인: 없음")
        self.button = QPushButton("연결 확인")
        connection_layout.addWidget(self.status)
        connection_layout.addWidget(self.checked_at)
        connection_layout.addWidget(self.button)
        layout.addWidget(connection)

        activity = QGroupBox("현재 활성 창")
        activity_layout = QFormLayout(activity)
        self.collection_status = display_label("대기 — Backend 연결을 확인해 주세요.")
        self.application = display_label("—")
        self.process = display_label("—")
        # 긴 제목과 여러 줄을 줄바꿈/스크롤로 확인하며 서식이나 링크로 실행하지 않는다.
        self.window_title = QPlainTextEdit()
        self.window_title.setReadOnly(True)
        self.window_title.setTabChangesFocus(True)
        self.window_title.setMaximumHeight(96)
        self.window_title.setPlainText("—")
        self.activity_updated_at = display_label("마지막 정상 수신: 없음")
        activity_layout.addRow("수집 상태", self.collection_status)
        activity_layout.addRow("프로그램", self.application)
        activity_layout.addRow("프로세스", self.process)
        activity_layout.addRow("창 제목", self.window_title)
        activity_layout.addRow(self.activity_updated_at)
        layout.addWidget(activity)
        layout.addStretch()

        self.activity = ActivityClient(port, self)
        self.activity.activity_received.connect(self._show_activity)
        self.activity.activity_failed.connect(self._clear_activity)
        self.backend = BackendClient(port, self)
        self.backend.result.connect(self._show_result)
        self.backend.connection_changed.connect(self._connection_changed)
        self.button.clicked.connect(self.check)

    def check(self) -> None:
        """연결 재확인 동안 이전 조회를 취소해 늦은 결과가 섞이지 않게 한다."""
        if self.backend.reply is not None:
            return
        self.activity.stop()
        self._clear_activity("대기 — Backend 연결 확인 중")
        self.status.setText("연결 중")
        self.button.setEnabled(False)
        self.backend.check()

    def _show_result(self, message: str) -> None:
        """연결 결과와 확인 시각은 현재 창 수신 상태와 별도로 표시한다."""
        self.status.setText(message)
        self.checked_at.setText("마지막 확인: " + self._now())
        self.button.setEnabled(True)

    def _connection_changed(self, connected: bool) -> None:
        """표시 문구를 분석하는 대신 검증 결과로 자동 조회 여부를 결정한다."""
        if connected:
            self._clear_activity("확인 중 — 현재 창 정보를 기다리고 있습니다.")
            self.activity.start()
        else:
            self._clear_activity("수신 중단 — Backend 연결을 확인해 주세요.")

    def _show_activity(self, activity: CurrentActivity) -> None:
        """새 스냅샷으로 교체하며 비수집 상태에서는 이전 프로그램/제목을 지운다."""
        messages = {
            "collecting": "감지 중 — 현재 창 정보 자동 갱신",
            "no_active_window": "대기 — 활성 창 없음",
            "unsupported": "수집 불가 — 지원하지 않는 창 또는 환경",
            "error": "감지 오류 — 다음 조회에서 다시 확인합니다.",
        }
        if activity.window is None:
            self._clear_activity(messages[activity.collection_status])
        else:
            self.collection_status.setText(messages[activity.collection_status])
            window = activity.window
            if self.application.text() != window.application:
                self.application.setText(window.application)
            process = f"{window.process_name} · PID {window.process_id}"
            if self.process.text() != process:
                self.process.setText(process)
            title = window.window_title or "(제목 없음)"
            # 동일 창의 반복 응답은 사용자가 선택한 텍스트/스크롤 위치를 초기화하지 않는다.
            if self.window_title.toPlainText() != title:
                self.window_title.setPlainText(title)
        self.activity_updated_at.setText("마지막 정상 수신: " + self._now())

    def _clear_activity(self, message: str) -> None:
        """이전 성공 데이터를 현재 감지 결과로 오인하지 않도록 즉시 비운다."""
        self.collection_status.setText(message)
        self.application.setText("—")
        self.process.setText("—")
        self.window_title.setPlainText("—")

    @staticmethod
    def _now() -> str:
        """수신 시각을 표시하며 작업 시작 시각이나 활성 시간으로 사용하지 않는다."""
        return QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")

    def closeEvent(self, event: QCloseEvent) -> None:
        """화면 종료 이후 자동 조회나 응답 콜백이 남지 않도록 두 요청을 정리한다."""
        self.activity.stop()
        self.backend.close()
        super().closeEvent(event)
