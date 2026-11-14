"""최근 저장 기록 목록과 새로고침 화면. DB를 직접 읽거나 쓰지 않는다."""

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client.clipboard_widget import ClipboardWidget
from client.document_content_widget import DocumentContentWidget
from client.records_client import RecordsClient
from client.theme import set_reading_text, set_role
from client.time_values import format_duration, format_timestamp, parse_timestamp
from client.web_content_widget import WebContentWidget
from shared.records import RECENT_RECORDS_LIMIT, ContextRecord


class RecentRecordsWidget(QWidget):
    """목록은 응답 단위로 교체하고 조회 실패 시 이전 기록을 비운다."""

    document_requested = Signal(object)

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """독립적인 기록 요청과 읽기 전용 목록/상세 화면을 준비한다."""
        super().__init__(parent)
        self.connected = False
        self.loaded = False
        self.records: list[ContextRecord] = []
        self.preferred_id: str | None = None
        self._syncing_timeline = False
        self._timeline_items: dict[str, QTreeWidgetItem] = {}
        self.client = RecordsClient(port, self)
        self.client.records_received.connect(self._show_records)
        self.client.records_failed.connect(self._show_error)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"최근 {RECENT_RECORDS_LIMIT}건 · 마지막 활성 시각순 · PC 현지 시각"))
        self.status = QLabel("대기 — Backend 연결을 확인해 주세요.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.button = QPushButton("최근 기록 새로고침")
        self.button.setEnabled(False)
        self.button.clicked.connect(self.refresh)
        self.attach_button = QPushButton("선택한 작업에 문서 연결")
        self.attach_button.setEnabled(False)
        self.attach_button.clicked.connect(self._attach_document)
        set_role(self.attach_button, "primary")
        set_role(self.button, "quiet")
        controls = QHBoxLayout()
        controls.addWidget(self.button)
        controls.addWidget(self.attach_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.filter_edit = QLineEdit()
        self.filter_edit.setAccessibleName("불러온 최근 기록 빠른 필터")
        self.filter_edit.setPlaceholderText(
            f"불러온 최근 {RECENT_RECORDS_LIMIT}건에서 제목·프로그램·출처 찾기")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._filter_records)
        self.view_selector = QComboBox()
        self.view_selector.setAccessibleName("최근 기록 보기 방식")
        self.view_selector.addItem("목록 보기", "list")
        self.view_selector.addItem("날짜별 보기", "timeline")
        self.view_selector.setToolTip("마지막 활성 시각을 기준으로 받은 최근 20건만 날짜별로 표시합니다.")
        filter_row = QHBoxLayout()
        filter_row.addWidget(self.filter_edit, 1)
        filter_row.addWidget(self.view_selector)
        layout.addLayout(filter_row)
        self.reading_splitter = QSplitter(Qt.Orientation.Vertical)
        self.reading_splitter.setChildrenCollapsible(False)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["프로그램", "창 제목", "마지막 활성", "활성 시간", "파일 출처"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 110), (2, 120), (3, 75), (4, 140)):
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self._show_selection)
        self.table.setMinimumHeight(100)
        self.timeline = QTreeWidget()
        self.timeline.setAccessibleName("받은 최근 기록의 날짜별 타임라인")
        self.timeline.setHeaderLabels(["마지막 활성 · 프로그램", "창 제목"])
        self.timeline.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.timeline.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.timeline.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.timeline.setRootIsDecorated(False)
        self.timeline.setItemsExpandable(False)
        self.timeline.setExpandsOnDoubleClick(False)
        self.timeline.setAlternatingRowColors(True)
        self.timeline.setWordWrap(False)
        self.timeline.setMinimumHeight(100)
        self.timeline.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.timeline.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.timeline.setColumnWidth(0, 190)
        self.timeline.itemSelectionChanged.connect(self._timeline_selection_changed)
        self.timeline.currentItemChanged.connect(self._timeline_current_changed)
        self.record_views = QStackedWidget()
        self.record_views.addWidget(self.table)
        self.record_views.addWidget(self.timeline)
        self.reading_splitter.addWidget(self.record_views)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setTabChangesFocus(True)
        self.detail.setPlaceholderText("기록을 선택하면 전체 제목과 시간 정보를 확인할 수 있습니다.")
        self.detail_tabs = QTabWidget()
        self.detail_tabs.addTab(self.detail, "작업 정보")
        self.clipboard = ClipboardWidget(port, self)
        self.detail_tabs.addTab(self.clipboard, "복사 텍스트")
        self.web_content = WebContentWidget(port, self)
        self.detail_tabs.addTab(self.web_content, "웹 본문")
        self.document_content = DocumentContentWidget(port, self)
        self.detail_tabs.addTab(self.document_content, "문서 본문")
        self.detail_tabs.setMinimumHeight(170)
        self.detail_tabs.currentChanged.connect(self._detail_tab_changed)
        self.reading_splitter.addWidget(self.detail_tabs)
        self.reading_splitter.setStretchFactor(0, 3)
        self.reading_splitter.setStretchFactor(1, 2)
        self.reading_splitter.handle(1).setToolTip("경계를 끌어 목록과 본문의 읽기 높이를 조절합니다.")
        layout.addWidget(self.reading_splitter, 1)
        self.updated_at = QLabel("마지막 정상 조회: 없음")
        layout.addWidget(self.updated_at)
        self.view_selector.currentIndexChanged.connect(self._change_view)

    def set_connected(self, connected: bool) -> None:
        """연결 재확인 시 요청을 취소하고 그 전 서버에서 받은 기록을 지운다."""
        self.client.close()
        self.connected = connected
        self.loaded = False
        self.preferred_id = None
        self._clear_rows()
        self.status.setText("조회 대기 — 최근 기록을 확인해 주세요." if connected
                            else "대기 — Backend 연결을 확인해 주세요.")
        self.button.setEnabled(connected)

    def load_if_needed(self) -> None:
        """탭을 처음 열었을 때만 자동 조회하며 이후에는 새로고침 버튼을 사용한다."""
        if self.connected and not self.loaded:
            self.refresh()

    def refresh(self) -> None:
        """현재 선택을 기억하고 요청 중 버튼을 잠가 중복 클릭을 막는다."""
        if not self.connected or self.client.reply is not None:
            return
        row = self._selected_table_row()
        self.preferred_id = self.records[row].id if row >= 0 else None
        self._clear_rows()
        self.status.setText("조회 중 — 최근 작업 기록을 불러오고 있습니다.")
        self.button.setEnabled(False)
        self.client.refresh()

    def _selected_table_row(self) -> int:
        """선택 해제 뒤에도 남는 currentRow 대신 실제 선택한 보이는 행만 사용한다."""
        selected = self.table.selectionModel().selectedRows()
        if len(selected) != 1:
            return -1
        row = selected[0].row()
        return row if 0 <= row < len(self.records) and not self.table.isRowHidden(row) else -1

    def _show_records(self, records: list[ContextRecord]) -> None:
        """중복 누적 없이 목록을 교체하고 같은 ID가 있으면 선택을 복원한다."""
        self.records = records
        self.table.setRowCount(len(records))
        selected = -1
        for row, record in enumerate(records):
            if record.id == self.preferred_id:
                selected = row
            values = (record.application, record.window_title or "(제목 없음)",
                      parse_timestamp(record.last_active_at).astimezone().strftime("%m-%d %H:%M:%S"),
                      format_duration(record.active_duration_ms),
                      record.document.file_path if record.document else "—")
            for column, value in enumerate(values):
                # 기본 표 항목은 문자열을 HTML로 해석하지 않는다. 원문은 아래 상세란에 보존한다.
                item = QTableWidgetItem(value)
                # 긴 경로는 가로 스크롤·툴팁과 작업 상세에서 원문 전체를 확인한다.
                if column == 4 and record.document:
                    item.setToolTip(record.document.file_path)
                self.table.setItem(row, column, item)
        self.loaded = True
        self.updated_at.setText("마지막 정상 조회: "
                               + QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))
        self.button.setEnabled(self.connected)
        if selected >= 0:
            self.table.selectRow(selected)
        self._filter_records()

    def _filter_records(self, _text: str = "") -> None:
        """받은 최대 20건만 숨김 처리하며 실제 행·ID 연결과 서버 조회 순서를 유지한다."""
        query = self.filter_edit.text().strip().casefold()
        visible = []
        for row, record in enumerate(self.records):
            fields = [record.application, record.process_name, record.window_title]
            if record.browser:
                fields += [record.browser.page_title or "", record.browser.url or ""]
            if record.document:
                fields.append(record.document.file_path)
            match = not query or query in "\n".join(fields).casefold()
            self.table.setRowHidden(row, not match)
            if match:
                visible.append(row)
        self._rebuild_timeline(visible)
        selected = self._selected_table_row()
        if visible:
            if selected not in visible:
                self.table.selectRow(visible[0])
            self._show_selection()
        else:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self._show_selection()
        if not self.loaded:
            return
        if query:
            self.status.setText(f"불러온 {len(self.records)}건 중 {len(visible)}건 · 현재 목록 안에서만 필터")
        else:
            self.status.setText(f"최근 기록 {len(self.records)}건" if self.records
                                else "저장된 작업 기록이 없습니다.")

    def _rebuild_timeline(self, visible_rows: list[int]) -> None:
        """받은 기록의 현지 날짜만 묶고 세션·하루 전체 이력·활성 구간을 추정하지 않는다."""
        self._syncing_timeline = True
        try:
            self.timeline.clear()
            self._timeline_items.clear()
            groups: dict[str, QTreeWidgetItem] = {}
            counts: dict[str, int] = {}
            for row in visible_rows:
                record = self.records[row]
                local_time = parse_timestamp(record.last_active_at).astimezone()
                day = local_time.date().isoformat()
                if day not in groups:
                    heading = QTreeWidgetItem(self.timeline)
                    heading.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    heading.setFirstColumnSpanned(True)
                    font = heading.font(0)
                    font.setBold(True)
                    heading.setFont(0, font)
                    groups[day], counts[day] = heading, 0
                heading = groups[day]
                counts[day] += 1
                heading.setText(0, f"{day} · 현재 목록 {counts[day]}건")
                item = QTreeWidgetItem(heading, [
                    f"{local_time:%H:%M:%S} · {record.application}",
                    record.window_title or "(제목 없음)",
                ])
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setData(0, Qt.ItemDataRole.UserRole, record.id)
                # 원문 제목·주소를 툴팁의 자동 rich text 해석에 넘기지 않는다.
                item.setToolTip(0, "마지막 활성: " + format_timestamp(record.last_active_at))
                item.setToolTip(1, "선택하면 작업 정보와 원본 출처를 확인할 수 있습니다.")
                self._timeline_items[record.id] = item
            self.timeline.expandAll()
        finally:
            self._syncing_timeline = False

    def _change_view(self, _index: int) -> None:
        """보기만 바꾸며 선택된 본문·필터·조회 결과를 다시 요청하거나 초기화하지 않는다."""
        self.record_views.setCurrentWidget(
            self.timeline if self.view_selector.currentData() == "timeline" else self.table)
        self._sync_timeline_selection()

    def _sync_timeline_selection(self) -> None:
        """표의 실제 선택 ID만 날짜별 보기에 전달해 두 표시의 연결 대상을 일치시킨다."""
        if self._syncing_timeline:
            return
        row = self._selected_table_row()
        valid = row >= 0
        item = self._timeline_items.get(self.records[row].id) if valid else None
        if self.timeline.currentItem() is item and (item is None or item.isSelected()):
            return
        self._syncing_timeline = True
        try:
            self.timeline.clearSelection()
            self.timeline.setCurrentItem(item)
            if item is not None:
                item.setSelected(True)
        finally:
            self._syncing_timeline = False

    def _clear_timeline_selection(self) -> None:
        """날짜 머리글이나 선택 해제는 이전 기록을 연결 대상으로 남기지 않는다."""
        self._syncing_timeline = True
        try:
            # 머리글의 current 위치는 남겨 키보드가 다음 실제 항목으로 이동할 수 있게 한다.
            self.timeline.clearSelection()
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self._show_selection()
        finally:
            self._syncing_timeline = False

    def _timeline_current_changed(self, current: QTreeWidgetItem | None,
                                  _previous: QTreeWidgetItem | None) -> None:
        """키보드·강제 current 변경으로 날짜 머리글이 활성화돼도 실제 작업을 고르지 않는다."""
        if self._syncing_timeline:
            return
        if current is None or not isinstance(current.data(0, Qt.ItemDataRole.UserRole), str):
            self._clear_timeline_selection()

    def _timeline_selection_changed(self) -> None:
        """날짜별 항목의 실제 ID를 기존 표 행에 대응시키고 같은 상세 경로를 재사용한다."""
        if self._syncing_timeline:
            return
        selected = self.timeline.selectedItems()
        identifier = selected[0].data(0, Qt.ItemDataRole.UserRole) if len(selected) == 1 else None
        row = next((index for index, record in enumerate(self.records)
                    if record.id == identifier and not self.table.isRowHidden(index)), -1)
        if row < 0 or self._timeline_items.get(identifier) is not selected[0]:
            self._clear_timeline_selection()
            return
        self.table.selectRow(row)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """좁은 목록에서는 긴 경로 열을 접고 선택 상세에서 원본을 그대로 확인한다."""
        super().resizeEvent(event)
        if hasattr(self, "table"):
            self.table.setColumnHidden(4, self.width() < 720)

    def _show_selection(self) -> None:
        """선택 기록의 시간과 브라우저/파일 출처를 일반 텍스트로 표시한다.

        페이지 제목과 Windows 창 제목은 다른 출처이므로 구분한다. URL을 HTML 링크로
        해석하거나 자동 실행하지 않아 긴 주소와 태그 모양의 제목도 그대로 확인할 수 있다.
        """
        row = self._selected_table_row()
        valid = row >= 0
        self._sync_timeline_selection()
        self.attach_button.setEnabled(self.connected and valid)
        if not valid:
            self.detail.clear()
            self.clipboard.set_record(None)
            self.web_content.set_record(None)
            self.document_content.set_record(None)
            return
        record = self.records[row]
        self.clipboard.set_record(record.id)
        self.web_content.set_record(record)
        self.document_content.set_record(record)
        self._detail_tab_changed(self.detail_tabs.currentIndex())
        browser_text = "\n브라우저 출처: 없음 / 서버 미제공"
        if record.browser is not None:
            page = record.browser
            browser_name = "Google Chrome" if page.browser == "chrome" else "Microsoft Edge"
            browser_text = (f"\n브라우저: {browser_name}\n페이지 제목: {page.page_title or '(제목 없음)'}"
                            f"\nURL: {page.url or '없음 (새 탭·내부 페이지 등)'}")
        document_text = "\n파일 출처: 없음 / 서버 미제공"
        if record.document is not None:
            document_text = (f"\n문서 유형: {record.document.file_type.upper()}"
                             f"\n파일 경로: {record.document.file_path}")
        set_reading_text(self.detail,
            f"프로그램: {record.application} · 프로세스: {record.process_name}\n"
            f"시작: {format_timestamp(record.started_at)}\n"
            f"마지막 활성: {format_timestamp(record.last_active_at)}\n"
            f"활성 시간: {format_duration(record.active_duration_ms)}"
            f" · 재방문: {record.foreground_count - 1}회\n"
            f"창 제목: {record.window_title or '(제목 없음)'}" + browser_text + document_text)

    def _attach_document(self) -> None:
        """선택된 실제 저장 기록을 연결 대상으로 전달하고 파일 내용을 직접 추출하지 않는다."""
        row = self._selected_table_row()
        if self.connected and row >= 0:
            if self.view_selector.currentData() == "timeline":
                item = self.timeline.currentItem()
                if (item is None or not item.isSelected()
                        or item.data(0, Qt.ItemDataRole.UserRole) != self.records[row].id
                        or self._timeline_items.get(self.records[row].id) is not item):
                    return
            self.document_requested.emit(self.records[row])

    def _detail_tab_changed(self, index: int) -> None:
        """복사 텍스트·웹/문서 본문은 사용자가 해당 상세 탭을 열 때만 별도로 조회한다."""
        if self.detail_tabs.widget(index) is self.clipboard:
            self.clipboard.load_if_needed()
        elif self.detail_tabs.widget(index) is self.web_content:
            self.web_content.load_if_needed()
        elif self.detail_tabs.widget(index) is self.document_content:
            self.document_content.load_if_needed()

    def _clear_rows(self) -> None:
        """이전 응답과 선택된 상세 내용이 새 결과에 섞이지 않도록 비운다."""
        self.records = []
        self.loaded = False
        self.attach_button.setEnabled(False)
        self._syncing_timeline = True
        try:
            self.timeline.clear()
            self._timeline_items.clear()
        finally:
            self._syncing_timeline = False
        self.table.setRowCount(0)
        self.detail.clear()
        self.clipboard.set_record(None)
        self.web_content.set_record(None)
        self.document_content.set_record(None)

    def _show_error(self, message: str) -> None:
        """빈 목록과 오류를 구분하며 수동 새로고침으로 복구할 수 있게 한다."""
        self._clear_rows()
        self.preferred_id = None
        self.status.setText(message)
        self.button.setEnabled(self.connected)
