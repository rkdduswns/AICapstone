"""실제 Backend의 문서 업로드·목록 API를 사용하는 가져오기 화면."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from client.documents_client import DocumentsClient
from client.theme import set_reading_text, set_role
from client.time_values import format_timestamp
from shared.document import MAX_DOCUMENT_CONTENT_LENGTH, ImportedDocument
from shared.records import ContextRecord


class DocumentsWidget(QWidget):
    """가져온 문서를 실제 작업의 열람 이력과 구분하여 표시한다."""

    record_linked = Signal(str)

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """요청 중 입력을 잠그고 파일 선택·전송·목록·본문을 연결한다."""
        super().__init__(parent)
        self.connected = self.loaded = self.busy = False
        self.rows: list[ImportedDocument] = []
        self.target_record_id: str | None = None
        self._uploading = False
        self._preferred_document_id: int | None = None
        self._completion_document_id: int | None = None
        self.client = DocumentsClient(port, self)
        self.client.documents_received.connect(self._show_rows)
        self.client.document_uploaded.connect(self._uploaded)
        self.client.documents_failed.connect(self._failed)
        self.client.upload_started.connect(self._upload_started)
        self.client.upload_progress.connect(self._upload_progress)
        layout = QVBoxLayout(self)
        description = QLabel("PDF·DOCX를 가져오거나 최근 기록에서 선택한 작업에 연결합니다.\n"
                             "문서 저장 시각과 작업 열람 시각은 별도로 보존합니다.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.target = QLabel("연결 대상 없음 · 문서만 가져옵니다.")
        self.target.setTextFormat(Qt.TextFormat.PlainText)
        self.target.setWordWrap(True)
        self.target.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.target)
        buttons = QHBoxLayout()
        self.import_button = QPushButton("문서 선택하여 가져오기")
        self.refresh_button = QPushButton("목록 새로고침")
        self.clear_target_button = QPushButton("연결 대상 해제")
        self.clear_target_button.clicked.connect(lambda: self.set_target_record(None))
        self.import_button.clicked.connect(self._choose)
        self.refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.clear_target_button)
        layout.addLayout(buttons)
        set_role(self.import_button, "primary")
        set_role(self.refresh_button, "quiet")
        set_role(self.clear_target_button, "quiet")
        self.transfer_summary = QLabel()
        self.transfer_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.transfer_summary.setWordWrap(True)
        self.transfer_summary.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred,
        )
        self.transfer_summary.hide()
        layout.addWidget(self.transfer_summary)
        self.progress = QProgressBar()
        self.progress.setAccessibleName("문서 전송 진행 상태")
        self.progress.hide()
        layout.addWidget(self.progress)
        self.completion = QLabel()
        self.completion.setTextFormat(Qt.TextFormat.PlainText)
        self.completion.setWordWrap(True)
        self.completion.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.completion.hide()
        layout.addWidget(self.completion)
        self.notice = QLabel("Backend 연결을 확인해 주세요.")
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.notice)
        self.records = QListWidget()
        self.records.currentRowChanged.connect(self._select)
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setTabChangesFocus(True)
        self.reading_splitter = QSplitter(Qt.Orientation.Vertical)
        self.reading_splitter.setChildrenCollapsible(False)
        self.reading_splitter.addWidget(self.records)
        self.reading_splitter.addWidget(self.content)
        self.reading_splitter.setStretchFactor(0, 1)
        self.reading_splitter.setStretchFactor(1, 2)
        self.reading_splitter.handle(1).setToolTip("경계를 끌어 문서 목록과 본문 높이를 조절합니다.")
        layout.addWidget(self.reading_splitter, 1)
        self._controls()

    def _controls(self) -> None:
        """진행 중 요청을 재전송하거나 연결 전 파일을 읽지 않게 한다."""
        self.import_button.setEnabled(self.connected and not self.busy)
        self.refresh_button.setEnabled(self.connected and not self.busy)
        self.clear_target_button.setEnabled(not self.busy and self.target_record_id is not None)
        self.records.setEnabled(not self.busy)

    def set_target_record(self, record: ContextRecord | None) -> bool:
        """사용자가 선택한 작업을 명시하며 진행 중 업로드의 대상을 바꾸지 않는다."""
        if self.busy:
            return False
        self.target_record_id = record.id if record is not None else None
        self.target.setText(f"연결 대상 #{record.id} · {record.window_title}" if record else
                            "연결 대상 없음 · 문서만 가져옵니다.")
        self._controls()
        return True

    def set_connected(self, connected: bool) -> None:
        """재연결·종료 시 요청과 옛 문서 본문을 모두 정리한다."""
        self.client.close()
        self.connected, self.loaded, self.busy = connected, False, False
        self._uploading = False
        self._preferred_document_id = None
        self._clear_transfer()
        self._clear_completion()
        self.set_target_record(None)
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
        if self._preferred_document_id is None:
            index = self.records.currentRow()
            self._preferred_document_id = self.rows[index].id if 0 <= index < len(self.rows) else None
        self.busy = True
        self.notice.setText("문서 목록 조회 중")
        self._controls()
        self.client.refresh()

    def _choose(self) -> None:
        """선택한 파일 하나만 전송하고 취소하면 아무 파일도 읽지 않는다."""
        path, _ = QFileDialog.getOpenFileName(self, "가져올 문서 선택", "", "문서 (*.pdf *.docx)")
        if path:
            self.upload(path)

    def upload(self, path: str, source_path: str | None = None) -> None:
        """명시적 사용자 선택에만 업로드를 실행하고 결과를 기다린다."""
        if not self.connected or self.busy:
            return
        self.busy = self._uploading = True
        self._clear_completion()
        self._clear_transfer()
        self.notice.setText("선택한 문서 확인 중")
        self._controls()
        self.client.upload(path, self.target_record_id, source_path)

    def _show_rows(self, rows: list[ImportedDocument]) -> None:
        """목록과 본문을 같은 응답으로 교체하여 오래된 선택을 표시하지 않는다."""
        if not self.connected or self._uploading:
            return
        preferred_id, self._preferred_document_id = self._preferred_document_id, None
        self.rows, self.loaded, self.busy = rows, True, False
        self.records.clear()
        self.content.clear()
        for row in rows:
            linked = f" · 작업 #{row.record_id}" if row.record_id is not None else " · 연결 없음"
            self.records.addItem(f"{row.file_name} · {format_timestamp(row.captured_at)}{linked}")
        self.notice.setText(f"가져온 문서 {len(rows)}건 · 최근 20건까지 표시")
        if rows:
            index = next((i for i, row in enumerate(rows) if row.id == preferred_id), 0)
            self.records.setCurrentRow(index)
        if self._completion_document_id not in {row.id for row in rows}:
            self._clear_completion()
        self._controls()

    def _uploaded(self, document: ImportedDocument) -> None:
        """성공 확인 후에만 새로 조회하여 서버에서 실제 저장한 목록을 표시한다."""
        if not self.connected or not self._uploading:
            return
        self.busy = self._uploading = False
        self._clear_transfer()
        self._preferred_document_id = self._completion_document_id = document.id
        linked = f"작업 #{document.record_id}에 연결됨" if document.record_id else "작업 연결 없음"
        self.completion.setText(f"가져오기 완료 · {document.file_name} · {linked}")
        self.completion.show()
        if document.record_id is not None:
            self.record_linked.emit(document.record_id)
            self.set_target_record(None)
        self.refresh()

    def _select(self, index: int) -> None:
        """일반 텍스트로 보여주고 긴 본문은 표시 범위를 명시한다."""
        self.content.clear()
        if 0 <= index < len(self.rows):
            row = self.rows[index]
            text = row.extracted_text
            header = f"연결된 파일: {row.file_path}\n\n" if row.file_path else ""
            set_reading_text(self.content, header + text[:MAX_DOCUMENT_CONTENT_LENGTH])
            if len(text) > MAX_DOCUMENT_CONTENT_LENGTH:
                self.notice.setText("본문은 처음 50,000자까지 표시합니다.")

    def _failed(self, message: str) -> None:
        """요청 실패 시 옛 결과를 현재 결과로 오인하지 않게 지우고 수동 복구를 허용한다."""
        self.busy = self._uploading = False
        self._preferred_document_id = None
        self._clear_transfer()
        self._clear_completion()
        self.rows = []
        self.records.clear()
        self.content.clear()
        self.notice.setText(message)
        self._controls()

    def _upload_started(self, name: str, size: int) -> None:
        """검증된 파일 정보와 명시적 연결 대상을 전송 중에도 화면에 유지한다."""
        if not self.connected or not self._uploading:
            return
        self.transfer_summary.setText(f"{name} · {size:,}바이트 · {self.target.text()}")
        self.transfer_summary.show()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("전송 %p%")
        self.progress.show()
        self.notice.setText("문서 전송 중")

    def _upload_progress(self, sent: int, total: int) -> None:
        """전송률과 서버 응답 대기를 구분하며 추출·저장 진행률은 만들어내지 않는다."""
        if not self.connected or not self._uploading:
            return
        if total > 0 and sent < total:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, sent * 100 // total)))
            self.progress.setFormat("전송 %p%")
            self.notice.setText("문서 전송 중")
        elif total > 0:
            self.progress.setRange(0, 0)
            self.notice.setText("서버 처리 결과 확인 중")
        else:
            self.progress.setRange(0, 0)
            self.notice.setText("문서 전송 중 · 전송량 확인 대기")
        self.progress.show()

    def _clear_transfer(self) -> None:
        """성공·실패·재연결에서 진행 표시와 파일 정보를 함께 지운다."""
        self.progress.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.transfer_summary.clear()
        self.transfer_summary.hide()

    def _clear_completion(self) -> None:
        """새 요청이나 오류 뒤에 과거 문서의 완료 표시가 남지 않게 한다."""
        self._completion_document_id = None
        self.completion.clear()
        self.completion.hide()

    def closeEvent(self, event: QCloseEvent) -> None:
        """독립 문서 화면을 닫아도 진행 요청과 나중에 올 표시 신호를 정리한다."""
        self.set_connected(False)
        super().closeEvent(event)
