"""실제 API 표시 경계에서 다른 질문·임의 출처·잘못된 근거를 거부하는지 확인한다."""

import json
from dataclasses import asdict

import pytest
from PySide6.QtWidgets import QApplication

from client.ai_clients import RAGClient, source_chunk
from shared.document import LocalDocument
from shared.protocol import API_VERSION, SERVICE_NAME
from shared.search_data import SourceMetadata


@pytest.fixture
def app():
    """일반 Qt fixture와 동일하게 이벤트 객체의 수명을 테스트 동안 유지한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def evidence():
    """확보 시각과 작업 시각이 다른 정상 근거 응답을 만든다."""
    source = SourceMetadata("document", "Word", "winword.exe", "가상 문서",
                            "2026-11-20T09:00:00+00:00", "2026-11-20T09:05:00+00:00",
                            "2026-11-21T10:00:00+00:00", False,
                            document=LocalDocument(r"C:\자료\가상.docx", "docx"))
    return {"id": "saved-chunk", "context_id": "7", "source_kind": "document", "title": "가상.docx",
            "text": "저장된 근거 본문", "similarity": 0.9, "chunk_index": 0,
            "captured_at": source.captured_at, "url": None, "file_path": source.document.file_path,
            "content_truncated": False, "source": asdict(source)}


@pytest.mark.parametrize("change", ["source_missing", "path", "time", "boolean_id", "nan", "text"])
def test_malformed_evidence_is_never_completed_with_placeholder_metadata(change):
    """부족하거나 모순된 근거에서 작업 ID·시각·경로를 임시로 채우지 않는다."""
    row = evidence()
    if change == "source_missing":
        row.pop("source")
    elif change == "path":
        row["file_path"] = r"C:\다른 자료\가상.docx"
    elif change == "time":
        row["captured_at"] = "2026-11-22T10:00:00+00:00"
    elif change == "boolean_id":
        row["context_id"] = True
    elif change == "nan":
        row["similarity"] = float("nan")
    else:
        row["text"] = "x"*4001
    with pytest.raises(ValueError):
        source_chunk(row)


def test_answer_confirms_query_and_preserves_actual_source_times(app, monkeypatch):
    """POST 조건을 확인하고 확보 시각을 작업 열람 시각으로 바꾸지 않는다."""
    client = RAGClient(8765)
    requests, answers, failures = [], [], []
    monkeypatch.setattr(client, "post", lambda path, payload: requests.append((path, payload)))
    client.answer_received.connect(lambda *args: answers.append(args))
    client.answer_failed.connect(lambda *args: failures.append(args))
    client.ask(4, "자료를 설명해줘")
    expected = json.loads(requests[0][1])
    assert requests[0][0] == "/records/answer"
    row = evidence()
    data = {"service": SERVICE_NAME, "api_version": API_VERSION, "request": expected,
            "answer": "[1]에 따른 답변", "evidence": [row], "insufficient_evidence": False}
    client._received(json.dumps({"ok": True, "error": None, "data": data}).encode())
    assert answers[0][0] == 4 and failures == []
    chunk = answers[0][1].evidence[0]
    assert chunk.context_id == "7"
    assert chunk.source.captured_at != chunk.source.last_active_at
    data["request"] = {**expected, "query": "다른 질문"}
    client._received(json.dumps({"ok": True, "error": None, "data": data}).encode())
    assert len(answers) == 1 and len(failures) == 1
    client.close()


def test_backend_basic_rag_does_not_invent_original_path_or_capture_time():
    """원본 Backend의 평면 근거로 표시·시간 정렬을 수행하되 원본 경로를 단정하지 않는다."""
    from client.search_presentation import chunk_metadata, ordered_chunks

    row = evidence()
    del row["context_id"], row["source"]
    chunk = source_chunk(row)
    assert chunk.context_id is None and chunk.source.last_active_at is None
    detail = chunk_metadata(chunk)
    assert row["file_path"] in detail and "원본 경로 미확인" in detail
    assert "본문 확보 시각 미제공" in detail and "Backend 응답 시각" in detail
    assert ordered_chunks([chunk], "oldest") == [(0, chunk)]


def test_backend_basic_semantic_hit_without_source():
    """기본 웹 검색 ID를 작업 ID로 바꾸거나 미제공 시각을 추정하지 않는다."""
    from client.search_presentation import chunk_metadata

    row = evidence()
    record = dict(id="web-19", application="Chrome", process_name="chrome.exe",
                  window_title="탭", started_at=row["captured_at"], last_active_at=row["captured_at"],
                  active_duration_ms=0, foreground_count=1, document=None,
                  browser=dict(browser="chrome", page_title="자료", url="https://example.test/"))
    hit = dict(chunk_id="page", preview="자료", similarity=0.8, chunk_index=0,
               content_truncated=False, record=record)
    chunk = source_chunk(hit, preview=True)
    assert chunk.context_id is None
    assert "https://example.test/" in chunk_metadata(chunk) and "본문 확보 시각 미제공" in chunk_metadata(chunk)


def test_backend_upload_ack_without_context_is_success_not_verified_link(app):
    """Backend 201의 문서 ID만 인정하고 요청한 작업 ID를 응답에 보충하지 않는다."""
    from client.documents_client import DocumentsClient

    client = DocumentsClient(8765)
    client.operation, client.expected_record_id = "upload", "7"
    received = []
    client.document_uploaded.connect(received.append)
    row = dict(id=5, file_name="자료.pdf", file_type=".pdf", extracted_text="자료", captured_at=evidence()["captured_at"])
    client._received(json.dumps(dict(ok=True, error=None, data=row)).encode())
    assert [(d.id, d.record_id, d.file_path) for d in received] == [(5, None, None)]
    client.close()
