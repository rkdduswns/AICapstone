"""일반 Client의 검색 화면과 기존 관리 화면을 한 창에서 전환한다."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget

from client.compact_search_window import CompactAnswer, CompactSearchWindow
from client.window import MainWindow
from client.window_geometry import fit_window
from shared.activity import CurrentActivity
from shared.privacy import PrivacyState
from shared.protocol import DEFAULT_PORT


class ApplicationWindow(QWidget):
    """관리 화면 인스턴스를 유지하고 일반 실행은 작은 검색 화면에서 시작한다."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        """기존 API 클라이언트를 관리 화면에 한 번만 구성한다."""
        super().__init__()
        self.setWindowTitle("ContextTrace — 검색")
        self._management_open = False
        self._search_size = QSize(440, 112)
        self._connection_state = "unknown"
        self._activity_state = "unknown"
        self._privacy_state = "unknown"
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
        self.search.connection_button.show()
        self.search.connection_button.clicked.connect(lambda: self.show_management(0))
        self.management.check_started.connect(self._connection_check_started)
        self.management.backend.connection_changed.connect(self._connection_changed)
        self.management.activity.activity_received.connect(self._activity_received)
        self.management.activity.activity_failed.connect(self._activity_failed)
        self.management.privacy.client.state_received.connect(self._privacy_received)
        self.management.privacy.client.state_failed.connect(self._privacy_failed)
        self.management.privacy.client.changing.connect(self._privacy_changing)
        self._show_connection_status()
        self.search.query.setPlaceholderText("검색어 입력 · 답변 기능 준비 중")
        self.search.preferred_size_changed.connect(self._resize_search)
        self.search.search_requested.connect(self._answer_unavailable)
        self.back_button.clicked.connect(self.show_search)
        fit_window(self, self._search_size)

    def _connection_check_started(self) -> None:
        """같은 관리 화면에서 재확인할 때 이전 채널의 확인값을 함께 비운다."""
        self._connection_state = "checking"
        self._activity_state = self._privacy_state = "unknown"
        self._show_connection_status()

    def _connection_changed(self, connected: bool) -> None:
        """건강 확인과 실제 작업·보호 상태의 수신 여부를 구분한다."""
        self._connection_state = "connected" if connected else "failed"
        self._activity_state = self._privacy_state = "unknown"
        self._show_connection_status()

    def _activity_received(self, activity: CurrentActivity) -> None:
        """현재 작업 채널의 성공만 갱신하여 다른 채널의 실패를 보존한다."""
        self._activity_state = activity.collection_status
        self._show_connection_status()

    def _activity_failed(self, _message: str) -> None:
        """마지막 건강 확인이 성공했어도 작업 수신 실패를 현재 상태에 반영한다."""
        self._activity_state = "failed"
        self._show_connection_status()

    def _privacy_received(self, state: PrivacyState, _operation: str) -> None:
        """Backend가 확인한 기록 사유만 사용하고 창 감지에서 저장 여부를 추정하지 않는다."""
        self._privacy_state = state.recording.reason
        self._show_connection_status()

    def _privacy_failed(self, _message: str) -> None:
        """보호 상태 수신 실패가 현재 작업의 성공 응답으로 지워지지 않게 한다."""
        self._privacy_state = "failed"
        self._show_connection_status()

    def _privacy_changing(self) -> None:
        """설정 적용을 기다리는 동안 이전 기록 가능 판정을 사용하지 않는다."""
        self._privacy_state = "changing"
        self._show_connection_status()

    def _show_connection_status(self) -> None:
        """독립적으로 수신하는 상태를 보수적으로 조합해 짧은 버튼과 안전한 설명을 표시한다."""
        connection = {
            "unknown": ("연결 미확인", "Backend 연결을 확인해 주세요."),
            "checking": ("연결 확인 중", "현재 작업과 보호 상태를 새로 확인하고 있습니다."),
            "failed": ("연결 확인 실패", "Backend 실행과 연결 설정을 확인해 주세요."),
        }
        restricted = {
            "paused": "기록 일시정지", "blocked_program": "프로그램 차단",
            "blocked_url": "URL 차단", "sensitive_content": "민감정보 차단",
            "no_active_window": "활성 창 없음", "unsupported": "미지원 환경",
            "error": "보호 상태 오류",
        }
        activity = {
            "no_active_window": "활성 창 없음", "unsupported": "감지 미지원", "error": "감지 오류",
        }
        if self._connection_state in connection:
            label, description = connection[self._connection_state]
        elif "failed" in (self._activity_state, self._privacy_state):
            label = "상태 수신 실패"
            description = "마지막 연결 확인 후 현재 작업 또는 보호 상태를 받지 못했습니다."
        elif self._privacy_state == "changing":
            label, description = "연결됨 · 설정 확인 중", "서버의 개인정보 설정 적용 결과를 기다립니다."
        elif self._privacy_state in restricted:
            label = "연결됨 · " + restricted[self._privacy_state]
            description = "Backend가 마지막으로 확인한 기록 상태입니다."
        elif self._activity_state in activity:
            label = "연결됨 · " + activity[self._activity_state]
            description = "현재 작업의 감지 상태를 확인해 주세요."
        elif "unknown" in (self._activity_state, self._privacy_state):
            label, description = "연결됨 · 상태 확인 중", "현재 작업과 보호 상태를 기다리고 있습니다."
        elif self._activity_state == "collecting" and self._privacy_state == "allowed":
            label, description = "연결됨 · 기록 가능", "현재 작업과 보호 상태를 모두 확인했습니다."
        else:
            label, description = "연결됨 · 상태 확인 중", "현재 작업과 보호 상태를 다시 확인해 주세요."
        self.search.connection_button.setText(label)
        self.search.connection_button.setToolTip(description + " 현재 작업과 연결 설정을 엽니다.")

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
