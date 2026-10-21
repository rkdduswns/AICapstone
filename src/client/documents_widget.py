"""실제 Backend의 문서 업로드·목록 API를 사용하는 가져오기 화면."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from client.documents_client import DocumentsClient
from client.time_values import format_timestamp
from shared.document import MAX_DOCUMENT_CONTENT_LENGTH, ImportedDocument


class DocumentsWidget(QWidget):
    """가져온 문서를 실제 작업의 열람 이력과 구분하여 표시한다."""

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """요청 중 입력을 잠그고 파일 선택·전송·목록·본문을 연결한다."""
        super().__init__(parent)
        self.connected = self.loaded = self.busy = False
        self.rows: list[ImportedDocument] = []
        self.client = DocumentsClient(port, self)
        self.client.documents_received.connect(self._show_rows)
        self.client.document_uploaded.connect(self._uploaded)
        self.client.documents_failed.connect(self._failed)
        layout = QVBoxLayout(self)
        description = QLabel("선택한 PDF·DOCX를 가져와 저장된 본문을 확인합니다.\n"
                             "표시 시각은 가져온 시각이며, 작업 열람 이력과 자동으로 연결되지 않습니다.")
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = QHBoxLayout()
        self.import_button = QPushButton("문서 선택하여 가져오기")
        self.refresh_button = QPushButton("목록 새로고침")
        self.import_button.clicked.connect(self._choose)
        self.refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.refresh_button)
        layout.addLayout(buttons)
        self.notice = QLabel("Backend 연결을 확인해 주세요.")
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.notice)
        self.records = QListWidget()
        self.records.currentRowChanged.connect(self._select)
        layout.addWidget(self.records, 1)
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        layout.addWidget(self.content, 2)
        self._controls()

    def _controls(self) -> None:
        """진행 중 요청을 재전송하거나 연결 전 파일을 읽지 않게 한다."""
        self.import_button.setEnabled(self.connected and not self.busy)
        self.refresh_button.setEnabled(self.connected and not self.busy)

    def set_connected(self, connected: bool) -> None:
        """재연결·종료 시 요청과 옛 문서 본문을 모두 정리한다."""
        self.client.close()
        self.connected, self.loaded, self.busy = connected, False, False
        self.rows = []
        self.records.clear()
        self.content.clear()
        self.notice.setText("문서 목록을 조회할 수 있습니다." if connected
                            else "Backend 연결을 확인해 주세요.")
        self._controls()

    def load_if_needed(self) -> None:
        """사용자가 탭을 처음 열 때만 목록을 자동 조회한다."""
        if not self.loaded:
            self.refresh()

    def refresh(self) -> None:
        """저장 내용만 조회하며 기존 파일을 다시 업로드하지 않는다."""
        if not self.connected or self.busy:
            return
        self.busy = True
        self.notice.setText("문서 목록 조회 중")
        self._controls()
        self.client.refresh()

    def _choose(self) -> None:
        """선택한 파일 하나만 전송하고 취소하면 아무 파일도 읽지 않는다."""
        path, _ = QFileDialog.getOpenFileName(self, "가져올 문서 선택", "", "문서 (*.pdf *.docx)")
        if path:
            self.upload(path)

    def upload(self, path: str) -> None:
        """명시적 사용자 선택에만 업로드를 실행하고 결과를 기다린다."""
        if not self.connected or self.busy:
            return
        self.busy = True
        self.notice.setText("문서를 가져오는 중")
        self._controls()
        self.client.upload(path)

    def _show_rows(self, rows: list[ImportedDocument]) -> None:
        """목록과 본문을 같은 응답으로 교체하여 오래된 선택을 표시하지 않는다."""
        self.rows, self.loaded, self.busy = rows, True, False
        self.records.clear()
        self.content.clear()
        for row in rows:
            self.records.addItem(f"{row.file_name} · {format_timestamp(row.captured_at)}")
        self.notice.setText(f"가져온 문서 {len(rows)}건 · 최근 20건까지 표시")
        if rows:
            self.records.setCurrentRow(0)
        self._controls()

    def _uploaded(self, document: ImportedDocument) -> None:
        """성공 확인 후에만 새로 조회하여 서버에서 실제 저장한 목록을 표시한다."""
        self.busy = False
        self.refresh()

    def _select(self, index: int) -> None:
        """일반 텍스트로 보여주고 긴 본문은 표시 범위를 명시한다."""
        self.content.clear()
        if 0 <= index < len(self.rows):
            text = self.rows[index].extracted_text
            self.content.setPlainText(text[:MAX_DOCUMENT_CONTENT_LENGTH])
            if len(text) > MAX_DOCUMENT_CONTENT_LENGTH:
                self.notice.setText("본문은 처음 50,000자까지 표시합니다.")

    def _failed(self, message: str) -> None:
        """요청 실패 시 옛 결과를 현재 결과로 오인하지 않게 지우고 수동 복구를 허용한다."""
        self.busy = False
        self.rows = []
        self.records.clear()
        self.content.clear()
        self.notice.setText(message)
        self._controls()
