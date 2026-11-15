"""격리된 검증 서버에서 네이티브 Client의 확인 상태와 문서 읽기 흐름을 검사한다."""

from collections import Counter
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from client.application_window import ApplicationWindow


class ReadingDiagnostic(QObject):
    """성공한 health만으로 종료하지 않고 실제 확인 응답과 읽기 화면까지 기다린다."""

    def __init__(self, window: ApplicationWindow,
                 finished: Callable[[bool, dict[str, bool]], None]) -> None:
        """결과에는 불리언만 담고 문서 본문·URL·경로·사용자 표시 설정을 기록하지 않는다."""
        super().__init__(window)
        self.window = window
        self.finished = finished
        self.checks = dict.fromkeys((
            "health_confirmed", "activity_confirmed", "privacy_confirmed",
            "document_list", "document_find", "document_source_none", "management_return",
        ), False)
        self._done = False
        self._documents_started = False
        self._documents_scheduled = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._finish(False))
        management = window.management
        management.backend.connection_changed.connect(self._health_received)
        management.activity.activity_received.connect(lambda _state: self._confirmed("activity_confirmed"))
        management.activity.activity_failed.connect(lambda _message: self._finish(False))
        management.privacy.client.state_received.connect(
            lambda _state, _operation: self._confirmed("privacy_confirmed"),
        )
        management.privacy.client.state_failed.connect(lambda _message: self._finish(False))
        management.documents.client.documents_received.connect(self._documents_received)
        management.documents.client.documents_failed.connect(lambda _message: self._finish(False))
        window.installEventFilter(self)
        self.timer.start(10_000)

    def _health_received(self, connected: bool) -> None:
        """연결 실패는 종료하고 성공 시에도 두 상태 채널의 확인 전에는 읽기를 시작하지 않는다."""
        if connected:
            self._confirmed("health_confirmed")
        else:
            self._finish(False)

    def _confirmed(self, key: str) -> None:
        """Client 파서가 승인한 상태만 확인하며 일시정지·차단을 기록 허용으로 바꾸지 않는다."""
        if self._done:
            return
        self.checks[key] = True
        if (self._documents_started or not all(self.checks[key] for key in (
                "health_confirmed", "activity_confirmed", "privacy_confirmed"))):
            return
        self._documents_started = True
        # 기존 탭 진입의 GET을 사용한다. 진단이 업로드나 설정 PUT을 만들지 않는다.
        management = self.window.management
        self.window.show_management(management.tabs.indexOf(management.documents))

    def _documents_received(self, _rows: object) -> None:
        """기존 화면의 응답 반영과 배치가 끝난 뒤 한 번만 표시 동작을 검사한다."""
        if self._done or not self._documents_started or self._documents_scheduled:
            return
        self._documents_scheduled = True
        QTimer.singleShot(0, self._exercise_reading)

    def _exercise_reading(self) -> None:
        """검증 서버의 두 문서 본문을 찾되 원본 파일·웹페이지를 실제로 열지 않는다."""
        if self._done:
            return
        documents = self.window.management.documents
        rows = documents.rows
        self.checks["document_list"] = (
            documents.loaded and not documents.busy and len(rows) == 2
            and all(row.file_type in {"pdf", "docx"} for row in rows)
        )
        if not self.checks["document_list"]:
            self._finish(False)
            return
        self.checks["document_find"] = True
        self.checks["document_source_none"] = True
        for index, row in enumerate(rows):
            documents.records.setCurrentRow(index)
            body = documents.content.toPlainText()
            # 반복 문자가 있으면 여러 일치 사이의 이동도 검사한다. 공백/제어 문자는 고르지 않는다.
            letters = Counter(char for char in body if char.isprintable() and not char.isspace())
            needle = letters.most_common(1)[0][0] if letters else ""
            if not needle:
                self.checks["document_find"] = False
                break
            finder = documents.find_bar
            finder.open()
            finder.query.setText(needle)
            first = documents.content.textCursor()
            first_position = first.selectionStart()
            first_found = first.selectedText().casefold() == needle.casefold()
            try:
                current, count = map(int, finder.result_label.text().split("/"))
            except ValueError:
                current = count = 0
            finder.find_next()
            following = documents.content.textCursor()
            moved = (
                following.selectedText().casefold() == needle.casefold()
                and (count == 1 or following.selectionStart() != first_position)
            )
            finder.find_previous()
            returned = documents.content.textCursor()
            found = (
                finder.isVisible() and finder.next_button.isEnabled()
                and current == 1 and count > 0 and first_found and moved
                and returned.selectedText().casefold() == needle.casefold()
                and returned.selectionStart() == first_position
                and finder.result_label.text() == f"1/{count}"
                and documents.content.isReadOnly() and documents.content.toPlainText() == body
            )
            self.checks["document_find"] &= found
            self.checks["document_source_none"] &= (
                row.record_id is None and row.file_path is None
                and documents.source_actions.file_path is None
                and documents.source_actions.url is None and not documents.source_actions.isEnabled()
            )
            finder.close_button.click()
            self.checks["document_find"] &= finder.isHidden()
        # 앱 내부의 키 이벤트만 전달한다. 운영체제 입력기·실제 키보드 조작의 검증은 아니다.
        QApplication.sendEvent(self.window.back_button, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier,
        ))
        self.checks["management_return"] = (
            self.window.search.isVisible() and not self.window.management_panel.isVisible()
        )
        self._finish(all(self.checks.values()))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """사용자가 진단 창을 먼저 닫으면 이후 지연 응답을 성공으로 기록하지 않는다."""
        if watched is self.window and event.type() == QEvent.Type.Close:
            self._finish(False)
        return super().eventFilter(watched, event)

    def cancel(self) -> None:
        """명시적 취소도 실패 한 번으로 끝내고 타이머·늦은 신호의 재완료를 막는다."""
        self._finish(False)

    def _finish(self, success: bool) -> None:
        """성공·실패·시간 초과·창 닫힘을 하나의 완료 경계로 모은다."""
        if self._done:
            return
        self._done = True
        self.timer.stop()
        self.finished(success, dict(self.checks))
