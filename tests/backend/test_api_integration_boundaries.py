"""통합 과정의 구형 DB 보존·출처 ID·잘림·지연 색인·삭제 경계를 확인한다."""

import sqlite3
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from backend.embedding import EmbeddingService
from backend.privacy_settings import StoredPrivacySettings
from shared.activity import ActiveWindow
from shared.rag import RAGAnswer

TIME = "2026-11-20T09:00:00+00:00"
AUTH = {"Authorization": "Bearer boundary-token"}


def work(store):
    """가상 자료를 실제 작업 테이블에 저장하고 발급된 ID를 사용한다."""
    return store.save_record(ActiveWindow("Chrome", "chrome.exe", 1, "가상 창"), TIME, TIME, 0)


def docx_bytes():
    """모델이나 개인정보 없이 실제 추출을 실행할 DOCX 바이트를 만든다."""
    output = BytesIO()
    doc = Document()
    doc.add_paragraph("검색 색인 경계를 확인하는 가상 문서입니다.")
    doc.save(output)
    return output.getvalue()


def test_old_database_links_raw_paths_and_privacy_are_preserved(tmp_path):
    """이전 main 형식의 실제 연결만 옮기고 원문·ID·시각·설정을 보존한다."""
    path = tmp_path / "old.db"
    source_path = r"C:\가상 자료\이전 문서.docx"
    settings = StoredPrivacySettings(paused=True, clipboard_enabled=False, blocked_processes=["private.exe"])
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE activity_records(id INTEGER PRIMARY KEY,application TEXT,process_name TEXT,
                process_id INTEGER,window_title TEXT,started_at TEXT,ended_at TEXT,active_duration_ms INTEGER);
            CREATE TABLE document_records(id INTEGER PRIMARY KEY,file_path TEXT,file_name TEXT,
                file_type TEXT,extracted_text TEXT,captured_at TEXT);
            CREATE TABLE record_document_sources(record_id INTEGER,source_id INTEGER UNIQUE,
                PRIMARY KEY(record_id,source_id));
            CREATE TABLE privacy_settings(singleton INTEGER PRIMARY KEY,payload TEXT);
        """)
        db.execute("INSERT INTO activity_records VALUES (7,'Word','winword.exe',1,'이전 창',?,?,100)", (TIME, TIME))
        db.execute("INSERT INTO document_records VALUES (9,?,'이전 문서.docx','.docx','보존한 원문',?)",
                   (source_path, TIME))
        db.execute("INSERT INTO record_document_sources VALUES (7,9)")
        db.execute("INSERT INTO privacy_settings VALUES (1,?)", (settings.model_dump_json(),))
    store = ActivityStore(path)
    assert store.get_record_document(7).file_path == source_path
    assert store.get_record_document(7).context_id == 7
    assert store.get_record_document(7).captured_at == TIME
    assert store.load_privacy_settings() == settings
    with store._connect() as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    client = TestClient(create_app(activity_store=store, collection_interval=None))
    body = client.get("/records/document-content?record_id=7").json()["data"]["content"]
    assert body["text"] == "보존한 원문" and body["document"]["file_path"] == source_path
    assert client.get("/activity/current").json()["data"]["collection_status"] == "paused"
    assert len(ActivityStore(path).get_recent_records()) == 1


def test_legacy_search_table_is_archived_without_losing_rows(tmp_path):
    """실험용 v1 검색 표를 새 검색 스키마와 섞거나 삭제하지 않는다."""
    path = tmp_path / "legacy-index.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE search_chunks(id TEXT PRIMARY KEY,record_id INTEGER,text TEXT)")
        db.execute("INSERT INTO search_chunks VALUES ('preserved',7,'이전 조각')")
    store = ActivityStore(path)
    with store._connect() as db:
        assert tuple(db.execute("SELECT * FROM legacy_search_chunks_v1").fetchone()) == ("preserved", 7, "이전 조각")
        assert "search_source_id" in {row["name"] for row in db.execute("PRAGMA table_info(search_chunks)")}
    ActivityStore(path)


@pytest.mark.parametrize("value", [True, 1.5, "1.0", "01"])
def test_browser_context_rejects_coerced_identifiers(tmp_path, value):
    """새 context_id 입력을 실제 작업과 다른 값으로 강제 변환하지 않는다."""
    store = ActivityStore(tmp_path / "ids.db")
    client = TestClient(create_app(activity_store=store, collection_interval=None, browser_token="boundary-token"))
    response = client.post("/browser/source", headers=AUTH, json={
        "browser": "chrome", "page_title": "가상", "url": "https://example.test/", "context_id": value,
    })
    assert response.status_code == 422
    assert store.get_recent_browser_source_records() == []


def test_browser_capture_preserves_truncation_in_history_and_search(tmp_path):
    """표시 제한보다 짧은 본문도 수집 단계에서 잘렸으면 실제 색인/조회에 표시한다."""
    store = ActivityStore(tmp_path / "body.db")
    detector = SimpleNamespace(get_active_window_handle=lambda: 1, get_process_id=lambda _h: 1,
                               get_process_name=lambda _pid: "chrome.exe", normalize_app_name=lambda n: n,
                               get_window_title=lambda _h: "가상 창")
    tracker = ActivityTracker(store=store, detector=detector)
    client = TestClient(create_app(activity_store=store, activity_tracker=tracker,
                                   collection_interval=None, browser_token="boundary-token"))
    rid = client.get("/activity/current").json()["data"]["record_id"]
    result = client.post("/browser/source", headers=AUTH, json={
        "browser": "chrome", "page_title": "가상", "url": "https://example.test/", "context_id": rid,
    })
    assert result.status_code == 200
    sid = result.json()["data"]["id"]
    assert result.json()["data"]["activity_record_id"] == rid
    assert client.post("/browser/content", headers=AUTH,
                       json={"browser_source_id": sid, "content_text": "일부만 수집한 본문", "truncated": True}).status_code == 200
    content = client.get(f"/records/web-content?record_id={rid}").json()["data"]["content"]
    assert content["truncated"] is True
    with store._connect() as db:
        assert db.execute("SELECT content_truncated FROM search_sources").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM semantic_embeddings").fetchone()[0] == 0


def test_collection_defers_real_model_and_query_indexes_saved_bytes(tmp_path, monkeypatch):
    """일반 수집은 모델을 실행하지 않고 검색 요청 때만 실제 색인 파이프라인을 실행한다."""
    store = ActivityStore(tmp_path / "pending.db")
    rid = work(store)
    model = EmbeddingService()
    calls = []
    monkeypatch.setattr(model, "split_passage", lambda text, **kwargs: calls.append("split") or [text])
    monkeypatch.setattr(model, "embed_passages", lambda texts, **kwargs: [[1.0]+[0.0]*383 for _ in texts])
    monkeypatch.setattr(model, "embed_query", lambda text, **kwargs: [1.0]+[0.0]*383)
    client = TestClient(create_app(activity_store=store, embedding_service=model, collection_interval=None))
    result = client.post("/documents", headers={"X-ContextTrace-Client": "desktop"},
        data={"context_id": str(rid), "file_path": r"C:\가상 자료\문서.docx"},
        files={"file": ("문서.docx", docx_bytes())})
    assert result.status_code == 201 and calls == []
    assert model._model is None
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM search_chunks").fetchone()[0] > 0
        assert db.execute("SELECT COUNT(*) FROM semantic_embeddings").fetchone()[0] == 0
    query = client.post("/records/semantic-search", json={"query": "검색할 내용"})
    assert query.status_code == 200 and calls == ["split"]
    hit = query.json()["data"]["hits"][0]
    assert hit["record"]["id"] == hit["context_id"] == str(rid)
    assert hit["source"]["document"]["file_path"] == r"C:\가상 자료\문서.docx"


def test_rag_drops_sources_deleted_while_generator_is_running(tmp_path):
    """모델 응답을 기다리는 사이 삭제된 근거를 답변의 출처로 반환하지 않는다."""
    store = ActivityStore(tmp_path / "deleted-rag.db")
    rid = work(store)
    model = SimpleNamespace(model_name="intfloat/multilingual-e5-small",
                            split_passage=lambda text, **kwargs: [text],
                            embed_passages=lambda texts, **kwargs: [[1.0]+[0.0]*383 for _ in texts],
                            embed_query=lambda text, **kwargs: [1.0]+[0.0]*383)

    class DeletingGenerator:
        """추론 경계에서만 삭제 경쟁 조건을 재현한다."""

        def generate(self, query, evidence):
            store.delete_activity_record(rid)
            return RAGAnswer("지금 삭제된 근거의 답변", [evidence[0].id])

    client = TestClient(create_app(activity_store=store, collection_interval=None, embedding_service=model,
                                   answer_generator=DeletingGenerator()))
    assert client.post("/documents", headers={"X-ContextTrace-Client": "desktop"},
        data={"context_id": str(rid), "file_path": r"C:\가상\문서.docx"},
        files={"file": ("문서.docx", docx_bytes())}).status_code == 201
    result = client.post("/records/answer", json={"query": "무슨 자료인가요"})
    assert result.status_code == 200
    data = result.json()["data"]
    assert data["insufficient_evidence"] is True and data["evidence"] == []
    assert "지금 삭제된 근거의 답변" not in data["answer"]


def test_browser_origin_cannot_delete_saved_records(tmp_path):
    """외부 페이지의 삭제 요청을 실제 변경 전에 거부한다."""
    store = ActivityStore(tmp_path / "origin.db")
    rid = work(store)
    client = TestClient(create_app(activity_store=store, collection_interval=None))
    assert client.delete(f"/records/{rid}", headers={"Origin": "https://example.test"}).status_code == 403
    assert client.delete("/records?confirm=true", headers={"Origin": "https://example.test"}).status_code == 403
    assert store.get_record(rid) is not None


def test_failed_browser_reindex_restores_previous_body(tmp_path):
    """같은 출처 갱신 중 모델이 실패해도 이전 원문·시각·잘림을 잃지 않는다."""
    store = ActivityStore(tmp_path / "retry.db")
    state = SimpleNamespace(fail=False)

    def split(text, **kwargs):
        """추론 경계의 두 번째 실행만 실패시킨다."""
        if state.fail:
            raise RuntimeError("Model temporarily unavailable")
        return [text]

    model = SimpleNamespace(model_name="intfloat/multilingual-e5-small", split_passage=split,
                            embed_passages=lambda texts, **kwargs: [[1.0]+[0.0]*383 for _ in texts])
    client = TestClient(create_app(activity_store=store, collection_interval=None,
                                   embedding_service=model, browser_token="boundary-token"))
    sid = client.post("/browser/source", headers=AUTH, json={"browser": "chrome",
        "page_title": "가상", "url": "https://example.test/"}).json()["data"]["id"]
    assert client.post("/browser/content", headers=AUTH,
        json={"browser_source_id": sid, "content_text": "보존할 이전 본문"}).status_code == 200
    before = store.get_browser_content_record(sid)
    state.fail = True
    response = client.post("/browser/content", headers=AUTH,
        json={"browser_source_id": sid, "content_text": "실패한 새 본문", "truncated": True})
    assert response.status_code == 503
    assert store.get_browser_content_record(sid) == before
    assert store.browser_content_truncated(sid) is False
