"""일반 Client의 검색 화면과 기존 관리 화면을 한 창에서 전환한다."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget

from client.compact_search_window import CompactAnswer, CompactSearchWindow
from client.window import MainWindow
from client.window_geometry import fit_window
from shared.protocol import DEFAULT_PORT


class ApplicationWindow(QWidget):
    """관리 화면 인스턴스를 유지하고 일반 실행은 작은 검색 화면에서 시작한다."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        """기존 API 클라이언트를 관리 화면에 한 번만 구성한다."""
        super().__init__()
        self.setWindowTitle("ContextTrace — 검색")
        self._management_open = False
        self._search_size = QSize(440, 112)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = CompactSearchWindow()
        layout.addWidget(self.search)

        self.management_panel = QWidget()
        management_layout = QVBoxLayout(self.management_panel)
        management_layout.setContentsMargins(0, 0, 0, 0)
        self.back_button = QPushButton("검색으로 돌아가기")
        management_layout.addWidget(self.back_button)
        self.management = MainWindow(port)
        # 작은 작업 영역에서는 관리 화면을 스크롤해 맨 아래 기능에도 접근한다.
        self.management_scroll = QScrollArea()
        self.management_scroll.setWidgetResizable(True)
        self.management_scroll.setWidget(self.management)
        management_layout.addWidget(self.management_scroll, 1)
        layout.addWidget(self.management_panel)
        self.management_panel.hide()

        menu = QMenu(self.search.management_button)
        for index in range(self.management.tabs.count()):
            action = menu.addAction(self.management.tabs.tabText(index))
            action.triggered.connect(
                lambda _checked=False, tab_index=index: self.show_management(tab_index),
            )
        self.search.management_button.setMenu(menu)
        self.search.management_button.show()
        self.search.query.setPlaceholderText("검색어 입력 · 답변 기능 준비 중")
        self.search.preferred_size_changed.connect(self._resize_search)
        self.search.search_requested.connect(self._answer_unavailable)
        self.back_button.clicked.connect(self.show_search)
        fit_window(self, self._search_size)

    def _answer_unavailable(self, request_id: int, _query: str) -> None:
        """답변 API가 연결될 때까지 기능 준비 상태를 표시한다."""
        self.search.receive_result(request_id, CompactAnswer("unavailable"))

    def _resize_search(self, target: QSize) -> None:
        """검색 상태의 목표 크기를 보관하고 검색 화면이 열려 있을 때 적용한다."""
        self._search_size = target
        if not self._management_open:
            fit_window(self, target)

    def show_management(self, index: int = 0) -> None:
        """같은 연결과 탭을 사용해 선택한 관리 화면을 연다."""
        self._management_open = True
        self.search.hide()
        self.management.tabs.setCurrentIndex(index)
        self.management_panel.show()
        fit_window(self, QSize(620, 780))
        self.back_button.setFocus()

    def show_search(self) -> None:
        """입력과 답변을 유지한 검색 화면의 크기로 돌아간다."""
        self._management_open = False
        self.management_panel.hide()
        self.search.show()
        fit_window(self, self._search_size)
        self.search.query.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """관리 화면의 Esc는 검색으로 돌아가고 다른 키는 기본 처리에 맡긴다."""
        if event.key() == Qt.Key.Key_Escape and self._management_open:
            self.show_search()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """두 화면이 소유한 통신과 대기 중인 검색을 종료한다."""
        self.search.close()
        self.management.close()
        super().closeEvent(event)
