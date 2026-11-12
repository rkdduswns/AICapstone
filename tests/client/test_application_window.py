"""일반 실행의 작은 검색 창과 기존 관리 화면 사이의 연결을 검증한다."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from client.application_window import ApplicationWindow
from client.compact_search_window import CompactAnswer
from client.window import MainWindow
from shared.activity import ActiveWindow, CurrentActivity
from shared.browser import BrowserPage
from shared.privacy import PrivacySettings, PrivacyState, RecordingStatus
from shared.search_data import DocumentChunk, SourceMetadata

QUERY = "개인정보 저장 기준을 찾아줘"
ACTIVITY = CurrentActivity("collecting", ActiveWindow("가상 앱", "fixture.exe", 42, "가상 창"))


def privacy_state(reason="allowed"):
    """서버가 판정한 상태를 전달하는 고정 응답을 만들며 실제 설정을 변경하지 않는다."""
    return PrivacyState(
        PrivacySettings(reason == "paused", ["blocked.exe"] if reason == "blocked_program" else []),
        RecordingStatus(reason == "allowed", reason),
    )


@pytest.fixture
def status_clients(shell, monkeypatch):
    """기존 신호 전달만 검사하고 건강 확인에 따른 실제 네트워크 시작은 격리한다."""
    management = shell.management
    monkeypatch.setattr(management.activity, "start", lambda: None)
    monkeypatch.setattr(management.privacy.client, "start", lambda: None)
    return management.backend, management.activity, management.privacy.client


@pytest.fixture(scope="module")
def app():
    """모든 화면에 같은 Qt 애플리케이션과 이벤트 루프를 제공한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def shell(app):
    """기본 실행 셸을 표시하고 테스트 종료 시 네트워크 요청을 함께 정리한다."""
    window = ApplicationWindow()
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window
    window.close()
    app.processEvents()


