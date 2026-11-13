"""기존 문서 요청 계약과 명시적 작업·원본 경로 연결을 Client HTTP 경계에서 검증한다."""

import json
import threading
import time
from copy import deepcopy
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtWidgets import QApplication

import client.documents_client as documents_module
from client.documents_client import DocumentsClient

SOURCE_PATH = r"C:\가상 자료\source.docx"
GOOD_ROW = {
    "id": 13,
    "file_name": "source.docx",
    "file_type": ".docx",
    "captured_at": "2026-11-13T04:00:00+00:00",
    "extracted_text": "저장된 가상 본문",
    "activity_record_id": 7,
    "file_path": SOURCE_PATH,
}


@pytest.fixture(scope="module")
def app():
    """다른 Client 검증과 같은 Qt 앱을 유지하며 비동기 HTTP 응답을 처리한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=5):
    """Qt 이벤트를 처리하면서 결과를 기다리고 실패를 시간 제한 안에 보고한다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("문서 Client 응답 시간 초과")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def document_file(tmp_path):
    """전송 바이트만 확인하므로 문서 추출기 없이 고정된 가상 파일을 준비한다."""
    path = tmp_path / "source.docx"
    path.write_bytes(b"synthetic-document-bytes")
    return path


@pytest.fixture
def fake_server():
    """실제 loopback 요청을 받아 multipart 계약과 Client의 응답 판정을 분리한다."""
    settings = {"status": 201, "row": deepcopy(GOOD_ROW), "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            """파일·필드·헤더를 보존하고 시험에서 지정한 성공 또는 오류를 반환한다."""
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            mime = BytesParser(policy=policy.default).parsebytes(
                f'Content-Type: {self.headers["Content-Type"]}\r\n'
                "MIME-Version: 1.0\r\n\r\n".encode() + raw
            )
            fields = {}
            for part in mime.iter_parts():
                key = part.get_param("name", header="content-disposition")
                fields.setdefault(key, []).append(part.get_payload(decode=True))
            settings["requests"].append({
                "path": self.path,
                "fields": fields,
                "desktop_header": self.headers.get("X-ContextTrace-Client"),
            })
            payload = json.dumps({"ok": True, "error": None, "data": settings["row"]}).encode()
            self.send_response(settings["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            """검증 데이터도 요청 로그에 남기지 않는다."""
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, settings
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def client(app, fake_server):
    """업로드 성공·표시 실패·HTTP 실패를 함께 관찰하고 종료 시 요청을 취소한다."""
    instance = DocumentsClient(fake_server[0])
    uploaded, failures, http_failures = [], [], []
    instance.document_uploaded.connect(uploaded.append)
    instance.documents_failed.connect(failures.append)
    instance.failed.connect(lambda reason, status: http_failures.append((reason, status)))
    try:
        yield instance, uploaded, failures, http_failures
    finally:
        instance.close()
        instance.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("record_id,status", [("1", 200), (str(2**63 - 1), 201)])
def test_existing_multipart_contract_preserves_explicit_source(
    app, client, fake_server, document_file, record_id, status,
):
    """기존 서버에 같은 작업 ID·원본 경로를 한 번 보내고 새 추정 필드를 추가하지 않는다."""
    instance, uploaded, failures, _ = client
    state = fake_server[1]
    state["status"] = status
    state["row"]["activity_record_id"] = int(record_id)
    instance.upload(str(document_file), record_id, SOURCE_PATH)
    wait_for(app, lambda: bool(uploaded or failures))
    assert failures == [] and len(uploaded) == 1
    assert uploaded[0].record_id == record_id and uploaded[0].file_path == SOURCE_PATH
    assert len(state["requests"]) == 1
    request = state["requests"][0]
    assert request["path"] == "/documents" and request["desktop_header"] == "desktop"
    assert request["fields"] == {
        "file": [document_file.read_bytes()],
        "record_id": [record_id.encode()],
        "file_path": [SOURCE_PATH.encode()],
    }


@pytest.mark.parametrize("record_id", [
    True, False, 1, 1.0, "", "0", "01", "-1", "+1", " 1", "1.0", "１", str(2**63),
])
def test_invalid_record_id_is_rejected_before_file_or_post(
    app, document_file, monkeypatch, record_id,
):
    """잘못된 연결 ID를 서버 저장 후 발견하지 않고 파일 읽기·전송 전에 거부한다."""
    instance = DocumentsClient(9)
    failures, opened, posted = [], [], []
    instance.documents_failed.connect(failures.append)

    def unexpected_file(*args):
        """잘못된 ID 요청은 파일 객체 생성에도 도달하지 않아야 한다."""
        opened.append(args)
        raise AssertionError("검증 전에 파일을 열었습니다.")

    def unexpected_post(*args):
        """입력 오류를 서버가 보정해 줄 것으로 기대하며 업로드하지 않는다."""
        posted.append(args)
        raise AssertionError("검증 전에 파일을 전송했습니다.")

    monkeypatch.setattr(documents_module, "QFile", unexpected_file)
    monkeypatch.setattr(instance.manager, "post", unexpected_post)
    try:
        instance.upload(str(document_file), record_id, SOURCE_PATH)
        assert len(failures) == 1 and opened == posted == []
        assert instance.reply is None
    finally:
        instance.close()
        instance.deleteLater()
        app.processEvents()


def test_wrong_original_file_name_is_rejected_before_reading(
    app, document_file, monkeypatch,
):
    """전송 파일과 다른 이름의 원본 출처를 조합하지 않는다."""
    instance = DocumentsClient(9)
    failures, opened = [], []
    instance.documents_failed.connect(failures.append)

    def unexpected_file(*args):
        """출처 이름 불일치는 실제 파일을 읽기 전에 거부해야 한다."""
        opened.append(args)
        raise AssertionError("출처 확인 전에 파일을 열었습니다.")

    monkeypatch.setattr(documents_module, "QFile", unexpected_file)
    try:
        instance.upload(str(document_file), "7", r"C:\가상 자료\other.docx")
        assert len(failures) == 1 and opened == [] and instance.reply is None
    finally:
        instance.close()
        instance.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("field,value", [
    ("file_path", r"C:\server\uuid.docx"),
    ("file_path", None),
    ("activity_record_id", 8),
    ("activity_record_id", None),
    ("file_name", "other.docx"),
])
def test_upload_response_cannot_replace_requested_identity(
    app, client, fake_server, document_file, field, value,
):
    """200이어도 다른 작업·이름·서버 사본을 요청한 원본의 연결 성공으로 표시하지 않는다."""
    instance, uploaded, failures, _ = client
    fake_server[1]["row"][field] = value
    instance.upload(str(document_file), "7", SOURCE_PATH)
    wait_for(app, lambda: bool(uploaded or failures))
    assert uploaded == [] and len(failures) == 1
    assert "호환되지" in failures[0] or "연결" in failures[0]
    assert len(fake_server[1]["requests"]) == 1


def test_http_403_wins_over_success_shaped_body_and_is_not_retried(
    app, client, fake_server, document_file,
):
    """거부 응답의 본문이 성공 모양이어도 저장 완료 신호나 자동 재전송을 만들지 않는다."""
    instance, uploaded, failures, http_failures = client
    fake_server[1]["status"] = 403
    instance.upload(str(document_file), "7", SOURCE_PATH)
    wait_for(app, lambda: bool(failures))
    deadline = time.monotonic() + 0.1
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert uploaded == [] and len(failures) == 1
    assert http_failures == [("http", 403)]
    assert "거부" in failures[0] and len(fake_server[1]["requests"]) == 1


def test_legacy_unlinked_upload_remains_available(app, client, fake_server, document_file):
    """연결 대상이 없으면 파일만 전송하고 응답에 없는 작업·경로를 만들어내지 않는다."""
    instance, uploaded, failures, _ = client
    del fake_server[1]["row"]["activity_record_id"]
    del fake_server[1]["row"]["file_path"]
    instance.upload(str(document_file))
    wait_for(app, lambda: bool(uploaded or failures))
    assert failures == [] and len(uploaded) == 1
    assert uploaded[0].record_id is None and uploaded[0].file_path is None
    assert len(fake_server[1]["requests"]) == 1
    assert fake_server[1]["requests"][0]["fields"] == {"file": [document_file.read_bytes()]}


@pytest.mark.parametrize("field,value", [("file_name", "other.docx"), ("file_type", ".pdf")])
def test_unlinked_upload_still_requires_selected_document_identity(
    app, client, fake_server, document_file, field, value,
):
    """작업 연결이 없어도 선택한 문서의 이름·유형과 다른 응답을 성공으로 표시하지 않는다."""
    instance, uploaded, failures, _ = client
    del fake_server[1]["row"]["activity_record_id"]
    del fake_server[1]["row"]["file_path"]
    fake_server[1]["row"][field] = value
    instance.upload(str(document_file))
    wait_for(app, lambda: bool(uploaded or failures))
    assert uploaded == [] and len(failures) == 1
    assert len(fake_server[1]["requests"]) == 1
