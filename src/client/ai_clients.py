"""실제 의미 검색·RAG API를 비동기로 호출하고 작업·출처가 확인된 응답만 표시한다."""

import json
import math
from dataclasses import asdict, replace

from PySide6.QtCore import Signal

from client.basic_search_source import read_basic_source
from client.compact_search_window import CompactAnswer
from client.json_request import JsonRequest
from client.records_client import read_context_records
from client.search_data_values import read_source_metadata
from shared.protocol import API_VERSION, SERVICE_NAME
from shared.rag import MAX_RAG_EVIDENCE_COUNT, MAX_RAG_QUERY_LENGTH, RAG_PATH, RAGRequest
from shared.search_data import DocumentChunk
from shared.semantic_search import SEMANTIC_SEARCH_PATH, SemanticSearchRequest


def response_data(payload: bytes, expected: dict) -> dict:
    """정상 프로토콜과 제출 조건을 대조해 다른 질문의 응답을 표시하지 않는다."""
    body = json.loads(payload)
    data = body.get("data") if isinstance(body, dict) else None
    if (not isinstance(body, dict) or body.get("ok") is not True or "error" not in body or body["error"] is not None
            or not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION
            or data.get("request") != expected):
        raise ValueError("Incompatible AI response")
    return data


def source_chunk(raw: dict, *, preview: bool = False) -> DocumentChunk:
    """응답에 없는 작업 ID·열람 시각·출처를 임의 생성하지 않고 스냅샷을 검사한다."""
    if not isinstance(raw, dict):
        raise ValueError("Invalid evidence")
    identifier = raw.get("chunk_id" if preview else "id")
    context = raw.get("context_id")
    text = raw.get("preview" if preview else "text")
    index, score = raw.get("chunk_index"), raw.get("similarity")
    if (not isinstance(identifier, str) or not identifier.strip()
            or (context is not None and (not isinstance(context, str) or not context.isascii()
                                        or not context.isdecimal() or context.startswith("0")))
            or not isinstance(text, str) or not text.strip() or len(text) > (600 if preview else 4000)
            or type(index) is not int or index < 0
            or type(score) not in (int, float) or not math.isfinite(score) or not -1 <= score <= 1
            or type(raw.get("content_truncated")) is not bool):
        raise ValueError("Invalid evidence fields")
    if "source" not in raw and "context_id" not in raw:
        # 기본 계약의 record.id와 실제 작업 ID는 별개다.
        return DocumentChunk(identifier, None, index, text, read_basic_source(raw, preview))
    source = read_source_metadata(raw.get("source"))
    if preview:
        record = read_context_records([raw.get("record")], 1)[0]
        if (context is not None and record.id != context and not (source.browser and record.id.startswith("web-") and record.id[4:].isascii() and record.id[4:].isdecimal())) or (
                record.application, record.process_name, record.window_title, record.started_at,
                record.last_active_at, record.browser, record.document) != (
                source.application, source.process_name, source.window_title, source.started_at,
                source.last_active_at, source.browser, source.document):
            raise ValueError("Semantic provenance does not match")
    else:
        address = source.browser.url if source.browser else None
        path = source.document.file_path if source.document else None
        if (raw.get("source_kind") != source.kind or raw.get("url") != address
                or raw.get("file_path") != path or raw.get("captured_at") != source.captured_at):
            raise ValueError("Evidence provenance does not match")
    source = replace(source, content_truncated=raw["content_truncated"] or source.content_truncated)
    return DocumentChunk(identifier, context, index, text, source)


