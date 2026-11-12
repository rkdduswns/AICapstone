"""실제 DB의 작업 ID·출처·본문 연결과 잘못된 연결 거부를 검증한다."""

import sqlite3
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from client.document_content_client import read_record_document_content
from client.records_client import read_recent_records
from client.web_content_client import read_record_web_content

AUTH = {"Authorization": "Bearer example-test-token"}
DESKTOP = {"X-ContextTrace-Client": "desktop"}


@pytest.fixture
def runtime(tmp_path):
    """OS 응답만 가상화하고 실제 추적기·HTTP 처리·DB를 사용한다."""
    state = SimpleNamespace(tick=0, process="chrome.exe", title="가상 페이지")
    detector = SimpleNamespace(
        get_active_window_handle=lambda: 1, get_process_id=lambda handle: 123,
        get_process_name=lambda pid: state.process, normalize_app_name=lambda name: name,
        get_window_title=lambda handle: state.title,
    )
    store = ActivityStore(tmp_path / "activity.db")
    tracker = ActivityTracker(detector=detector, store=store, clock=lambda: state.tick,
        now=lambda: datetime(2026, 10, 22, tzinfo=timezone.utc) + timedelta(seconds=state.tick))
    app = create_app(activity_tracker=tracker, activity_store=store, collection_interval=None,
                     browser_token="example-test-token", clipboard_reader=lambda: None)
    return TestClient(app), state, store, tracker


def source(client, record_id, url="https://example.test/a", browser="chrome"):
    """작업 ID를 명시한 브라우저 출처를 실제 API에 전송한다."""
    return client.post("/browser/source", headers=AUTH,
        json={"browser": browser, "url": url, "page_title": "가상 페이지", "record_id": record_id})


def docx_bytes(text="가상 문서 본문"):
    """개인정보 없는 실제 DOCX 바이트를 만들어 추출까지 검증한다."""
    output = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    return output.getvalue()


def test_stable_record_id_updates_and_survives_restart(runtime):
    """수집 중 발급한 ID가 샘플 갱신·종료·DB 재조회 뒤에도 유지된다."""
    client, state, store, tracker = runtime
    first = client.get("/activity/current").json()["data"]
    assert first["record_id"] == "1"
    state.tick = 3
    assert client.get("/activity/current").json()["data"]["record_id"] == first["record_id"]
    assert len(store.get_recent_records()) == 1
    assert store.get_recent_records()[0].active_duration_ms == 3000
    tracker.finish()
    assert len(ActivityStore(store._db_path).get_recent_records()) == 1


@pytest.mark.parametrize("browser,process", [("chrome", "chrome.exe"), ("edge", "msedge.exe")])
def test_link_browser_and_read_through_actual_client_parsers(runtime, browser, process):
    """Chrome/Edge 출처와 본문을 저장하고 기존 Client 파서가 같은 작업으로 읽는지 확인한다."""
    client, state, store, _ = runtime
    state.process = process
    rid = client.get("/activity/current").json()["data"]["record_id"]
    response = source(client, rid, browser=browser)
    assert response.status_code == 200
    sid = response.json()["data"]["id"]
    assert client.post("/browser/content", headers=AUTH,
        json={"browser_source_id": sid, "content_text": "가상 <b>본문</b>"}).status_code == 200
    records = read_recent_records(client.get("/records/recent").content)
    assert records[0].id == rid
    assert records[0].browser.url == "https://example.test/a"
    body = read_record_web_content(client.get("/records/web-content", params={"record_id": rid}).content,
                                   rid, records[0].browser)
    assert body.content.text == "가상 <b>본문</b>"
    assert store.source_record_id("browser", sid) == int(rid)


