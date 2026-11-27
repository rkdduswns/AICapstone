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