class RAGClient(JsonRequest):
    """모델 실행을 기다리는 동안 UI를 유지하며 취소/재연결 시 늦은 응답을 폐기한다."""

    answer_received = Signal(int, object)
    answer_failed = Signal(int, str)

    def __init__(self, port, parent=None):
        """일반 상태 API보다 긴 로컬 모델 실행 제한을 별도로 적용한다."""
        super().__init__(port, parent)
        self.timer.setInterval(180000)
        self.request_id = 0
        self.expected = None
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def ask(self, request_id: int, query: str) -> None:
        """사용자가 제출한 질문만 실제 POST로 전송하고 기존 요청은 취소한다."""
        self.close()
        self.request_id = request_id
        query = query.strip()
        if (not query or len(query) > MAX_RAG_QUERY_LENGTH
                or any(ord(c) < 32 or ord(c) == 127 for c in query)):
            self.answer_failed.emit(request_id, "질문은 1~500자로 입력해 주세요.")
            return
        self.expected = asdict(RAGRequest(query=query))
        self.post(RAG_PATH, json.dumps(self.expected).encode())

    def _received(self, payload: bytes) -> None:
        """확인된 답변·실제 근거만 기존 소형 창의 표시 모델로 변환한다."""
        try:
            data = response_data(payload, self.expected)
            answer, rows, insufficient = data.get("answer"), data.get("evidence"), data.get("insufficient_evidence")
            if (not isinstance(answer, str) or not answer.strip() or len(answer) > 100000
                    or not isinstance(rows, list) or len(rows) > MAX_RAG_EVIDENCE_COUNT
                    or type(insufficient) is not bool or (not insufficient and not rows)):
                raise ValueError("Invalid RAG result")
            chunks = tuple(source_chunk(row) for row in rows)
            if len({c.id for c in chunks}) != len(chunks):
                raise ValueError("Duplicate evidence")
            result = CompactAnswer("insufficient" if insufficient else "answer",
                                   answer[:160], answer, chunks)
        except (ValueError, TypeError, KeyError, AttributeError):
            self.answer_failed.emit(self.request_id, "답변의 출처 정보를 확인할 수 없습니다.")
            return
        self.answer_received.emit(self.request_id, result)

    def _failed(self, reason: str, status: int) -> None:
        """모델 미설치·Ollama 중지·통신 실패를 성공한 가상 답변으로 바꾸지 않는다."""
        message = ("검색 모델 또는 Ollama를 사용할 수 없습니다. Backend 설정을 확인해 주세요."
                   if status == 503 else "답변 요청이 거부됐습니다." if status in (403, 422)
                   else "답변 대기 시간이 초과됐습니다." if reason == "timeout"
                   else "Backend에서 답변을 받지 못했습니다.")
        self.answer_failed.emit(self.request_id, message)


class SemanticSearchClient(JsonRequest):
    """질의와 조건을 실제 의미 검색 API에 전송하고 공급자 관련도 순서를 유지한다."""

    results_received = Signal(object)
    results_failed = Signal(str)

    def __init__(self, port, parent=None):
        """모델 로드 중에도 상태/개인정보 요청은 별도 객체에서 계속 처리한다."""
        super().__init__(port, parent)
        self.timer.setInterval(180000)
        self.expected = None
        self.received.connect(self._received)
        self.failed.connect(lambda reason, status: self.results_failed.emit(
            "의미 검색 모델 설정을 확인해 주세요." if status == 503 else "의미 검색 요청에 실패했습니다."))

    def search(self, request) -> None:
        """입력 화면에서 검증한 조건을 Shared HTTP 요청으로 바꾼다."""
        self.close()
        self.expected = asdict(SemanticSearchRequest(**asdict(request)))
        self.post(SEMANTIC_SEARCH_PATH, json.dumps(self.expected).encode())

    def _received(self, payload: bytes) -> None:
        """출처 스냅샷과 순서가 검증된 미리보기만 화면에 전달한다."""
        try:
            data = response_data(payload, self.expected)
            rows = data.get("hits")
            if (not isinstance(rows, list) or len(rows) > 20 or type(data.get("has_more")) is not bool):
                raise ValueError("Invalid semantic results")
            chunks = [source_chunk(row, preview=True) for row in rows]
            if len({chunk.id for chunk in chunks}) != len(chunks):
                raise ValueError("Duplicate semantic results")
        except (ValueError, TypeError, KeyError, AttributeError):
            self.results_failed.emit("의미 검색 출처를 확인할 수 없습니다.")
            return
        self.results_received.emit(chunks)