def test_url_change_with_same_title_keeps_distinct_history(runtime):
    """제목이 같은 두 URL을 별도 작업으로 보존하고 옛 페이지 본문을 새 출처에 붙이지 않는다."""
    client, state, store, _ = runtime
    old_id = client.get("/activity/current").json()["data"]["record_id"]
    first = source(client, old_id).json()["data"]
    client.post("/browser/content", headers=AUTH,
                json={"browser_source_id": first["id"], "content_text": "첫 본문"})
    state.tick = 4
    second = source(client, old_id, "https://example.test/b").json()["data"]
    assert str(second["activity_record_id"]) != old_id
    assert len(store.get_recent_records()) == 2
    rows = read_recent_records(client.get("/records/recent").content)
    assert {r.browser.url for r in rows} == {"https://example.test/a", "https://example.test/b"}
    assert client.post("/browser/content", headers=AUTH,
        json={"browser_source_id": first["id"], "content_text": "늦은 잘못된 본문"}).status_code == 409
    assert store.get_browser_content_record(first["id"]).content_text == "첫 본문"


@pytest.mark.parametrize("change", ["process", "title", "pause", "wrong_id"])
def test_stale_or_wrong_browser_link_is_rejected(runtime, change):
    """현재 프로세스·창·작업·정책이 달라진 요청은 연결 테이블에 쓰지 않는다."""
    client, state, store, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]
    if change == "process":
        state.process = "word.exe"
    elif change == "title":
        state.title = "다른 창"
    elif change == "pause":
        client.put("/privacy/paused", json={"paused": True}, headers=DESKTOP)
    else:
        rid = "99999"
    assert source(client, rid).status_code in (403, 409)
    assert store.get_recent_browser_source_records() == []


def test_duplicate_capture_updates_body_without_duplicate_rows(runtime):
    """같은 페이지 재전송과 본문 갱신은 기존 출처/본문 행을 재사용한다."""
    client, _, store, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]
    sid = source(client, rid).json()["data"]["id"]
    assert source(client, rid).json()["data"]["id"] == sid
    for text in ("이전 본문", "바뀐 본문"):
        assert client.post("/browser/content", headers=AUTH,
            json={"browser_source_id": sid, "content_text": text}).status_code == 200
    assert len(store.get_recent_browser_source_records()) == 1
    assert store.get_browser_content_record(sid).content_text == "바뀐 본문"


def test_link_docx_keeps_exact_path_and_saved_body(runtime):
    """사용자가 명시한 작업과 Windows 경로를 저장하고 실제 Client 상세 계약으로 읽는다."""
    client, _, store, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]
    path = r"C:\가상 자료\연결 문서.docx"
    response = client.post("/documents", headers=DESKTOP,
        data={"record_id": rid, "file_path": path},
        files={"file": ("연결 문서.docx", docx_bytes(), "application/octet-stream")})
    assert response.status_code == 201
    rows = read_recent_records(client.get("/records/recent").content)
    assert rows[0].document.file_path == path
    result = read_record_document_content(
        client.get("/records/document-content", params={"record_id": rid}).content,
        rid, rows[0].document)
    assert result.content.text == "가상 문서 본문"
    assert store.source_record_id("document", response.json()["data"]["id"]) == int(rid)
    # 원본 파일을 다시 읽지 않고 재시작 후에도 같은 저장 내용으로 조회한다.
    restarted = TestClient(create_app(activity_store=ActivityStore(store._db_path),
                                      collection_interval=None))
    assert restarted.get("/records/document-content", params={"record_id": rid}).json() == (
        client.get("/records/document-content", params={"record_id": rid}).json())


@pytest.mark.parametrize("path", ["document.docx", r"C:relative\document.docx",
                                  r"\\?\C:\private\document.docx", r"C:\private\..\document.docx",
                                  r"C:\private\wrong.pdf", r"C:\private\other.docx"])
def test_invalid_document_source_is_not_stored(runtime, path):
    """상대·장치·상위 이동·유형 불일치·다른 이름의 경로를 출처로 저장하지 않는다."""
    client, _, store, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]
    response = client.post("/documents", headers=DESKTOP,
        data={"record_id": rid, "file_path": path},
        files={"file": ("document.docx", docx_bytes(), "application/octet-stream")})
    assert response.status_code == 422
    assert store.get_recent_document_records() == []


