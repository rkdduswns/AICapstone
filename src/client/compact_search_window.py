"""검색 입력에서 요약과 근거까지 한 창에서 펼치는 Client 미리보기."""

from dataclasses import dataclass
from math import ceil
from typing import Literal

from PySide6.QtCore import QRect, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QKeySequence,
    QResizeEvent,
    QShortcut,
    QShowEvent,
    QTextCursor,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from client.search_presentation import RESULT_ORDERS, chunk_detail, chunk_source, ordered_chunks
from client.window_geometry import fit_window
from shared.search_data import DocumentChunk


@dataclass(frozen=True)
class CompactAnswer:
    """미리보기 공급자가 건네는 화면 값과 검증된 근거. HTTP 규격과 분리한다."""

    status: Literal["answer", "empty", "insufficient", "error", "unavailable"]
    summary: str = ""
    full_answer: str = ""
    evidence: tuple[DocumentChunk, ...] = ()


def _plain_label(text: str = "") -> QLabel:
    """긴 URL과 모델 텍스트를 평문으로 표시하고 창의 최소 너비를 키우지 않는다."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


class CompactSearchWindow(QWidget):
    """현재 요청의 결과만 표시하고 접은 영역을 창 크기 계산에서 제외한다."""

    search_requested = Signal(int, str)
    search_cancelled = Signal(int)
    preferred_size_changed = Signal(QSize)

    def __init__(self) -> None:
        """기본 입력과 필요할 때만 표시하는 결과 영역을 같은 창에 둔다."""
        super().__init__()
        self.setWindowTitle("ContextTrace — 검색 미리보기")
        self._view = "compact"
        self._result: CompactAnswer | None = None
        self._pending_id: int | None = None
        self._request_id = 0
        self._reveal_on_completion = True
        self._notice = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        query_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setAccessibleName("검색 문장")
        self.query.setPlaceholderText("기억나는 내용을 검색해 보세요")
        self.search_button = QPushButton("검색")
        query_row.addWidget(self.query, 1)
        query_row.addWidget(self.search_button)
        layout.addLayout(query_row)
        controls = QHBoxLayout()
        self.status = _plain_label()
        self.connection_button = QPushButton("연결 미확인")
        self.connection_button.setFlat(True)
        self.connection_button.setAccessibleName("Backend 연결 및 기록 상태")
        self.connection_button.hide()
        self.evidence_button = QPushButton("근거 보기")
        self.results_button = QPushButton("결과 보기")
        self.management_button = QPushButton("관리")
        self.management_button.hide()
        controls.addWidget(self.connection_button)
        controls.addStretch(1)
        controls.addWidget(self.evidence_button)
        controls.addWidget(self.results_button)
        controls.addWidget(self.management_button)
        layout.addLayout(controls)
        layout.addWidget(self.status)

        self.empty_message = _plain_label()
        layout.addWidget(self.empty_message)
        self.summary_panel = QWidget()
        summary_layout = QVBoxLayout(self.summary_panel)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_heading = _plain_label("요약 답변")
        self.summary = _plain_label()
        self.summary.setWordWrap(False)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_button = QPushButton("전체 답변·근거 보기")
        summary_layout.addWidget(self.summary_heading)
        summary_layout.addWidget(self.summary)
        summary_layout.addWidget(self.detail_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.summary_panel, 1)

        self.detail_panel = QWidget()
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_controls = QHBoxLayout()
        self.collapse_button = QPushButton("상세 접기")
        self.evidence_heading = QLabel()
        self.evidence_picker = QComboBox()
        self.evidence_picker.setAccessibleName("근거 선택")
        self.evidence_picker.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.evidence_order = QComboBox()
        self.evidence_order.setAccessibleName("근거 정렬")
        for label, order in RESULT_ORDERS:
            self.evidence_order.addItem(label, order)
        detail_controls.addWidget(self.evidence_heading)
        detail_controls.addWidget(self.evidence_picker, 1)
        detail_controls.addWidget(self.evidence_order)
        detail_controls.addWidget(self.collapse_button)
        detail_layout.addLayout(detail_controls)
        detail_actions = QHBoxLayout()
        self.answer_top_button = QPushButton("답변 처음으로")
        self.copy_answer_button = QPushButton("답변 복사")
        self.copy_source_button = QPushButton("출처 복사")
        detail_actions.addWidget(self.answer_top_button)
        detail_actions.addWidget(self.copy_answer_button)
        detail_actions.addWidget(self.copy_source_button)
        detail_actions.addStretch(1)
        detail_layout.addLayout(detail_actions)
        self.detail_feedback = _plain_label()
        detail_layout.addWidget(self.detail_feedback)
        self.detail_text = QPlainTextEdit()
        self.detail_text.setAccessibleName("전체 답변과 선택한 근거")
        self.detail_text.setReadOnly(True)
        self.detail_text.setTabChangesFocus(True)
        self.detail_text.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        detail_layout.addWidget(self.detail_text, 1)
        layout.addWidget(self.detail_panel, 1)

        self.query.textChanged.connect(self._edit_query)
        self.query.returnPressed.connect(self.submit)
        self.search_button.clicked.connect(self._submit_or_cancel)
        self.results_button.clicked.connect(self._toggle_results)
        self.detail_button.clicked.connect(self._show_detail)
        self.evidence_button.clicked.connect(self._show_detail)
        self.collapse_button.clicked.connect(self._fold_detail)
        self.answer_top_button.clicked.connect(self._answer_top)
        self.copy_answer_button.clicked.connect(self._copy_answer)
        self.copy_source_button.clicked.connect(self._copy_source)
        self.evidence_picker.currentIndexChanged.connect(self._select_evidence)
        self.evidence_order.currentIndexChanged.connect(self._order_evidence)
        self._escape = QShortcut(QKeySequence("Escape"), self)
        self._escape.activated.connect(self._escape_action)
        self._render()

    def submit(self) -> None:
        """확정한 검색 문장에 요청 번호를 부여하고 응답 대기 중에는 작게 유지한다."""
        query = self.query.text().strip()
        if not query or self._pending_id is not None:
            return
        self._request_id += 1
        self._pending_id = self._request_id
        self._clear_result()
        self._notice = ""
        self._view = "compact"
        self._reveal_on_completion = True
        self._render()
        self.search_requested.emit(self._request_id, query)

    def receive_result(self, request_id: int, result: CompactAnswer) -> None:
        """유효한 요청의 응답만 받아 요약이나 근거 부족·실패 상태로 전환한다."""
        if request_id != self._pending_id:
            return
        self._pending_id = None
        if result.status == "answer" and not result.full_answer.strip():
            result = CompactAnswer("error")
        self._result = result
        self._notice = {
            "answer": "",
            "empty": "검색 결과가 없습니다.",
            "insufficient": "답변을 만들 근거가 충분하지 않습니다.",
            "error": "검색 응답을 받지 못했습니다. 다시 검색해 주세요.",
            "unavailable": "답변 기능 준비 중입니다. 관리에서 조건 검색을 열어 주세요.",
        }[result.status]
        self._view = "open" if result.status == "answer" and self._reveal_on_completion else "compact"
        self._fill_result(result)
        self._render()

    def _fill_result(self, result: CompactAnswer) -> None:
        """요약과 전체 답변을 분리하고 현재 표시 순서로 근거를 채운다."""
        self.evidence_heading.setText(f"근거 {len(result.evidence)}개")
        self._order_evidence()

    def _update_summary_preview(self, width: int) -> None:
        """글꼴과 실제 폭에 맞춰 시각적 줄 수를 제한하고 잘림을 명시한다."""
        result = self._result
        if result is None or result.status != "answer":
            return
        content = result.summary.strip() or result.full_answer.strip()
        candidate = "\n".join(content.splitlines()[:5])[:200].rstrip()
        text = candidate.replace("\n", "\u2028")
        encoded = text.encode("utf-16-le")
        metrics = self.summary.fontMetrics()
        maximum_lines = max(1, min(5, 110 // metrics.lineSpacing()))
        layout = QTextLayout(text, self.summary.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        fragments = []
        line_heights = []
        height = 0.0
        consumed = 0
        layout.beginLayout()
        for _ in range(maximum_lines):
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1, width))
            if height + line.height() > 110:
                break
            height += line.height()
            line_heights.append(line.height())
            consumed = line.textStart() + line.textLength()
            # Qt 문자 위치는 UTF-16 단위다. 한글과 보조 평면 문자도 원문대로 읽는다.
            fragment = encoded[line.textStart() * 2:consumed * 2].decode("utf-16-le")
            fragments.append(fragment.rstrip())
        layout.endLayout()
        clipped = len(candidate) < len(content) or consumed * 2 < len(encoded)
        if clipped and fragments:
            fragments[-1] = metrics.elidedText(fragments[-1] + "…", Qt.TextElideMode.ElideRight, width)
        preview = "\n".join(fragments)
        flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        bounds = metrics.boundingRect(QRect(0, 0, width, 110), flags, preview)
        # 대체 글꼴의 실제 줄 높이가 기본 글꼴보다 큰 경우도 표시 상한 안에 맞춘다.
        while bounds.height() > 110 and fragments:
            fragments.pop()
            line_heights.pop()
            clipped = True
            if fragments:
                fragments[-1] = metrics.elidedText(
                    fragments[-1].rstrip("…") + "…", Qt.TextElideMode.ElideRight, width,
                )
            preview = "\n".join(fragments)
            bounds = metrics.boundingRect(QRect(0, 0, width, 110), flags, preview)
        self.summary.setText(preview)
        heading = "요약 답변" if result.summary.strip() else "답변 미리보기"
        self.summary_heading.setText(heading + (" · 일부 표시 중" if clipped else ""))
        self.summary.setFixedHeight(max(ceil(sum(line_heights)), bounds.height()) if fragments else 0)

    def _order_evidence(self) -> None:
        """표시 순서만 바꾸고 답변에서 인용한 번호와 선택한 근거를 유지한다."""
        if self._result is None:
            return
        selected = self.evidence_picker.currentData()
        rows = ordered_chunks(self._result.evidence, self.evidence_order.currentData())
        with QSignalBlocker(self.evidence_picker):
            self.evidence_picker.clear()
            for index, chunk in rows:
                title, kind, _ = chunk_source(chunk)
                self.evidence_picker.addItem(f"{index + 1}. {title} · {kind}", index)
            if selected is not None:
                self.evidence_picker.setCurrentIndex(self.evidence_picker.findData(selected))
        if selected is None or self.evidence_picker.currentData() != selected:
            self._select_evidence()

    def _select_evidence(self) -> None:
        """전체 답변과 선택 근거를 한 스크롤에 두고 긴 URL도 줄바꿈한다."""
        result = self._result
        if result is None:
            return
        self.detail_feedback.clear()
        self.detail_feedback.hide()
        text = f"전체 답변\n\n{result.full_answer}" if result.status == "answer" else ""
        self.detail_text.setPlainText(text)
        index = self.evidence_picker.currentData()
        if index is None:
            return
        cursor = self.detail_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\n\n" if text else "")
        position = cursor.position()
        cursor.insertText(f"근거 {index + 1}\n\n{chunk_detail(result.evidence[index])}")
        cursor.setPosition(position if self._view == "detail" else 0)
        self.detail_text.setTextCursor(cursor)

    def _answer_top(self) -> None:
        """현재 답변 문서의 처음으로 돌아가 읽기를 이어갈 수 있게 한다."""
        self.detail_text.moveCursor(QTextCursor.MoveOperation.Start)
        self.detail_text.verticalScrollBar().setValue(0)
        self.detail_text.setFocus()

    def _copy_answer(self) -> None:
        """사용자 요청으로 생략되지 않은 전체 답변만 클립보드에 복사한다."""
        if self._result is not None and self._result.status == "answer":
            QApplication.clipboard().setText(self._result.full_answer)
            self.detail_feedback.setText("전체 답변을 복사했습니다.")
            self.detail_feedback.show()

    def _copy_source(self) -> None:
        """선택한 근거의 확보 당시 URL이나 파일 경로를 그대로 복사한다."""
        index = self.evidence_picker.currentData()
        if self._result is not None and index is not None:
            _, _, address = chunk_source(self._result.evidence[index])
            QApplication.clipboard().setText(address)
            self.detail_feedback.setText("출처를 복사했습니다.")
            self.detail_feedback.show()

    def _edit_query(self, _text: str) -> None:
        """입력 편집 시 대기 중 응답과 표시 중인 결과를 함께 폐기한다."""
        self._invalidate_request()
        self._clear_result()
        self._notice = ""
        self._view = "compact"
        self._render()

    def _invalidate_request(self) -> None:
        """취소 알림을 보내기 전에 식별자를 폐기해 늦은 응답을 막는다."""
        pending = self._pending_id
        self._pending_id = None
        if pending is not None:
            self.search_cancelled.emit(pending)

    def _clear_result(self) -> None:
        """폐기한 답변과 근거가 숨은 위젯에도 남지 않도록 비운다."""
        self._result = None
        self.summary.clear()
        self.detail_text.clear()
        self.detail_feedback.clear()
        self.detail_feedback.hide()
        self.evidence_picker.clear()

    def _submit_or_cancel(self) -> None:
        """대기 중에는 현재 요청을 취소하고 그 외에는 검색을 제출한다."""
        if self._pending_id is None:
            self.submit()
            return
        self._invalidate_request()
        self._notice = "검색을 취소했습니다."
        self._view = "compact"
        self._render()
        self.query.setFocus()

    def _toggle_results(self) -> None:
        """요청 없이 빈 영역을 열거나 현재 응답을 요약 상태로 다시 연다."""
        opening = self._view == "compact"
        self._view = "open" if opening else "compact"
        if self._pending_id is not None:
            self._reveal_on_completion = opening
        self._render()

    def _show_detail(self) -> None:
        """저장된 같은 응답의 전체 답변과 근거를 펼친다."""
        self._view = "detail"
        self._render()
        self.collapse_button.setFocus()

    def _fold_detail(self) -> None:
        """답변이 있으면 요약으로 돌아가고 근거만 있었다면 기본 크기로 접는다."""
        answered = self._result is not None and self._result.status == "answer"
        self._view = "open" if answered else "compact"
        self._render()
        (self.detail_button if answered else self.evidence_button).setFocus()

    def _escape_action(self) -> None:
        """열린 영역을 한 단계씩 접고 기본 창에서만 대기 중 검색을 취소한다."""
        if self._view == "detail":
            self._fold_detail()
        elif self._view == "open":
            self._toggle_results()
            self.results_button.setFocus()
        elif self._pending_id is not None:
            self._submit_or_cancel()

    def _render(self) -> None:
        """현재 상태의 패널만 배치하고 활성 화면 안에서 목표 크기로 조정한다."""
        result = self._result
        answered = result is not None and result.status == "answer"
        loading = self._pending_id is not None
        empty_open = self._view == "open" and not answered
        summary_open = self._view == "open" and answered
        detail_open = self._view == "detail"
        evidence = bool(result and result.evidence and result.status in ("answer", "insufficient"))
        self.search_button.setText("취소" if loading else "검색")
        self.search_button.setEnabled(loading or bool(self.query.text().strip()))
        self.results_button.setText("결과 보기" if self._view == "compact" else "결과 숨기기")
        self.evidence_button.setVisible(evidence and not answered and not detail_open)
        self.status.setText("검색 중…" if loading else "" if empty_open else self._notice)
        self.status.setVisible(bool(self.status.text()))
        self.empty_message.setText(
            "검색 결과를 기다리는 중입니다." if loading else self._notice or "아직 검색 결과가 없습니다.",
        )
        self.empty_message.setVisible(empty_open)
        self.summary_panel.setVisible(summary_open)
        self.detail_panel.setVisible(detail_open)
        self.evidence_heading.setVisible(evidence)
        self.evidence_picker.setVisible(evidence)
        self.evidence_order.setVisible(evidence and len(result.evidence) > 1)
        self.answer_top_button.setVisible(answered)
        self.copy_answer_button.setVisible(answered)
        self.copy_source_button.setVisible(evidence)

        size = QSize(440, 112)
        if detail_open:
            size = QSize(560, 496)
        elif summary_open:
            # 짧은 답변 아래에 빈 공간을 남기지 않고 버튼을 바로 이어 표시한다.
            screen = self.screen()
            width = min(440, screen.availableGeometry().width()) if screen else 440
            margins = self.layout().contentsMargins()
            text_width = max(1, width - margins.left() - margins.right())
            self._update_summary_preview(text_width)
            # 자식 레이아웃을 먼저 갱신해 첫 펼침과 다시 접은 상태가 같은 높이를 사용한다.
            self.summary_panel.layout().activate()
            self.layout().invalidate()
            size = QSize(440, min(248, self.layout().sizeHint().height()))
        elif empty_open:
            size = QSize(440, 168)
        self._fit_window(size)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """사용자가 폭을 바꿔도 요약 잘림 표시와 줄 수를 다시 맞춘다."""
        super().resizeEvent(event)
        if self._view == "open":
            margins = self.layout().contentsMargins()
            self._update_summary_preview(max(1, self.width() - margins.left() - margins.right()))

    def _fit_window(self, target: QSize) -> None:
        """단독 실행에서는 자신을, 포함된 화면에서는 부모 창을 목표 크기로 맞춘다."""
        if self.isWindow():
            fit_window(self, target)
        else:
            self.preferred_size_changed.emit(target)

    def showEvent(self, event: QShowEvent) -> None:
        """창 테두리가 적용되면 크기를 다시 맞추고 첫 검색 입력에 초점을 둔다."""
        super().showEvent(event)
        self._render()
        self.query.setFocus()

    def closeEvent(self, event: QCloseEvent) -> None:
        """창이 닫힌 뒤 이전 검색 응답이 화면을 다시 열지 못하게 한다."""
        self._invalidate_request()
        self._clear_result()
        self._notice = ""
        self._view = "compact"
        super().closeEvent(event)
