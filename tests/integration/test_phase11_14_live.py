"""실제 Qt→Uvicorn→SQLite→검색/RAG→로컬 모델 HTTP 경계를 연결해 검증한다."""

import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from docx import Document
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from backend.ollama_answer_generator import OllamaAnswerGenerator
from client.application_window import ApplicationWindow
from shared.activity import ActiveWindow


def wait_for(app, predicate, timeout=8):
    """Qt 이벤트와 실제 네트워크 콜백을 처리하면서 최종 상태를 기다린다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "실제 API 응답 대기 시간 초과"
        time.sleep(0.005)
    app.processEvents()


class TestEmbeddings:
    """모델 추론 출력만 주입한다. 청크·벡터 저장·필터·유사도·근거 선택은 실제 구현이다."""

    __test__ = False
    model_name = "intfloat/multilingual-e5-small"

    def split_passage(self, text, privacy_policy=None):
        return [text]

    def embed_passages(self, texts, privacy_policy=None):
        return [[1.0] + [0.0]*383 for _ in texts]

    def embed_query(self, query, privacy_policy=None):
        return ([0.0, 1.0]+[0.0]*382) if "없는 주제" in query else [1.0]+[0.0]*383


@pytest.fixture
def runtime(tmp_path):
    """OS 감지와 모델의 추론 출력만 가상화하고 나머지 서버 경계를 실제 실행한다."""
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = SimpleNamespace(fail=False, requests=[], entered=threading.Event(), release=threading.Event())
    state.release.set()

    class ModelHandler(BaseHTTPRequestHandler):
        """Ollama 전송 형식을 실제 로컬 HTTP로 받고 테스트용 추론 결과만 응답한다."""

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append(body)
            state.entered.set()
            state.release.wait(timeout=8)
            if state.fail:
                self.send_error(503)
                return
            prompt = json.loads(body["messages"][1]["content"])
            identifier = prompt["evidence"][0]["id"]
            result = {"message": {"content": json.dumps({
                "answer": "[1]에 따르면 저장된 자료에서 검색과 출처를 확인할 수 있습니다.",
                "evidence_ids": [identifier],
            }, ensure_ascii=False)}}
            content = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_args):
            """프롬프트 원문을 테스트 실행 로그에 남기지 않는다."""

    model_server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    model_thread = threading.Thread(target=model_server.serve_forever, daemon=True)
    model_thread.start()
    store = ActivityStore(tmp_path / "live.db")
    record_id = store.save_record(ActiveWindow("Word", "winword.exe", 10, "검색 통합 문서"),
                                 "2026-11-20T09:00:00+00:00", "2026-11-20T09:10:00+00:00", 600000)
    tracker = ActivityTracker(store=store, detector=SimpleNamespace(get_active_window_handle=lambda: None))
    backend = create_app(activity_store=store, activity_tracker=tracker, collection_interval=None,
                         document_storage_dir=tmp_path / "copies", embedding_service=TestEmbeddings(), browser_token="live-token",
                         answer_generator=OllamaAnswerGenerator(
                             base_url=f"http://127.0.0.1:{model_server.server_port}"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(backend, log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic()+5
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.01)
        window = ApplicationWindow(port)
        window.show()
        window.management.check()
        wait_for(app, lambda: window.management.documents.connected)
        try:
            yield app, window, store, record_id, port, state
        finally:
            state.release.set()
            window.close()
            app.processEvents()
            server.should_exit = True
            thread.join(timeout=10)
            model_server.shutdown()
            model_server.server_close()
            model_thread.join(timeout=5)
            assert not thread.is_alive()


def upload(app, window, record_id, tmp_path):
    """선택 작업과 Windows 경로는 UI로 전달하고 실제 DOCX 바이트를 업로드한다."""
    documents = window.management.documents
    window.show_management(window.management.tabs.indexOf(window.management.recent))
    wait_for(app, lambda: bool(window.management.recent.records))
    index = next(i for i, row in enumerate(window.management.recent.records) if row.id == str(record_id))
    window.management.recent.table.selectRow(index)
    window.management.recent.attach_button.click()
    wait_for(app, lambda: documents.loaded and not documents.busy)
    file = tmp_path / "통합 자료.docx"
    doc = Document()
    doc.add_paragraph("가상 검색 통합 자료입니다. 검색과 근거 출처를 확인합니다.")
    doc.save(file)
    source_path = str(file.resolve()) if sys.platform == "win32" else r"C:\검증 자료\통합 자료.docx"
    documents.upload(str(file), source_path=source_path)
    wait_for(app, lambda: bool(documents.rows) and not documents.busy)
    assert documents.rows[0].record_id == str(record_id)
    window.show_search()
    return source_path


def test_real_upload_condition_semantic_rag_and_provenance(runtime, tmp_path):
    """업로드→조건 검색→의미 검색→Ollama HTTP→답변/원본 시각을 같은 실제 ID로 확인한다."""
    app, window, store, record_id, _, state = runtime
    source_path = upload(app, window, record_id, tmp_path)
    search = window.management.search
    window.show_management(window.management.tabs.indexOf(search))
    search.keyword.setText("검색 통합")
    search.button.click()
    wait_for(app, lambda: bool(search.records))
    assert search.records[0].id == str(record_id)
    semantic = window.management.semantic
    window.show_management(window.management.tabs.indexOf(semantic))
    semantic.query.setText("출처 확인 방법")
    semantic.button.click()
    wait_for(app, lambda: bool(semantic._chunks))
    assert semantic._chunks[0].context_id == str(record_id)
    window.show_search()
    window.search.query.setText("저장한 자료를 설명해줘")
    window.search.submit()
    wait_for(app, lambda: window.search._result is not None)
    result = window.search._result
    assert result.status == "answer"
    assert result.full_answer.startswith("[1]")
    evidence = result.evidence[0]
    assert evidence.context_id == str(record_id)
    assert evidence.source.document.file_path == source_path
    if sys.platform == "win32":
        assert Path(source_path).is_file()
    assert evidence.source.started_at == "2026-11-20T09:00:00+00:00"
    assert evidence.source.last_active_at != evidence.source.captured_at
    assert state.requests[0]["stream"] is False
    assert store.get_search_chunk_text(evidence.id) in evidence.text


def test_no_evidence_and_model_failure_are_not_example_answers(runtime, tmp_path):
    """빈 검색과 모델 503을 구분하며 가상 성공 답변을 대신 표시하지 않는다."""
    app, window, _, record_id, _, state = runtime
    upload(app, window, record_id, tmp_path)
    window.search.query.setText("없는 주제 찾아줘")
    window.search.submit()
    wait_for(app, lambda: window.search._result is not None)
    assert window.search._result.status == "insufficient"
    assert window.search._result.evidence == ()
    assert state.requests == []
    state.fail = True
    window.search.query.setText("근거가 있는 질문")
    window.search.submit()
    wait_for(app, lambda: window.search._result is not None)
    assert window.search._result.status == "error"
    assert "Ollama" in window.search.status.text()
    assert window.search.detail_text.toPlainText() == ""


def test_cancelled_model_request_does_not_block_status_or_replace_new_query(runtime, tmp_path):
    """모델 응답을 기다릴 때 상태 API가 응답하고 취소한 결과는 새 입력에 나타나지 않는다."""
    app, window, _, record_id, port, state = runtime
    upload(app, window, record_id, tmp_path)
    state.release.clear()
    window.search.query.setText("오래 기다리는 질문")
    window.search.submit()
    wait_for(app, state.entered.is_set)
    with httpx.Client(trust_env=False, timeout=1) as client:
        assert client.get(f"http://127.0.0.1:{port}/privacy").status_code == 200
    window.search.query.setText("새 질문")
    assert window.rag.reply is None
    state.release.set()
    wait_for(app, lambda: window.search._pending_id is None)
    assert window.search._result is None
    assert window.search.detail_text.toPlainText() == ""


def test_sessions_display_actual_materials_and_confirm_before_delete(runtime, tmp_path, monkeypatch):
    """세션 조회·취소·실제 삭제 후 검색 색인/목록 정리를 UI에서 확인한다."""
    app, window, store, record_id, _, _ = runtime
    upload(app, window, record_id, tmp_path)
    sessions = window.management.sessions
    window.show_management(window.management.tabs.indexOf(sessions))
    wait_for(app, lambda: sessions.activities.count() == 1)
    assert "통합 자료.docx" in sessions.materials.toPlainText()
    sessions.activities.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    sessions.delete_selected()
    assert store.get_record(record_id) is not None
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    sessions.delete_selected()
    wait_for(app, lambda: store.get_record(record_id) is None and sessions.sessions.count() == 0)
    assert store.get_recent_document_records() == []
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM search_chunks").fetchone()[0] == 0


def test_canonical_upload_separates_backend_copy_and_original(runtime, tmp_path):
    """표준 context_id 폼과 확장 원본 경로를 함께 전송해 실제 저장·삭제 경계를 확인한다."""
    app, window, store, record_id, port, _ = runtime
    original = upload(app, window, record_id, tmp_path)
    row = httpx.get(f"http://127.0.0.1:{port}/documents", trust_env=False).json()["data"]["documents"][0]
    assert row["context_id"] == record_id and row["original_file_path"] == original
    copy = Path(row["file_path"])
    assert copy.is_file() and str(copy) != original
    assert httpx.delete(f"http://127.0.0.1:{port}/records/{record_id}", trust_env=False).is_success
    assert not copy.exists() and (tmp_path / "통합 자료.docx").is_file()
