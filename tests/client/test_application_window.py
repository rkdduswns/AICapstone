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
from shared.browser import BrowserPage
from shared.search_data import DocumentChunk, SourceMetadata

QUERY = "개인정보 저장 기준을 찾아줘"


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
