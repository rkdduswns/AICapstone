"""검색 입력에서 요약과 근거까지 한 창에서 펼치는 Client 미리보기."""

from dataclasses import dataclass
from html import escape
from math import ceil
from typing import Literal

from PySide6.QtCore import QRect, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import (
    QActionGroup,
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
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from client.search_presentation import RESULT_ORDERS, chunk_metadata, chunk_source, ordered_chunks
from client.theme import apply_client_style, set_role
from client.time_values import format_timestamp
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


class _SourceSummary(QLabel):
    """긴 제목도 두 줄의 개요 안에 두고 원문은 툴팁과 출처 정보에서 제공한다."""

    def __init__(self) -> None:
        """제목과 유형·열람 시각을 각각 한 줄로 제한한다."""
        super().__init__()
        self._lines: tuple[str, ...] = ()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_source(self, title: str, metadata: str) -> None:
        """받은 원문을 보존하고 현재 표시 폭에 맞춰 말줄임표를 계산한다."""
        self._lines = (title, metadata)
        # Qt 툴팁은 자동으로 HTML을 판별하므로 외부 제목의 태그도 원문으로 보이게 이스케이프한다.
        self.setToolTip("<qt>" + "<br/>".join(escape(line) for line in self._lines) + "</qt>")
        self._update_lines()

    def _update_lines(self) -> None:
        """폭이 달라져도 긴 제목이 본문 영역을 밀어내지 않게 한다."""
        width = max(1, self.contentsRect().width())
        metrics = self.fontMetrics()
        preview = "\n".join(metrics.elidedText(line, Qt.TextElideMode.ElideRight, width)
                            for line in self._lines)
        self.setText(preview)
        flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        height = metrics.boundingRect(QRect(0, 0, width, 1000), flags, preview).height()
        self.setFixedHeight(height if self._lines else 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """근거를 펼치거나 창 크기를 바꿀 때 실제 폭을 다시 반영한다."""
        super().resizeEvent(event)
        self._update_lines()

    def clear(self) -> None:
        """검색을 바꾸면 숨은 개요 원문도 함께 지워 크기 변경으로 복구되지 않게 한다."""
        self._lines = ()
        self.setToolTip("")
        super().clear()
        self.setFixedHeight(0)


class CompactSearchWindow(QWidget):
    """현재 요청의 결과만 표시하고 접은 영역을 창 크기 계산에서 제외한다."""

    search_requested = Signal(int, str)
    search_cancelled = Signal(int)
    preferred_size_changed = Signal(QSize)

    def __init__(self) -> None:
        """기본 입력과 필요할 때만 표시하는 결과 영역을 같은 창에 둔다."""
        super().__init__()
        apply_client_style(self)
        self.setWindowTitle("ContextTrace — 검색 미리보기")
        self._view = "compact"
        self._result: CompactAnswer | None = None
        self._pending_id: int | None = None
        self._request_id = 0
        self._reveal_on_completion = True
        self._notice = ""
        self._evidence_was_expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
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
        self.menu_button = QPushButton("메뉴")
        self.menu_button.setAccessibleName("화면과 설정 메뉴")
        self.menu_button.setProperty("menuControl", True)
        self.main_menu = QMenu(self.menu_button)
        self.result_view_action = self.main_menu.addAction("결과 보기")
        self.menu_button.setMenu(self.main_menu)
        controls.addWidget(self.connection_button)
        controls.addStretch(1)
        controls.addWidget(self.evidence_button)
        controls.addWidget(self.menu_button)
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
        self.detail_button = QPushButton("자세히 보기")
        summary_layout.addWidget(self.summary_heading)
        summary_layout.addWidget(self.summary)
        summary_layout.addWidget(self.detail_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.summary_panel, 1)

        self.detail_panel = QWidget()
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(8)
        detail_controls = QHBoxLayout()
        self.collapse_button = QPushButton("요약으로")
        self.detail_heading = _plain_label("전체 답변")
        self.answer_menu_button = QPushButton("답변 메뉴")
        self.answer_menu_button.setAccessibleName("답변 복사와 읽기 메뉴")
        self.answer_menu_button.setProperty("menuControl", True)
        self.answer_menu = QMenu(self.answer_menu_button)
        self.copy_answer_action = self.answer_menu.addAction("답변 복사")
        self.answer_top_action = self.answer_menu.addAction("답변 처음으로")
        self.answer_menu_button.setMenu(self.answer_menu)
        detail_controls.addWidget(self.detail_heading, 1)
        detail_controls.addWidget(self.answer_menu_button)
        detail_controls.addWidget(self.collapse_button)
        detail_layout.addLayout(detail_controls)
        self.detail_feedback = _plain_label()
        detail_layout.addWidget(self.detail_feedback)

        # 답변을 읽는 위치는 근거 선택과 분리한다. 펼친 두 영역의 높이도 직접 조절할 수 있다.
        self.reading_splitter = QSplitter(Qt.Orientation.Vertical)
        self.reading_splitter.setChildrenCollapsible(False)
        self.reading_splitter.setHandleWidth(6)
        self.answer_section = QWidget()
        answer_layout = QVBoxLayout(self.answer_section)
        answer_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_text = QPlainTextEdit()
        self.detail_text.setAccessibleName("전체 답변")
        self.detail_text.setReadOnly(True)
        self.detail_text.setTabChangesFocus(True)
        self.detail_text.setMinimumHeight(64)
        self.detail_text.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        answer_layout.addWidget(self.detail_text)
        self.reading_splitter.addWidget(self.answer_section)

        self.evidence_section = QWidget()
        evidence_layout = QVBoxLayout(self.evidence_section)
        evidence_layout.setContentsMargins(10, 8, 10, 8)
        evidence_layout.setSpacing(8)
        evidence_header = QHBoxLayout()
        self.evidence_toggle = QPushButton("근거 보기")
        self.evidence_toggle.setCheckable(True)
        self.evidence_toggle.setAccessibleName("근거 펼치기·접기")
        evidence_header.addWidget(self.evidence_toggle)
        evidence_header.addStretch(1)
        evidence_layout.addLayout(evidence_header)
        self.evidence_body = QWidget()
        evidence_body_layout = QVBoxLayout(self.evidence_body)
        evidence_body_layout.setContentsMargins(0, 0, 0, 0)
        evidence_body_layout.setSpacing(6)
        evidence_controls = QHBoxLayout()
        self.evidence_picker = QComboBox()
        self.evidence_picker.setAccessibleName("근거 선택")
        self.evidence_picker.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.evidence_menu_button = QPushButton("근거 메뉴")
        self.evidence_menu_button.setAccessibleName("출처 정보·복사·정렬 메뉴")
        self.evidence_menu_button.setProperty("menuControl", True)
        self.evidence_menu = QMenu(self.evidence_menu_button)
        self.copy_source_action = self.evidence_menu.addAction("출처 복사")
        self.source_details_action = self.evidence_menu.addAction("출처 정보 보기")
        self.source_details_action.setCheckable(True)
        self.evidence_sort_section = self.evidence_menu.addSection("정렬")
        self.evidence_order_group = QActionGroup(self)
        self.evidence_order_group.setExclusive(True)
        self.evidence_order_actions = {}
        # 정렬도 같은 한 단계 메뉴에서 선택한다. 인용 번호와 선택 대상은 원래 인덱스를 쓴다.
        for label, order in RESULT_ORDERS:
            action = self.evidence_menu.addAction(label)
            action.setData(order)
            action.setCheckable(True)
            self.evidence_order_group.addAction(action)
            self.evidence_order_actions[order] = action
        self.evidence_order_actions["relevance"].setChecked(True)
        self.evidence_menu_button.setMenu(self.evidence_menu)
        evidence_controls.addWidget(self.evidence_picker, 1)
        evidence_controls.addWidget(self.evidence_menu_button)
        evidence_body_layout.addLayout(evidence_controls)
        self.source_summary = _SourceSummary()
        evidence_body_layout.addWidget(self.source_summary)
        self.source_details = QPlainTextEdit()
        self.source_details.setAccessibleName("선택 근거의 출처 정보")
        self.source_details.setReadOnly(True)
        self.source_details.setTabChangesFocus(True)
        self.source_details.setMinimumHeight(42)
        self.source_details.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.evidence_text = QPlainTextEdit()
        self.evidence_text.setAccessibleName("선택한 근거의 본문")
        self.evidence_text.setReadOnly(True)
        self.evidence_text.setTabChangesFocus(True)
        self.evidence_text.setMinimumHeight(48)
        self.evidence_text.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        # 출처 정보를 본문과 같은 자리에서 읽어 작은 화면에도 별도 높이가 늘어나지 않는다.
        self.evidence_reading = QStackedWidget()
        self.evidence_reading.setMinimumHeight(48)
        self.evidence_reading.addWidget(self.evidence_text)
        self.evidence_reading.addWidget(self.source_details)
        evidence_body_layout.addWidget(self.evidence_reading, 1)
        evidence_layout.addWidget(self.evidence_body, 1)
        self.reading_splitter.addWidget(self.evidence_section)
        self.reading_splitter.handle(1).setToolTip("경계를 끌어 답변과 근거의 읽기 높이를 조절합니다.")
        self.reading_splitter.setStretchFactor(0, 3)
        self.reading_splitter.setStretchFactor(1, 2)
        detail_layout.addWidget(self.reading_splitter, 1)
        layout.addWidget(self.detail_panel, 1)

        set_role(self.search_button, "primary")
        for button in (self.detail_button, self.evidence_button, self.collapse_button):
            set_role(button, "secondary")
        for button in (self.connection_button, self.menu_button, self.answer_menu_button,
                       self.evidence_menu_button, self.evidence_toggle):
            set_role(button, "quiet")
        for heading in (self.summary_heading, self.detail_heading):
            set_role(heading, "heading")
        set_role(self.source_summary, "muted")
        set_role(self.detail_feedback, "muted")
        set_role(self.evidence_section, "card")

        self.query.textChanged.connect(self._edit_query)
        self.query.returnPressed.connect(self.submit)
        self.search_button.clicked.connect(self._submit_or_cancel)
        self.result_view_action.triggered.connect(self._toggle_results)
        self.detail_button.clicked.connect(self._show_detail)
        self.evidence_button.clicked.connect(self._show_detail)
        self.collapse_button.clicked.connect(self._fold_detail)
        self.answer_top_action.triggered.connect(self._answer_top)
        self.copy_answer_action.triggered.connect(self._copy_answer)
        self.copy_source_action.triggered.connect(self._copy_source)
        self.evidence_toggle.toggled.connect(self._update_evidence_visibility)
        self.source_details_action.toggled.connect(self._update_evidence_visibility)
        self.evidence_picker.currentIndexChanged.connect(self._select_evidence)
        self.evidence_order_group.triggered.connect(lambda _action: self._order_evidence())
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
            "unavailable": "검색·답변 기능 준비 중입니다. 메뉴에서 최근 기록과 문서 가져오기를 이용해 주세요.",
        }[result.status]
        self._view = "open" if result.status == "answer" and self._reveal_on_completion else "compact"
        self._fill_result(result)
        self._render()

    def _fill_result(self, result: CompactAnswer) -> None:
        """요약과 전체 답변을 분리하고 현재 표시 순서로 근거를 채운다."""
        self.detail_text.setPlainText(result.full_answer if result.status == "answer" else "")
        self.evidence_toggle.setChecked(result.status == "insufficient")
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
        rows = ordered_chunks(self._result.evidence, self.evidence_order_group.checkedAction().data())
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
        """근거만 교체해 읽던 답변 위치와 선택 가능한 원문을 보존한다."""
        result = self._result
        if result is None:
            return
        self.detail_feedback.clear()
        self.detail_feedback.hide()
        index = self.evidence_picker.currentData()
        if index is None:
            return
        chunk = result.evidence[index]
        title, kind, _ = chunk_source(chunk)
        partial = " · 일부 확보" if chunk.source.content_truncated else ""
        self.source_summary.set_source(
            f"[{index + 1}] {title}",
            f"{kind} · 열람 {format_timestamp(chunk.source.last_active_at)}{partial}",
        )
        self.source_details.setPlainText(f"근거 {index + 1}\n\n{chunk_metadata(chunk)}")
        self.evidence_text.setPlainText(chunk.text)

    def _update_evidence_visibility(self) -> None:
        """현재 응답의 근거와 상세 출처를 요청 없이 펼치고 숨은 공간을 회수한다."""
        expanded = self.evidence_toggle.isChecked()
        newly_expanded = expanded and not self._evidence_was_expanded
        self.evidence_body.setVisible(expanded)
        count = len(self._result.evidence) if self._result is not None else 0
        self.evidence_toggle.setText(f"근거 {count}개 {'접기' if expanded else '보기'}")
        showing_source = self.source_details_action.isChecked()
        self.evidence_reading.setCurrentWidget(self.source_details if showing_source else self.evidence_text)
        answered = self._result is not None and self._result.status == "answer"
        screen = self.screen()
        narrow = bool(expanded and screen and screen.availableGeometry().height() < 480)
        # 낮은 작업 영역은 두 본문을 세로로 쌓지 않고 근거를 읽는 동안 답변 영역을 접는다.
        self.answer_section.setVisible(answered and not narrow)
        self.answer_top_action.setText("답변으로" if answered and narrow else "답변 처음으로")
        self.detail_heading.setText("근거" if answered and narrow else "전체 답변" if answered else "확인할 근거")
        self.evidence_section.setMaximumHeight(16777215)
        if not expanded:
            self.evidence_section.layout().activate()
            self.evidence_section.setMaximumHeight(self.evidence_section.layout().sizeHint().height())
        self.evidence_body.layout().invalidate()
        self.evidence_section.layout().invalidate()
        self.detail_panel.layout().invalidate()
        self.layout().invalidate()
        self.updateGeometry()
        if newly_expanded and answered and not narrow and self._view == "detail":
            # 근거를 요청한 순간에는 읽기 공간을 먼저 확보하고 이후 사용자가 조절한 비율은 유지한다.
            self.evidence_section.layout().activate()
            height = max(1, self.reading_splitter.height())
            self.reading_splitter.setSizes([max(64, height // 4), max(1, height * 3 // 4)])
        self._evidence_was_expanded = expanded
        self._update_action_state()

    def _update_action_state(self) -> None:
        """현재 화면에서 쓸 수 있는 보조 동작만 메뉴에 제공한다."""
        result = self._result
        answered = bool(result and result.status == "answer")
        detail = self._view == "detail"
        evidence = bool(result and result.evidence and result.status in ("answer", "insufficient"))
        source_active = detail and evidence and self.evidence_toggle.isChecked()
        self.answer_menu_button.setVisible(detail and answered)
        self.copy_answer_action.setEnabled(detail and answered)
        self.answer_top_action.setEnabled(detail and answered)
        self.copy_source_action.setEnabled(source_active)
        self.source_details_action.setEnabled(source_active)
        self.evidence_menu_button.setVisible(source_active)
        sortable = bool(source_active and len(result.evidence) > 1)
        self.evidence_sort_section.setVisible(sortable)
        for action in self.evidence_order_actions.values():
            action.setVisible(sortable)
            action.setEnabled(sortable)

    def _answer_top(self) -> None:
        """현재 답변 문서의 처음으로 돌아가 읽기를 이어갈 수 있게 한다."""
        if self._view == "detail" and self.answer_section.isHidden():
            self.evidence_toggle.setChecked(False)
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
        self.source_summary.clear()
        self.source_details.clear()
        self.evidence_text.clear()
        self.answer_menu.close()
        self.evidence_menu.close()
        with QSignalBlocker(self.evidence_toggle), QSignalBlocker(self.source_details_action):
            self.evidence_toggle.setChecked(False)
            self.source_details_action.setChecked(False)
        self._update_evidence_visibility()
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
        popup = QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
            return
        if self._view == "detail":
            self._fold_detail()
        elif self._view == "open":
            self._toggle_results()
            self.menu_button.setFocus()
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
        self.result_view_action.setText("결과 보기" if self._view == "compact" else "결과 숨기기")
        self.collapse_button.setText("요약으로" if answered else "검색으로")
        self.evidence_button.setVisible(evidence and not answered and not detail_open)
        self.status.setText("검색 중…" if loading else "" if empty_open else self._notice)
        self.status.setVisible(bool(self.status.text()))
        self.empty_message.setText(
            "검색 결과를 기다리는 중입니다." if loading else self._notice or "아직 검색 결과가 없습니다.",
        )
        self.empty_message.setVisible(empty_open)
        self.summary_panel.setVisible(summary_open)
        self.detail_panel.setVisible(detail_open)
        self.detail_heading.setText("전체 답변" if answered else "확인할 근거")
        self.answer_section.setVisible(answered)
        self.evidence_section.setVisible(evidence)
        self.evidence_picker.setVisible(evidence)
        self._update_evidence_visibility()

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
        # 포함된 화면도 현재 표시 상태의 최소 크기를 먼저 계산해 숨긴 상세의 이전 높이를 버린다.
        self.layout().activate()
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
        self.main_menu.close()
        self._clear_result()
        self._notice = ""
        self._view = "compact"
        super().closeEvent(event)
