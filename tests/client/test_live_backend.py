"""Qt Client를 가상 HTTP 응답 대신 실제 FastAPI·추적기·SQLite에 연결한다."""

import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import uvicorn
from docx import Document
from PySide6.QtWidgets import QApplication

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from client.window import MainWindow


@pytest.fixture(scope="module")
def app():
    """Qt 이벤트 루프를 모듈 동안 유지한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, condition, timeout=8):
    """실제 HTTP 콜백이 진행되도록 이벤트를 처리하며 조건을 기다린다."""
    deadline = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("실제 Backend 응답을 기다리는 중 시간 초과")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def live_backend(tmp_path):
    """운영체제 감지만 가상화하고 실제 Uvicorn 서버를 예약한 loopback 소켓에서 연다."""
    state = SimpleNamespace(process="chrome.exe", title="가상 조사 자료", tick=0.0)
    detector = SimpleNamespace(
        get_active_window_handle=lambda: 1, get_process_id=lambda handle: 42,
        get_process_name=lambda pid: state.process, normalize_app_name=lambda name: name,
        get_window_title=lambda handle: state.title,
    )
    store = ActivityStore(tmp_path / "activity.db")
    tracker = ActivityTracker(
        detector=detector, store=store, clock=lambda: state.tick,
        now=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc) + timedelta(seconds=state.tick),
    )
    backend = create_app(activity_tracker=tracker, activity_store=store, collection_interval=None,
                         clipboard_reader=lambda: "가상 복사 원문")
    server = uvicorn.Server(uvicorn.Config(backend, log_level="warning", access_log=False))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started:
            assert thread.is_alive(), "Backend가 시작 전에 종료됐습니다."
            assert time.monotonic() < deadline
            time.sleep(0.005)
        try:
            yield port, state, store
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.fixture
def window(app, live_backend):
    """서버보다 먼저 창과 모든 요청을 종료해 늦은 응답이 다음 테스트에 섞이지 않게 한다."""
    widget = MainWindow(live_backend[0])
    widget.activity.poll_timer.setInterval(20)
    widget.privacy.client.poll_timer.setInterval(20)
    widget.show()
    try:
        widget.check()
        wait_for(app, lambda: widget.privacy.state is not None and widget.application.text() != "—")
        yield widget
    finally:
        widget.close()
        app.processEvents()


def test_real_activity_pause_resume_and_program_block(app, window):
    """UI의 버튼과 설정 입력이 실제 보호 판정에 반영되고 새 상태를 Client가 수신한다."""
    assert window.application.text() == "chrome.exe"
    window.privacy.toggle.click()
    wait_for(app, lambda: "일시정지" in window.collection_status.text())
    assert window.application.text() == "—"
    wait_for(app, lambda: window.privacy.toggle.isEnabled())
    window.privacy.toggle.click()
    wait_for(app, lambda: window.application.text() == "chrome.exe")
    window.privacy.editor.setPlainText("chrome.exe")
    wait_for(app, lambda: window.privacy.apply_button.isEnabled())
    window.privacy.apply_button.click()
    wait_for(app, lambda: "수집 차단" in window.collection_status.text())
    assert window.application.text() == "—"


def test_recent_records_and_clipboard_read_real_storage(app, window, live_backend):
    """실제 수집→창 전환→저장→Qt 조회까지 원문과 작업 ID가 보존되는지 확인한다."""
    _, state, store = live_backend
    window.privacy.client.set_clipboard_enabled(True)
    wait_for(app, lambda: window.privacy.state is not None
             and window.privacy.state.settings.clipboard_enabled is True)
    wait_for(app, lambda: len(store.get_recent_clipboard_records()) == 1)
    state.process, state.tick = "word.exe", 2.0
    wait_for(app, lambda: window.application.text() == "word.exe")
    received = []
    window.recent.client.records_received.connect(received.append)
    window.tabs.setCurrentWidget(window.recent)
    wait_for(app, lambda: bool(received))
    assert received[0][0].process_name == "chrome.exe"
    assert received[0][0].active_duration_ms == 2000
    # 실제 저장 ID로 별도의 Qt 클라이언트에서도 같은 복사 내용을 조회한다.
    from client.clipboard_client import ClipboardClient

    client = ClipboardClient(live_backend[0], window)
    entries = []
    client.entries_received.connect(entries.append)
    client.fetch(received[0][0].id)
    wait_for(app, lambda: bool(entries))
    assert entries[0].entries[0].text == "가상 복사 원문"
    client.close()


def test_upload_docx_and_reload_real_document_list(app, window, tmp_path):
    """실제 Qt multipart→Backend 추출→DB 저장→목록/본문 표시를 확인한다."""
    path = tmp_path / "가상 문서.docx"
    document = Document()
    document.add_paragraph("가상 통합 검증 <b>일반 텍스트</b>")
    document.save(path)
    window.tabs.setCurrentWidget(window.documents)
    wait_for(app, lambda: window.documents.loaded and not window.documents.busy)
    window.documents.upload(str(path))
    wait_for(app, lambda: len(window.documents.rows) == 1)
    row = window.documents.rows[0]
    assert row.file_name == path.name
    assert row.file_type == "docx"
    assert "<b>일반 텍스트</b>" in window.documents.content.toPlainText()
    window.documents.refresh()
    wait_for(app, lambda: not window.documents.busy)
    assert len(window.documents.rows) == 1


def test_document_import_denied_while_paused(app, window, tmp_path):
    """전체 일시정지 정책이 문서 가져오기 경로에도 적용되는지 실제 HTTP로 확인한다."""
    path = tmp_path / "가상.docx"
    document = Document()
    document.add_paragraph("허용 전 저장하지 않는 가상 자료")
    document.save(path)
    window.privacy.client.set_paused(True)
    wait_for(app, lambda: window.privacy.state is not None and window.privacy.state.settings.paused)
    window.tabs.setCurrentWidget(window.documents)
    wait_for(app, lambda: window.documents.loaded and not window.documents.busy)
    window.documents.upload(str(path))
    wait_for(app, lambda: not window.documents.busy)
    assert "허용되지" in window.documents.notice.text()
    assert window.documents.rows == []
