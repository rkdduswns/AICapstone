"""자연어 질의와 선택 조건을 받아 관련 조각을 표시하는 Client 화면."""

from collections.abc import Callable
from dataclasses import asdict, dataclass

from PySide6.QtCore import QDate, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client.search_client import local_date_range, read_search_request
from client.search_presentation import RESULT_ORDERS, chunk_detail, chunk_source, ordered_chunks
from shared.search import MAX_SEARCH_PROCESS, SearchRequest
from shared.search_data import DocumentChunk


@dataclass(frozen=True)
class SemanticSearchInput:
    """제출한 질의와 조건의 화면 내부 값. 기간은 마지막 활성 시각 기준이다."""

    query: str
    process_name: str
    source_type: str
    active_from: str | None
    active_before: str | None


class SemanticSearchWidget(QWidget):
    """입력과 결과 표현을 담당하고 결과의 순서와 출처를 공급자가 준 그대로 유지한다."""

    def __init__(
        self,
        provider: Callable[[SemanticSearchInput], list[DocumentChunk]],
        parent: QWidget | None = None,
    ) -> None:
        """동기 가상 응답을 주입해 검색 화면을 확인할 수 있게 구성한다."""
        super().__init__(parent)
        self._provider = provider
        self._chunks: list[DocumentChunk] = []
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("예: 브라우저에서 읽은 개인정보 저장 기준")
        form.addRow("검색 문장", self.query)
        self.process_name = QLineEdit()
        self.process_name.setMaxLength(MAX_SEARCH_PROCESS)
        self.process_name.setPlaceholderText("예: chrome.exe (선택)")
        form.addRow("프로그램", self.process_name)
        self.source = QComboBox()
        for label, value in (("전체 출처", "all"), ("웹", "web"), ("문서 전체", "document"),
                             ("PDF", "pdf"), ("DOCX", "docx")):
            self.source.addItem(label, value)
        form.addRow("출처 유형", self.source)
        self.use_dates = QCheckBox("날짜 범위 지정")
        form.addRow("기간", self.use_dates)
        dates = QHBoxLayout()
        self.first_date = QDateEdit(QDate.currentDate())
        self.last_date = QDateEdit(QDate.currentDate())
        for editor in (self.first_date, self.last_date):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
            editor.setEnabled(False)
        dates.addWidget(self.first_date)
        dates.addWidget(QLabel("~"))
        dates.addWidget(self.last_date)
        form.addRow("마지막 활성 날짜", dates)
        layout.addLayout(form)
        self.button = QPushButton("검색")
        layout.addWidget(self.button)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        result_controls = QHBoxLayout()
        self.result_order = QComboBox()
        self.result_order.setAccessibleName("결과 정렬")
        for label, order in RESULT_ORDERS:
            self.result_order.addItem(label, order)
        result_controls.addWidget(self.status, 1)
        result_controls.addWidget(QLabel("정렬"))
        result_controls.addWidget(self.result_order)
        layout.addLayout(result_controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["관련도 순위", "제목", "출처 유형", "관련 내용"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setTabChangesFocus(True)
        self.detail.setPlaceholderText("결과를 선택하면 원본 출처와 관련 본문을 볼 수 있습니다.")
        layout.addWidget(self.detail, 1)

        self.button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        self.process_name.returnPressed.connect(self.search)
        self.query.textChanged.connect(self._inputs_changed)
        self.process_name.textChanged.connect(self._inputs_changed)
        self.source.currentIndexChanged.connect(self._inputs_changed)
        self.first_date.dateChanged.connect(self._inputs_changed)
        self.last_date.dateChanged.connect(self._inputs_changed)
        self.use_dates.toggled.connect(self._dates_changed)
        self.result_order.currentIndexChanged.connect(self._order_results)
        self.table.itemSelectionChanged.connect(self._show_selection)
        self._inputs_changed()

    def _dates_changed(self, enabled: bool) -> None:
        """전체 기간과 선택 기간을 전환할 때 날짜 편집과 결과 상태를 갱신한다."""
        self.first_date.setEnabled(enabled)
        self.last_date.setEnabled(enabled)
        self._inputs_changed()

    def _inputs_changed(self, *_args: object) -> None:
        """수정한 조건 아래에서 이전 질의의 결과가 보이지 않도록 지운다."""
        self._clear()
        self.button.setEnabled(bool(self.query.text().strip()))
        self.status.setText("검색 문장과 필요한 조건을 입력해 주세요.")

    def _clear(self) -> None:
        """목록의 데이터와 선택 상세를 함께 지운다."""
        self._chunks = []
        self.result_order.setEnabled(False)
        self.table.setRowCount(0)
        self.detail.clear()

    def _request(self, query: str) -> SemanticSearchInput:
        """조건 검색의 PC 현지 날짜 경계와 프로그램·출처 검증을 재사용한다."""
        first = before = None
        if self.use_dates.isChecked():
            first, before = local_date_range(
                self.first_date.date().toPython(), self.last_date.date().toPython(),
            )
        filters = read_search_request(asdict(SearchRequest(
            process_name=self.process_name.text(), source_type=self.source.currentData(),
            active_from=first, active_before=before,
        )))
        return SemanticSearchInput(
            query, filters.process_name, filters.source_type, filters.active_from, filters.active_before,
        )

    def search(self) -> None:
        """명시적으로 제출한 입력을 공급자에게 전달하고 빈 결과와 오류를 구분한다."""
        query = self.query.text().strip()
        if not query:
            return
        self._clear()
        try:
            request = self._request(query)
        except ValueError as error:
            self.status.setText(str(error))
            return
        try:
            self._chunks = self._provider(request)
        except ValueError:
            self.status.setText("검색 결과를 표시할 수 없습니다. 다시 검색해 주세요.")
            return

        if self._chunks:
            self.result_order.setEnabled(len(self._chunks) > 1)
            self._order_results()
        else:
            self.status.setText("조건에 맞는 검색 결과가 없습니다.")

    def _order_results(self) -> None:
        """다시 요청하지 않고 표시 순서를 바꾸며 원래 관련도 순위와 선택을 보존한다."""
        if not self._chunks:
            return
        role = Qt.ItemDataRole.UserRole
        selected = self.table.selectedItems()
        selected_rank = self.table.item(selected[0].row(), 0).data(role) if selected else None
        rows = ordered_chunks(self._chunks, self.result_order.currentData())
        selected_row = 0
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(rows))
            for row, (rank, chunk) in enumerate(rows):
                title, kind, _ = chunk_source(chunk)
                snippet = " ".join(chunk.text.split())
                if len(snippet) > 96:
                    snippet = snippet[:96] + "…"
                rank_item = QTableWidgetItem(str(rank + 1))
                rank_item.setData(role, rank)
                self.table.setItem(row, 0, rank_item)
                for column, value in enumerate((title, kind, snippet), start=1):
                    self.table.setItem(row, column, QTableWidgetItem(value))
                if rank == selected_rank:
                    selected_row = row
            self.table.selectRow(selected_row)
        if rows[selected_row][0] != selected_rank:
            self._show_selection()
        self.status.setText(f"검색 결과 {len(rows)}건 · {self.result_order.currentText()}")

    def _show_selection(self) -> None:
        """선택한 조각의 원본 주소, 작업·확보 시각, 본문을 일반 텍스트로 표시한다."""
        selected = self.table.selectedItems()
        if not selected:
            self.detail.clear()
            return
        rank = self.table.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        self.detail.setPlainText(chunk_detail(self._chunks[rank]))
