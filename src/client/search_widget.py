"""명시적 조건을 제출하고 원본 기록의 출처·열람 시각을 확인하는 검색 화면."""

from dataclasses import asdict
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client.search_client import SearchClient, local_date_range, read_search_request
from client.time_values import format_duration, format_timestamp, parse_timestamp
from shared.records import ContextRecord
from shared.search import MAX_SEARCH_KEYWORD, MAX_SEARCH_PROCESS, SearchRequest, SearchResults


class SearchWidget(QWidget):
    """입력과 결과를 분리하고 조건 변경·취소·연결 변경에서 이전 결과를 정리한다."""

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """수동 검색 폼·읽기 전용 목록/상세와 비동기 요청을 준비한다."""
        super().__init__(parent)
        self.connected = False
        self.records: list[ContextRecord] = []
        self.client = SearchClient(port, self)
        self.client.results_received.connect(self._show_results)
        self.client.search_failed.connect(self._show_error)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.keyword = QLineEdit()
        self.keyword.setMaxLength(MAX_SEARCH_KEYWORD)
        self.keyword.setPlaceholderText("창·페이지 제목의 일부 (선택)")
        self.process_name = QLineEdit()
        self.process_name.setMaxLength(MAX_SEARCH_PROCESS)
        self.process_name.setPlaceholderText("예: chrome.exe, msedge.exe (선택)")
        form.addRow("제목 키워드", self.keyword)
        form.addRow("프로그램", self.process_name)
        choices = QHBoxLayout()
        self.source = QComboBox()
        for label, value in (("전체 출처", "all"), ("웹", "web"), ("문서 전체", "document"),
                             ("PDF", "pdf"), ("DOCX", "docx")):
            self.source.addItem(label, value)
        self.order = QComboBox()
        self.order.addItem("최근 활성순", "recent")
        self.order.addItem("오래된 활성순", "oldest")
        choices.addWidget(self.source)
        choices.addWidget(self.order)
        form.addRow("출처 · 정렬", choices)
        self.period = QComboBox()
        self.period.addItems(["전체 기간", "오늘", "날짜 선택"])
        form.addRow("기간", self.period)
        self.dates = QWidget()
        dates_layout = QHBoxLayout(self.dates)
        dates_layout.setContentsMargins(0, 0, 0, 0)
        self.first_date = QDateEdit(QDate.currentDate())
        self.last_date = QDateEdit(QDate.currentDate())
        for editor in (self.first_date, self.last_date):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
        dates_layout.addWidget(self.first_date)
        dates_layout.addWidget(QLabel("~"))
        dates_layout.addWidget(self.last_date)
        self.dates.setEnabled(False)
        form.addRow("PC 현지 날짜", self.dates)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.button = QPushButton("검색")
        self.cancel_button = QPushButton("취소")
        self.button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        self.status = self._label("대기 — Backend 연결을 확인해 주세요.")
        layout.addWidget(self.status)
        self.applied = self._label("마지막 활성 시각 기준 · 최대 20건 · 적용된 검색 조건 없음")
        layout.addWidget(self.applied)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["제목", "출처", "프로그램", "마지막 활성"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 130), (2, 100), (3, 115)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setTabChangesFocus(True)
        self.detail.setPlaceholderText("결과를 선택하면 전체 제목·출처·열람 시각을 확인할 수 있습니다.")
        self.detail.setMinimumHeight(95)
        self.detail.setMaximumHeight(130)
        layout.addWidget(self.detail)
        self.button.clicked.connect(self.search)
        self.cancel_button.clicked.connect(self.cancel)
        self.keyword.returnPressed.connect(self.search)
        self.process_name.returnPressed.connect(self.search)
        self.keyword.textChanged.connect(self._filters_changed)
        self.process_name.textChanged.connect(self._filters_changed)
        self.source.currentIndexChanged.connect(self._filters_changed)
        self.order.currentIndexChanged.connect(self._filters_changed)
        self.period.currentIndexChanged.connect(self._period_changed)
        self.first_date.dateChanged.connect(self._filters_changed)
        self.last_date.dateChanged.connect(self._filters_changed)
        self.table.itemSelectionChanged.connect(self._show_selection)

    @staticmethod
    def _label(text: str) -> QLabel:
        """긴 검색어·오류를 일반 텍스트로 줄바꿈하여 고정 창 너비를 유지한다."""
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    def _period_changed(self, index: int) -> None:
        """날짜 선택일 때만 날짜 입력을 열고 기존 검색 상태를 지운다."""
        self.dates.setEnabled(index == 2)
        self._filters_changed()

    def _filters_changed(self, *_args) -> None:
        """입력 중 새 조건 아래 옛 결과가 남지 않게 요청·목록·상세를 함께 비운다."""
        self.client.close()
        self._clear_results()
        self.status.setText("조건 변경됨 — 검색을 눌러 주세요." if self.connected
                            else "대기 — Backend 연결을 확인해 주세요.")
        self.button.setEnabled(self.connected)
        self.cancel_button.setEnabled(False)

    def set_connected(self, connected: bool) -> None:
        """재연결에서도 입력 초안은 유지하며 이전 서버의 검색 결과를 폐기한다."""
        self.connected = connected
        self._filters_changed()

    def _request(self) -> SearchRequest:
        """날짜 프리셋을 명시적 시간 경계로 바꾸고 공통 입력 검증을 적용한다."""
        first = before = None
        if self.period.currentIndex() == 1:
            today = date.today()
            first, before = local_date_range(today, today)
        elif self.period.currentIndex() == 2:
            first, before = local_date_range(
                self.first_date.date().toPython(), self.last_date.date().toPython())
        raw = asdict(SearchRequest(
            self.keyword.text(), self.process_name.text(), self.source.currentData(),
            first, before, self.order.currentData()))
        return read_search_request(raw)

    def search(self) -> None:
        """중복 요청을 막고 제출한 조건을 고정한 뒤 Backend 결과를 기다린다."""
        if not self.connected or self.client.reply is not None:
            return
        try:
            request = self._request()
        except ValueError as error:
            self._clear_results()
            self.status.setText(str(error))
            return
        self._clear_results()
        self.status.setText("검색 중 — 조건에 맞는 작업 기록을 확인하고 있습니다.")
        self.button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.client.search(request)

    def cancel(self) -> None:
        """사용자 취소를 오류나 정상 빈 결과로 처리하지 않는다."""
        self.client.close()
        self._clear_results()
        self.status.setText("검색을 취소했습니다.")
        self.button.setEnabled(self.connected)
        self.cancel_button.setEnabled(False)

    def _clear_results(self) -> None:
        """목록과 상세를 같이 지워 서로 다른 검색 결과가 섞이지 않게 한다."""
        self.records = []
        self.table.setRowCount(0)
        self.detail.clear()
        self.applied.setText("마지막 활성 시각 기준 · 최대 20건 · 적용된 검색 조건 없음")

    @staticmethod
    def _source(record: ContextRecord) -> tuple[str, str]:
        """서버가 준 출처만 표시하며 창 제목에서 URL이나 파일 경로를 추정하지 않는다."""
        if record.browser is not None:
            page = record.browser
            return page.page_title or record.window_title or "(제목 없음)", page.url or "(URL 없음)"
        if record.document is not None:
            return record.window_title or "(제목 없음)", record.document.file_path
        return record.window_title or "(제목 없음)", "일반 작업 / 출처 미제공"

    def _show_results(self, results: SearchResults) -> None:
        """서버가 확인한 조건을 표시하고 결과 순서를 그대로 유지한다."""
        self.records = results.records
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            title, source = self._source(record)
            values = (title, source, record.application,
                      parse_timestamp(record.last_active_at).astimezone().strftime("%m-%d %H:%M:%S"))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        query = results.request
        period = ("전체 기간" if query.active_from is None else
                  f"{format_timestamp(query.active_from)} 이상 · "
                  f"{format_timestamp(query.active_before)} 미만")
        self.applied.setText(
            f"확인된 조건 · 제목: {query.keyword or '전체'} · 프로그램: {query.process_name or '전체'}"
            f" · {self.source.currentText()} · {period} · {self.order.currentText()}")
        self.status.setText(
            f"검색 결과 {len(self.records)}건" + (" · 더 많은 기록이 있습니다. 조건을 좁혀 주세요."
                                         if results.has_more else "")
            if self.records else "조건에 맞는 기록이 없습니다.")
        self.button.setEnabled(self.connected)
        self.cancel_button.setEnabled(False)
        if self.records:
            self.table.selectRow(0)

    def _show_selection(self) -> None:
        """선택 기록의 전체 제목·출처·열람 시각과 작업 정보를 일반 텍스트로 보여준다."""
        row = self.table.currentRow()
        if not 0 <= row < len(self.records):
            self.detail.clear()
            return
        record = self.records[row]
        title, source = self._source(record)
        kind = ("웹" if record.browser else record.document.file_type.upper()
                if record.document else "일반 작업")
        self.detail.setPlainText(
            f"제목: {title}\n출처 ({kind}): {source}\n"
            f"프로그램: {record.application} · {record.process_name}\n"
            f"열람 시작: {format_timestamp(record.started_at)}\n"
            f"마지막 활성: {format_timestamp(record.last_active_at)}\n"
            f"활성 시간: {format_duration(record.active_duration_ms)}"
            f" · 재방문: {record.foreground_count - 1}회\n"
            f"창 제목: {record.window_title or '(제목 없음)'}\n기록 ID: {record.id}")

    def _show_error(self, message: str) -> None:
        """실패한 검색의 이전 결과를 지우고 같은 입력으로 수동 재검색을 허용한다."""
        self._clear_results()
        self.status.setText(message)
        self.button.setEnabled(self.connected)
        self.cancel_button.setEnabled(False)