@pytest.fixture
def delayed_server():
    """종료 전까지 응답을 보류해 실제 Qt 요청의 취소 상태를 확인한다."""
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """본문이 없는 가상 응답을 반환하며 Client의 취소를 허용한다."""
            release.wait(timeout=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(b"{}")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def log_message(self, *_args):
            """가상 요청도 콘솔에 기록하지 않는다."""
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_normal_start_is_small_and_opens_empty_results_manually(app, shell):
    """일반 실행에서도 검색 전 결과를 열 수 있고 관리 화면이 최소 크기를 키우지 않는다."""
    initial = shell.size()
    assert initial.width() <= 480 and initial.height() <= 150
    assert shell.search.isVisible()
    assert not shell.management.isVisible()
    assert shell.search.query.hasFocus()
    assert shell.search.management_button.isVisible()
    assert shell.search.window() is shell
    assert shell.management.window() is shell
    assert not shell.search.search_button.isEnabled()

    shell.search.results_button.click()
    app.processEvents()
    assert shell.search.empty_message.isVisible()
    assert shell.height() > initial.height()
    shell.search.results_button.click()
    app.processEvents()
    assert shell.size() == initial


def test_menu_reuses_management_tabs_and_roundtrip_preserves_search(app, shell):
    """관리 동작은 기존 한 인스턴스를 열고 돌아오면 입력·답변·정렬이 복원된다."""
    search, management = shell.search, shell.management
    actions = search.management_button.menu().actions()
    expected_tabs = [management.tabs.tabText(index) for index in range(management.tabs.count())]
    assert [action.text() for action in actions] == expected_tabs
    assert shell.findChildren(MainWindow) == [management]

    chunk = DocumentChunk(
        "fixture-chunk", "fixture-record", 0, "가상 출처의 관련 본문",
        SourceMetadata(
            "web", "가상 앱", "chrome.exe", "가상 창",
            "2026-11-08T09:00:00+09:00", "2026-11-08T09:02:00+09:00",
            "2026-11-08T09:01:00+09:00", False,
            browser=BrowserPage("chrome", "가상 자료", "https://example.test/research"),
        ),
    )
    response = CompactAnswer("answer", "가상 요약", "가상 전체 답변", (chunk,))
    # 일반 실행의 미지원 응답 대신 화면 상태 보존을 검사할 고정 응답을 주입한다.
    search.search_requested.disconnect()
    search.search_requested.connect(lambda identifier, _query: search.receive_result(identifier, response))
    search.query.setText(QUERY)
    search.submit()
    search.detail_button.click()
    search.evidence_order.setCurrentIndex(search.evidence_order.findData("longest"))
    previous_size = shell.size()
    previous_detail = search.detail_text.toPlainText()

    for index, action in enumerate(actions):
        action.trigger()
        app.processEvents()
        assert shell.management is management and shell.search is search
        assert management.isVisible() and not search.isVisible()
        assert management.tabs.currentIndex() == index
        assert shell.back_button.isVisible()
        assert shell.findChildren(MainWindow) == [management]
        if index == 0:
            QTest.keyClick(shell.back_button, Qt.Key.Key_Escape)
        else:
            shell.back_button.click()
        app.processEvents()
        assert search.isVisible() and not management.isVisible()
        assert search.query.text() == QUERY
        assert search.detail_panel.isVisible()
        assert search.detail_text.toPlainText() == previous_detail
        assert search.evidence_order.currentData() == "longest"
        assert shell.size() == previous_size


def test_normal_query_reports_answer_service_preparation_without_example_answer(shell):
    """일반 검색은 실제 답변 계약의 준비 상태를 알리고 가상 답변을 표시하지 않는다."""
    search = shell.search
    search.query.setText(QUERY)
    QTest.keyClick(search.query, Qt.Key.Key_Return)
    assert "준비" in search.status.text()
    assert not search.summary.isVisible()
    assert search.summary.text() == ""
    assert search.detail_text.toPlainText() == ""
    assert search.evidence_picker.count() == 0
    assert search.search_button.isEnabled()
    assert search.search_button.text() == "검색"


def test_connection_state_requires_both_channels_and_preserves_failures(shell, status_clients):
    """한 채널의 새 성공이 다른 채널의 수신 실패나 설정 확인 중 상태를 덮지 않는다."""
    backend, activity, privacy = status_clients
    button = shell.search.connection_button
    assert button.text() == "연결 미확인"
    backend.connection_changed.emit(True)
    assert "확인 중" in button.text()
    activity.activity_received.emit(ACTIVITY)
    assert "기록 가능" not in button.text()
    privacy.state_received.emit(privacy_state(), "read")
    assert button.text() == "연결됨 · 기록 가능"

    activity.activity_failed.emit("가상 민감 오류 본문")
    privacy.state_received.emit(privacy_state(), "read")
    assert button.text() == "상태 수신 실패"
    assert "민감 오류" not in button.toolTip()
    activity.activity_received.emit(ACTIVITY)
    assert button.text() == "연결됨 · 기록 가능"

    privacy.state_failed.emit("가상 민감 오류 본문")
    activity.activity_received.emit(ACTIVITY)
    assert button.text() == "상태 수신 실패"
    privacy.state_received.emit(privacy_state(), "read")
    assert button.text() == "연결됨 · 기록 가능"
    privacy.changing.emit()
    activity.activity_received.emit(ACTIVITY)
    assert "설정 확인 중" in button.text()
    privacy.state_received.emit(privacy_state("paused"), "pause")
    assert "일시정지" in button.text()
    activity.activity_received.emit(ACTIVITY)
    assert "일시정지" in button.text()

    privacy.state_received.emit(privacy_state("blocked_program"), "read")
    assert "프로그램 차단" in button.text()
    backend.connection_changed.emit(False)
    activity.activity_received.emit(ACTIVITY)
    privacy.state_received.emit(privacy_state(), "read")
    assert button.text() == "연결 확인 실패"


@pytest.mark.parametrize("collection_status", ["no_active_window", "unsupported", "error"])
def test_activity_status_prevents_stale_recording_allowed(shell, status_clients, collection_status):
    """이전 기록 허용 응답보다 현재 활성 창 없음·미지원·오류를 우선한다."""
    backend, activity, privacy = status_clients
    backend.connection_changed.emit(True)
    privacy.state_received.emit(privacy_state(), "read")
    activity.activity_received.emit(ACTIVITY)
    assert "기록 가능" in shell.search.connection_button.text()

    activity.activity_received.emit(CurrentActivity(collection_status, None))
    privacy.state_received.emit(privacy_state(), "read")
    assert "기록 가능" not in shell.search.connection_button.text()
    assert shell.search.connection_button.text().startswith("연결됨")


def test_connection_button_reuses_management_and_recheck_clears_status(app, shell, monkeypatch):
    """상태 버튼은 같은 관리 화면을 열고 명시적인 재확인에서만 건강 요청을 보낸다."""
    management = shell.management
    clients = (management.backend, management.activity, management.privacy.client)
    calls = []
    for client in clients:
        monkeypatch.setattr(client, "get", lambda path: calls.append(path))
    assert shell.search.connection_button.isVisible()
    for _ in range(2):
        shell.search.connection_button.click()
        app.processEvents()
        assert shell.management is management and management.tabs.currentIndex() == 0
        assert shell.management.isVisible()
        shell.back_button.click()
        app.processEvents()
    assert calls == []
    assert shell.findChildren(MainWindow) == [management]
    assert all(not client.timer.isActive() for client in clients)

    management.backend.connection_changed.emit(True)
    management.activity.activity_received.emit(ACTIVITY)
    management.privacy.client.state_received.emit(privacy_state(), "read")
    assert shell.search.connection_button.text() == "연결됨 · 기록 가능"
    calls.clear()
    started = []
    management.check_started.connect(lambda: started.append(True))
    management.backend.reply = object()
    try:
        management.check()
        assert started == []
    finally:
        management.backend.reply = None
    management.check()
    assert started == [True] and calls == ["/health"]
    assert shell.search.connection_button.text() == "연결 확인 중"


def test_management_fits_small_screen_and_keeps_back_button_accessible(app, shell, monkeypatch):
    """작은 작업 영역에서는 관리 본문만 스크롤하고 복귀 버튼과 창은 화면 안에 둔다."""
    bounds = QRect(30, 40, 360, 360)
    screen = SimpleNamespace(availableGeometry=lambda: bounds)
    monkeypatch.setattr(shell, "screen", lambda: screen)

    shell.show_management()
    app.processEvents()

    assert bounds.contains(shell.frameGeometry())
    assert shell.management_scroll.verticalScrollBar().maximum() > 0
    button_bounds = QRect(shell.back_button.mapToGlobal(QPoint()), shell.back_button.size())
    assert shell.back_button.isVisible()
    assert bounds.contains(button_bounds)
    assert shell.management_scroll.widget() is shell.management

    shell.back_button.click()
    app.processEvents()
    assert shell.search.isVisible()
    assert bounds.contains(shell.frameGeometry())


def test_close_aborts_management_requests_and_stops_polling(app, delayed_server):
    """관리 화면을 숨겨 둔 경우에도 셸 종료는 요청과 반복 조회를 정리한다."""
    window = ApplicationWindow(delayed_server)
    window.show()
    window.show_management()
    management = window.management
    management.check()
    management.activity.start()
    management.privacy.client.start()
    clients = (management.backend, management.activity, management.privacy.client)
    assert all(client.reply is not None for client in clients)

    window.show_search()
    window.close()
    app.processEvents()

    assert all(client.reply is None for client in clients)
    assert all(not client.timer.isActive() for client in clients)
    assert not management.activity.active
    assert not management.privacy.client.active
    assert not management.activity.poll_timer.isActive()
    assert not management.privacy.client.poll_timer.isActive()
    assert not window.isVisible()
