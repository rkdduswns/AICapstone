"""선택한 작업에 저장된 복사 텍스트의 읽기 전용 상세 화면."""

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from client.clipboard_client import ClipboardClient
from client.time_values import format_timestamp
from shared.clipboard import RecordClipboard


class ClipboardWidget(QWidget):
    """본문은 상세 탭 진입 시만 요청하고 작업 선택이 바뀌면 즉시 비운다."""

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """시간별 항목 선택과 일반 텍스트 표시를 준비한다."""
        super().__init__(parent)
        self.record_id: str | None = None
        self.loaded = False
        self.entries = []
        self.client = ClipboardClient(port, self)
        self.client.entries_received.connect(self._show_entries)
        self.client.entries_failed.connect(self._show_error)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.status = QLabel("작업 기록을 선택해 주세요.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.button = QPushButton("복사 텍스트 새로고침")
        self.button.setEnabled(False)
        self.button.clicked.connect(self.refresh)
        header.addWidget(self.status, 1)
        header.addWidget(self.button)
        layout.addLayout(header)
        self.selector = QComboBox()
        self.selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.selector.currentIndexChanged.connect(self._select_entry)
        layout.addWidget(self.selector)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setTabChangesFocus(True)
        self.text.setPlaceholderText("이 작업에 저장된 복사 텍스트가 여기에 표시됩니다.")
        layout.addWidget(self.text, 1)
        self.updated_at = QLabel("마지막 정상 조회: 없음")
        layout.addWidget(self.updated_at)

    def set_record(self, record_id: str | None) -> None:
        """다른 작업의 복사 내용과 늦은 응답을 새 작업 상세에 남기지 않는다."""
        if record_id == self.record_id:
            return
        self.client.close()
        self.record_id = record_id
        self.loaded = False
        self._clear_entries()
        self.updated_at.setText("마지막 정상 조회: 없음")
        self.status.setText("복사 텍스트 조회 대기" if record_id else "작업 기록을 선택해 주세요.")
        self.button.setEnabled(record_id is not None)

    def load_if_needed(self) -> None:
        """탭 최초 진입 시 요청하며 정상 수신 뒤에는 수동 새로고침을 사용한다."""
        if not self.loaded:
            self.refresh()

    def refresh(self) -> None:
        """중복 조회를 막고 요청 전에 기존 본문을 지운다."""
        if self.record_id is None or self.client.reply is not None:
            return
        self._clear_entries()
        self.loaded = False
        self.status.setText("복사 텍스트 조회 중")
        self.button.setEnabled(False)
        self.client.fetch(self.record_id)

    def _show_entries(self, result: RecordClipboard) -> None:
        """현재 선택과 일치하는 응답만 표시하고 빈 목록과 이전 항목 존재를 구분한다."""
        if result.record_id != self.record_id:
            return
        self.entries = result.entries
        self.loaded = True
        for index, entry in enumerate(self.entries):
            self.selector.addItem(f"{index + 1}. {format_timestamp(entry.copied_at)}")
        if not self.entries:
            message = "이 작업에 저장된 복사 텍스트가 없습니다."
        else:
            message = f"복사 텍스트 {len(self.entries)}건 · 최신순"
        if result.has_more:
            message += " · 이전 항목 더 있음 (최근 20건 표시)"
        self.status.setText(message)
        self.updated_at.setText("마지막 정상 조회: "
                               + QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))
        self.button.setEnabled(True)

    def _select_entry(self, index: int) -> None:
        """원문 공백·줄바꿈을 유지하고 HTML이나 링크로 실행하지 않는다."""
        self.text.setPlainText(self.entries[index].text if 0 <= index < len(self.entries) else "")

    def _clear_entries(self) -> None:
        """항목과 본문을 함께 비워 오류 뒤 이전 내용을 정상 결과로 오인하지 않게 한다."""
        self.entries = []
        self.selector.clear()
        self.text.clear()

    def _show_error(self, message: str) -> None:
        """빈 결과와 실패를 구분하고 사용자가 다시 요청할 수 있게 한다."""
        self._clear_entries()
        self.loaded = False
        self.status.setText(message)
        self.button.setEnabled(self.record_id is not None)
