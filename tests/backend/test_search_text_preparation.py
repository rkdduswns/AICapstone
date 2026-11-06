"""실제로 연결해 저장한 본문을 검색용 파생 텍스트로 준비하는 경계를 검증한다."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from io import BytesIO
from pathlib import PureWindowsPath
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from backend.search_text import prepare_search_texts
from shared.activity import ActiveWindow
from shared.browser import BrowserPage
from shared.document import LocalDocument

AUTH = {"Authorization": "Bearer test-search-preparation-token"}
DESKTOP = {"X-ContextTrace-Client": "desktop"}
TIME = "2026-11-06T03:00:00+00:00"
DOCUMENT_PATH = r"C:\가상 자료\정규화.docx"
URL = "https://example.test/article"


@pytest.fixture
def capture_runtime(tmp_path):
    """활성 창 감지만 가상화하고 기존 API로 실제 작업 행을 만든다."""
    db_path = tmp_path / "activity.db"
    store = ActivityStore(db_path)
    detector = SimpleNamespace(
        get_active_window_handle=lambda: 1,
        get_process_id=lambda handle: 42,
        get_process_name=lambda pid: "chrome.exe",
        normalize_app_name=lambda name: "Google Chrome",
        get_window_title=lambda handle: "가상 작업",
    )
    app = create_app(
        activity_tracker=ActivityTracker(detector=detector, store=store),
        activity_store=store, browser_token="test-search-preparation-token",
        collection_interval=None, clipboard_reader=lambda: None,
    )
    with TestClient(app) as client:
        response = client.get("/activity/current")
        assert response.status_code == 200
        yield db_path, store, client, int(response.json()["data"]["record_id"])


def capture_source(client, record_id, title="가상 웹페이지"):
    """현재 작업과 브라우저 출처를 기존 수신 API로 연결한다."""
    response = client.post(
        "/browser/source", headers=AUTH,
        json={"browser": "chrome", "url": URL, "page_title": title, "record_id": record_id},
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def capture_body(client, source_id, text):
    """본문 수신 응답에서 실제 저장 ID와 확보 시각을 받는다."""
    response = client.post(
        "/browser/content", headers=AUTH,
        json={"browser_source_id": source_id, "content_text": text},
    )
    assert response.status_code == 200
    return response.json()["data"]


def upload_document(client, record_id, text):
    """실제 DOCX 바이트를 업로드해 추출과 작업 연결을 함께 거친다."""
    document = Document()
    document.add_paragraph(text)
    file = BytesIO()
    document.save(file)
    response = client.post(
        "/documents", headers=DESKTOP,
        data={"record_id": record_id, "file_path": DOCUMENT_PATH},
        files={"file": (PureWindowsPath(DOCUMENT_PATH).name, file.getvalue())},
    )
    assert response.status_code == 201
    return response.json()["data"]


def save_work(store):
    """수집기를 띄울 필요가 없는 구형 DB·오류 검증용 작업을 저장한다."""
    return store.save_record(
        ActiveWindow("Google Chrome", "chrome.exe", 42, "가상 웹페이지"), TIME, TIME, 0,
    )


def run_cli(db_path, record_id):
    """실제 로컬 진입점을 실행해 Windows에서도 UTF-8 출력 바이트를 확인한다."""
    return subprocess.run(
        [sys.executable, "-m", "backend.search_text", "--db-path", str(db_path),
         "--record-id", str(record_id)],
        capture_output=True, timeout=10,
    )


def test_prepares_received_web_and_uploaded_docx_without_changing_saved_body(capture_runtime):
    """API로 저장한 원문 전체를 가공하고 양쪽 출처와 확보 시각을 보존한다."""
    db_path, store, client, record_id = capture_runtime
    source_id = capture_source(client, record_id)
    long_text = "가" * 50000
    raw_web = f"Cafe\u0301\r\n{long_text}\r\n본문 끝"
    browser_body = capture_body(client, source_id, raw_web)
    raw_document = "문서 Cafe\u0301\n둘째 줄"
    document = upload_document(client, record_id, raw_document)

    assert store.get_browser_content_record(source_id).content_text == raw_web
    assert store.get_record_document(record_id).extracted_text == raw_document
    rows = prepare_search_texts(db_path, record_id)

    assert len(rows) == 2
    assert {row.context_id for row in rows} == {str(record_id)}
    sources = {row.kind: row for row in rows}
    web, doc = sources["web"], sources["document"]
    assert web.source_id == str(source_id)
    assert web.browser == BrowserPage("chrome", "가상 웹페이지", URL)
    assert web.captured_at == browser_body["captured_at"]
    assert web.text == f"Café\n{long_text}\n본문 끝"
    assert doc.source_id == str(document["id"])
    assert doc.document == LocalDocument(DOCUMENT_PATH, "docx")
    assert doc.captured_at == document["captured_at"]
    assert doc.text == "문서 Café\n둘째 줄"
    assert store.get_browser_content_record(source_id).content_text == raw_web
    assert store.get_record_document(record_id).extracted_text == raw_document


def test_keeps_all_linked_sources_and_reads_only_latest_body_per_web_source(capture_runtime):
    """최신 출처 하나에 제한하지 않고 빈 웹 출처와 교체된 본문을 건너뛴다."""
    db_path, store, client, record_id = capture_runtime
    capture_source(client, record_id, "본문 없는 출처")
    first = capture_source(client, record_id)
    original = capture_body(client, first, "갱신 이전 본문")
    refreshed = capture_body(client, first, "갱신 이후 본문")
    assert original["id"] == refreshed["id"]
    second = capture_source(client, record_id, "동일 URL의 다른 출처")
    capture_body(client, second, "두 번째 웹 본문")
    first_doc = store.save_document_record(DOCUMENT_PATH, "첫 문서", TIME, record_id)
    second_doc = store.save_document_record(DOCUMENT_PATH, "둘째 문서", TIME, record_id)

    rows = prepare_search_texts(db_path, record_id)

    assert len(rows) == 4
    assert {(row.kind, row.source_id): row.text for row in rows} == {
        ("web", str(first)): "갱신 이후 본문",
        ("web", str(second)): "두 번째 웹 본문",
        ("document", str(first_doc)): "첫 문서",
        ("document", str(second_doc)): "둘째 문서",
    }
    assert next(row for row in rows if row.kind == "web" and row.source_id == str(first)).captured_at == (
        refreshed["captured_at"]
    )


def test_excludes_sensitive_text_and_invalid_source_metadata(tmp_path):
    """기존 연결 자료도 민감 정책을 적용하고 빈 본문과 시간대 없는 출처를 제외한다."""
    db_path = tmp_path / "sensitive.db"
    store = ActivityStore(db_path)
    record_id = save_work(store)
    allowed = store.save_document_record(DOCUMENT_PATH, "안전한 문서", TIME, record_id)
    store.save_document_record(DOCUMENT_PATH, "password=raw-secret", TIME, record_id)
    store.save_document_record(DOCUMENT_PATH, "pass\x00word=joined-secret", TIME, record_id)
    store.save_document_record(DOCUMENT_PATH, "\x00", TIME, record_id)
    store.save_document_record(
        r"C:\가상 자료\example@example.test.docx", "민감 경로를 가진 문서", TIME, record_id,
    )
    store.save_document_record(
        DOCUMENT_PATH, "시간대 없는 확보 시각", "2026-11-06T03:00:00", record_id,
    )

    rows = prepare_search_texts(db_path, record_id)

    assert [(row.source_id, row.text) for row in rows] == [(str(allowed), "안전한 문서")]


def test_preparation_uses_current_saved_pause_and_block_list(capture_runtime):
    """설정 변경이 같은 DB의 이후 준비 결과에 반영되며 저장 원문은 남는다."""
    db_path, store, client, record_id = capture_runtime
    store.save_document_record(DOCUMENT_PATH, "이미 저장된 본문", TIME, record_id)
    assert len(prepare_search_texts(db_path, record_id)) == 1

    assert client.put(
        "/privacy/blocked-processes", headers=DESKTOP, json={"blocked_processes": ["chrome.exe"]},
    ).status_code == 200
    assert prepare_search_texts(db_path, record_id) == []
    assert client.put(
        "/privacy/blocked-processes", headers=DESKTOP, json={"blocked_processes": []},
    ).status_code == 200
    assert client.put(
        "/privacy/paused", headers=DESKTOP, json={"paused": True},
    ).status_code == 200
    assert prepare_search_texts(db_path, record_id) == []
    assert client.put(
        "/privacy/paused", headers=DESKTOP, json={"paused": False},
    ).status_code == 200
    assert [row.text for row in prepare_search_texts(db_path, record_id)] == ["이미 저장된 본문"]
    assert store.get_record_document(record_id).extracted_text == "이미 저장된 본문"


def test_old_database_defaults_to_allowed_and_never_guesses_missing_links(tmp_path):
    """설정 테이블이 없는 DB도 실제 연결만 읽으며 파일에 쓰지 않는다."""
    db_path = tmp_path / "legacy.db"
    store = ActivityStore(db_path)
    record_id = save_work(store)
    linked = store.save_document_record(DOCUMENT_PATH, "명시적으로 연결됨", TIME, record_id)
    unlinked = store.save_browser_source_record("chrome", URL, "가상 웹페이지", TIME)
    store.save_browser_content_record(unlinked, "작업과 제목·시각은 같지만 연결 없음", TIME)
    store.save_document_record(DOCUMENT_PATH, "같은 경로지만 연결 없음", TIME)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("DROP TABLE privacy_settings")
        connection.commit()
    before = db_path.read_bytes()

    rows = prepare_search_texts(db_path, record_id)

    assert [(row.kind, row.source_id, row.text) for row in rows] == [
        ("document", str(linked), "명시적으로 연결됨"),
    ]
    assert db_path.read_bytes() == before


def test_deleted_work_is_missing_even_if_its_raw_document_remains(tmp_path):
    """작업이 삭제된 후 원문만 남아도 다음 준비 결과에는 포함하지 않는다."""
    db_path = tmp_path / "deleted.db"
    store = ActivityStore(db_path)
    record_id = save_work(store)
    store.save_document_record(DOCUMENT_PATH, "삭제 전 연결 본문", TIME, record_id)
    assert len(prepare_search_texts(db_path, record_id)) == 1

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM activity_records WHERE id = ?", (record_id,))
        connection.commit()

    assert store.get_recent_document_records()[0].extracted_text == "삭제 전 연결 본문"
    assert prepare_search_texts(db_path, record_id) is None


def test_cli_outputs_utf8_json_for_requested_record(tmp_path):
    """한글과 특수문자가 있는 경로에서 실제 CLI가 준비 결과를 UTF-8 JSON으로 출력한다."""
    db_path = tmp_path / "검색 이력 #1.db"
    store = ActivityStore(db_path)
    record_id = save_work(store)
    source_id = store.save_document_record(DOCUMENT_PATH, "한글 Cafe\u0301", TIME, record_id)

    result = run_cli(db_path, record_id)

    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout.decode("utf-8"))
    assert len(rows) == 1
    assert rows[0]["context_id"] == str(record_id)
    assert rows[0]["source_id"] == str(source_id)
    assert rows[0]["text"] == "한글 Café"
    assert rows[0]["document"]["file_path"] == DOCUMENT_PATH


def test_cli_errors_do_not_print_raw_details_or_create_missing_database(tmp_path):
    """누락 작업·손상 설정·없는 DB는 원문 없이 실패하고 새 파일을 만들지 않는다."""
    db_path = tmp_path / "invalid-settings.db"
    store = ActivityStore(db_path)
    record_id = save_work(store)
    store.save_document_record(DOCUMENT_PATH, "private-source-body", TIME, record_id)
    missing_record = run_cli(db_path, record_id + 1)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "INSERT INTO privacy_settings(singleton, payload) VALUES (1, ?)",
            ('{"paused":"private-settings-value","blocked_processes":[],"clipboard_enabled":false}',),
        )
        connection.commit()
    corrupted = run_cli(db_path, record_id)
    missing_path = tmp_path / "missing.db"
    missing_database = run_cli(missing_path, record_id)

    for result in (missing_record, corrupted, missing_database):
        assert result.returncode == 1
        assert not result.stdout
        assert result.stderr
        assert b"private-settings-value" not in result.stderr
        assert b"private-source-body" not in result.stderr
        assert b"Traceback" not in result.stderr
    assert not missing_path.exists()