@pytest.mark.parametrize("headers", [{}, {**DESKTOP, "Origin": "https://example.test"}])
def test_document_link_requires_desktop_request(runtime, headers):
    """웹 Origin 또는 전용 헤더가 없는 요청은 문서를 기존 작업에 연결하지 못한다."""
    client, _, store, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]
    response = client.post("/documents", headers=headers,
        data={"record_id": rid, "file_path": r"C:\가상\document.docx"},
        files={"file": ("document.docx", docx_bytes(), "application/octet-stream")})
    assert response.status_code == 403
    assert store.get_recent_document_records() == []


def test_deleted_document_target_rolls_back_source(runtime, monkeypatch):
    """업로드 도중 대상 작업이 삭제되면 출처와 연결을 같은 트랜잭션에서 모두 취소한다."""
    client, _, store, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]

    def extract_after_delete(path):
        """추출 경계에서 대상 삭제를 재현해 존재 확인 이후의 경쟁 조건을 확인한다."""
        with sqlite3.connect(store._db_path) as connection:
            connection.execute("DELETE FROM activity_records WHERE id = ?", (rid,))
        return "고아 출처로 남으면 안 되는 가상 본문"

    monkeypatch.setattr("backend.app.extract_document_text", extract_after_delete)
    response = client.post("/documents", headers=DESKTOP,
        data={"record_id": rid, "file_path": r"C:\가상\document.docx"},
        files={"file": ("document.docx", docx_bytes(), "application/octet-stream")})
    assert response.status_code == 404
    assert store.get_recent_document_records() == []


def test_browser_wrong_token_never_links_source(runtime):
    """토큰 오류를 작업 연결 이전에 거부해 출처 행도 남기지 않는다."""
    client, _, store, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]
    response = client.post("/browser/source", headers={"Authorization": "Bearer wrong"},
        json={"record_id": rid, "browser": "chrome", "url": "https://example.test/a",
              "page_title": "가상 페이지"})
    assert response.status_code == 401
    assert store.get_recent_browser_source_records() == []


def test_unlinked_legacy_records_are_not_guessed(runtime):
    """기존 저장 자료와 작업이 같은 시간이어도 FK 없이 자동 연결하지 않는다."""
    client, _, store, _ = runtime
    rid = int(client.get("/activity/current").json()["data"]["record_id"])
    store.save_document_record("old.docx", "예전 본문", "2026-10-22T00:00:00+00:00")
    store.save_browser_source_record("chrome", "https://example.test/a", "가상 페이지",
                                     "2026-10-22T00:00:00+00:00")
    # 구형 DB와 같은 테이블 구성으로 되돌린 뒤 초기화가 원본 행을 보존하는지 확인한다.
    with sqlite3.connect(store._db_path) as connection:
        connection.execute("DROP TABLE record_browser_sources")
        connection.execute("DROP TABLE record_document_sources")
    reopened = ActivityStore(store._db_path)
    assert reopened.get_record_browser(rid) is None
    assert reopened.get_record_document(rid) is None
    assert len(reopened.get_recent_document_records()) == 1
    assert len(reopened.get_recent_browser_source_records()) == 1


@pytest.mark.parametrize("endpoint", ["web-content", "document-content"])
def test_empty_missing_and_large_body_states(runtime, endpoint):
    """저장 본문 없음과 작업 없음은 구분하고 긴 웹 본문은 일부 표시 상태로 전달한다."""
    client, _, _, _ = runtime
    rid = client.get("/activity/current").json()["data"]["record_id"]
    assert client.get(f"/records/{endpoint}?record_id={rid}").json()["data"]["content"] is None
    assert client.get(f"/records/{endpoint}?record_id=999999").status_code == 404
    if endpoint == "web-content":
        sid = source(client, rid).json()["data"]["id"]
        client.post("/browser/content", headers=AUTH,
                    json={"browser_source_id": sid, "content_text": "x" * 60000})
        content = client.get(f"/records/{endpoint}?record_id={rid}").json()["data"]["content"]
        assert content["truncated"] is True
        assert len(content["text"]) == 50000
