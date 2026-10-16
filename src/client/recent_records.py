"""최근 저장 기록 목록과 새로고침 화면. DB를 직접 읽거나 쓰지 않는다."""

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from client.clipboard_widget import ClipboardWidget
from client.document_content_widget import DocumentContentWidget
from client.records_client import RecordsClient
from client.time_values import format_duration, format_timestamp, parse_timestamp
from client.web_content_widget import WebContentWidget
from shared.records import RECENT_RECORDS_LIMIT, ContextRecord


class RecentRecordsWidget(QWidget):
    """목록은 응답 단위로 교체하고 조회 실패 시 이전 기록을 비운다."""

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        """독립적인 기록 요청과 읽기 전용 목록/상세 화면을 준비한다."""
        super().__init__(parent)
        self.connected = False
        self.loaded = False
        self.records: list[ContextRecord] = []
        self.preferred_id: str | None = None
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
        layout.addWidget(self.button)
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
        for column, width in ((0, 125), (2, 120), (3, 80), (4, 140)):
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self._show_selection)
        layout.addWidget(self.table, 1)
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
        self.detail_tabs.setMinimumHeight(220)
        self.detail_tabs.setMaximumHeight(260)
        self.detail_tabs.currentChanged.connect(self._detail_tab_changed)
        layout.addWidget(self.detail_tabs)
        self.updated_at = QLabel("마지막 정상 조회: 없음")
        layout.addWidget(self.updated_at)

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
        row = self.table.currentRow()
        self.preferred_id = self.records[row].id if 0 <= row < len(self.records) else None
        self._clear_rows()
        self.status.setText("조회 중 — 최근 작업 기록을 불러오고 있습니다.")
        self.button.setEnabled(False)
        self.client.refresh()

    def _show_records(self, records: list[ContextRecord]) -> None:
        """중복 누적 없이 목록을 교체하고 같은 ID가 있으면 선택을 복원한다."""
        self.records = records
        self.table.setRowCount(len(records))
        selected = 0
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
        self.status.setText(f"최근 기록 {len(records)}건" if records else "저장된 작업 기록이 없습니다.")
        self.updated_at.setText("마지막 정상 조회: "
                               + QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))
        self.button.setEnabled(self.connected)
        if records:
            self.table.selectRow(selected)

    def _show_selection(self) -> None:
        """선택 기록의 시간과 브라우저/파일 출처를 일반 텍스트로 표시한다.

        페이지 제목과 Windows 창 제목은 다른 출처이므로 구분한다. URL을 HTML 링크로
        해석하거나 자동 실행하지 않아 긴 주소와 태그 모양의 제목도 그대로 확인할 수 있다.
        """
        row = self.table.currentRow()
        if not 0 <= row < len(self.records):
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
        self.detail.setPlainText(
            f"프로그램: {record.application} · 프로세스: {record.process_name}\n"
            f"시작: {format_timestamp(record.started_at)}\n"
            f"마지막 활성: {format_timestamp(record.last_active_at)}\n"
            f"활성 시간: {format_duration(record.active_duration_ms)}"
            f" · 재방문: {record.foreground_count - 1}회\n"
            f"창 제목: {record.window_title or '(제목 없음)'}" + browser_text + document_text)

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
