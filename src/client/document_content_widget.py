"""선택 작업의 저장 문서 본문과 추출 당시 출처를 보여주는 읽기 전용 화면."""

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from client.document_content_client import DocumentContentClient
from client.time_values import format_timestamp
from shared.document import LocalDocument, RecordDocumentContent
from shared.records import ContextRecord


class DocumentContentWidget(QWidget):
    """본문은 상세 탭에서만 읽고, 선택이 바뀌거나 조회가 실패하면 이전 내용을 비운다."""

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """조회 상태, 파일 출처, 원문을 분리해 일부 본문과 빈 결과를 명확히 표시한다."""
        super().__init__(parent)
        self.record_id: str | None = None
        self.document: LocalDocument | None = None
        self.loaded = False
        self.client = DocumentContentClient(port, self)
        self.client.content_received.connect(self._show_content)
        self.client.content_failed.connect(self._show_error)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.status = QLabel("작업 기록을 선택해 주세요.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.button = QPushButton("문서 본문 새로고침")
        self.button.setEnabled(False)
        self.button.clicked.connect(self.refresh)
        header.addWidget(self.status, 1)
        header.addWidget(self.button)
        layout.addLayout(header)
        # 긴 파일 경로 때문에 앱 전체가 커지지 않도록 출처도 높이가 고정된 텍스트 영역을 쓴다.
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setTabChangesFocus(True)
        self.source.setFixedHeight(64)
        self.source.setPlaceholderText("본문 추출 당시의 파일 경로·유형·시각")
        layout.addWidget(self.source)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setTabChangesFocus(True)
        self.text.setPlaceholderText("이 작업에 저장된 문서 본문이 여기에 표시됩니다.")
        layout.addWidget(self.text, 1)
        self.updated_at = QLabel("마지막 정상 조회: 없음")
        layout.addWidget(self.updated_at)

    def set_record(self, record: ContextRecord | None) -> None:
        """작업 ID와 파일 출처를 함께 비교해 같은 ID의 파일 변경도 새 선택으로 처리한다."""
        identifier = record.id if record else None
        document = record.document if record else None
        if (identifier, document) == (self.record_id, self.document):
            return
        self.client.close()
        self.record_id, self.document = identifier, document
        self.loaded = False
        self._clear_content()
        self.updated_at.setText("마지막 정상 조회: 없음")
        if identifier is None:
            message = "작업 기록을 선택해 주세요."
        elif document is None:
            message = "파일 출처가 없습니다. 일반 작업·구형 기록은 문서 본문을 요청하지 않습니다."
        else:
            message = "문서 본문 조회 대기"
        self.status.setText(message)
        self.button.setEnabled(self._can_fetch())

    def _can_fetch(self) -> bool:
        """목록 응답에 파일 출처가 확인된 작업만 상세 조회 대상으로 삼는다."""
        return self.record_id is not None and self.document is not None

    def load_if_needed(self) -> None:
        """탭 최초 진입 또는 실패 뒤 재진입 때 조회하며 성공한 본문을 반복해서 요청하지 않는다."""
        if not self.loaded:
            self.refresh()

    def refresh(self) -> None:
        """같은 요청의 중복 실행을 막고 응답 대기 중 이전 본문을 정상 결과처럼 남기지 않는다."""
        if not self._can_fetch() or self.client.reply is not None:
            return
        self._clear_content()
        self.loaded = False
        self.status.setText("저장된 문서 본문 조회 중")
        self.button.setEnabled(False)
        self.client.fetch(self.record_id, self.document)

    def _show_content(self, result: RecordDocumentContent) -> None:
        """현재 작업의 본문만 표시하고 추출 시각과 Client 조회 시각을 구분한다."""
        if result.record_id != self.record_id:
            return
        self._clear_content()
        self.loaded = True
        content = result.content
        if content is None:
            self.status.setText("이 작업에 저장된 문서 본문이 없습니다.")
        else:
            self.source.setPlainText(
                f"{content.document.file_type.upper()} · {content.document.file_path}\n"
                f"추출 시각: {format_timestamp(content.captured_at)}")
            # HTML 파싱/외부 리소스 로드를 하지 않는다. 태그 모양의 원문도 글자로만 표시한다.
            self.text.setPlainText(content.text)
            message = f"저장된 문서 본문 · {len(content.text):,}자"
            if content.truncated:
                message += " · 길이 제한으로 일부만 저장됨"
            self.status.setText(message)
        self.updated_at.setText("마지막 정상 조회: "
                               + QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))
        self.button.setEnabled(self._can_fetch())

    def _clear_content(self) -> None:
        """본문과 해당 본문의 출처를 함께 비워 서로 다른 조회 결과가 섞이지 않게 한다."""
        self.source.clear()
        self.text.clear()

    def _show_error(self, message: str) -> None:
        """조회 실패는 빈 본문과 구분하고 이전 텍스트를 지운 뒤 수동 재조회를 허용한다."""
        self._clear_content()
        self.loaded = False
        self.status.setText(message)
        self.button.setEnabled(self._can_fetch())
