"""저장 문서 본문을 작업 ID로 조회한다. 파일을 직접 읽거나 PDF/DOCX를 추출하지 않는다."""

import json
from urllib.parse import quote

from PySide6.QtCore import QObject, Signal

from client.document_values import read_document
from client.json_request import JsonRequest
from client.time_values import parse_timestamp
from shared.document import (
    MAX_DOCUMENT_CONTENT_LENGTH,
    RECORD_DOCUMENT_CONTENT_PATH,
    DocumentContent,
    LocalDocument,
    RecordDocumentContent,
)
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME


class DocumentSourceChangedError(ValueError):
    """목록 조회 후 같은 작업의 파일 출처가 바뀌어 출처를 다시 확인해야 하는 경우."""


def read_record_document_content(
    payload: bytes, record_id: str, document: LocalDocument,
) -> RecordDocumentContent:
    """작업 ID와 파일 경로/유형을 함께 검사해 선택한 출처의 저장 본문만 반환한다.

    경로는 목록에서 확인된 원문과 정확히 대조한다. Client가 실제 파일을 열어
    존재 여부나 내용을 확인하지 않으며 출처 변경 시 목록 갱신을 요청한다.
    """
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True
            or "error" not in body or body["error"] is not None):
        raise ValueError("Invalid document content envelope")
    data = body.get("data")
    if (not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION
            or data.get("record_id") != record_id or "content" not in data):
        raise ValueError("Incompatible document content response")
    content = data["content"]
    if content is None:
        return RecordDocumentContent(record_id, None)
    if not isinstance(content, dict):
        raise ValueError("Invalid document content")
    source = read_document(content.get("document"))
    if source is None:
        raise ValueError("Missing document source")
    if source != document:
        raise DocumentSourceChangedError("Document source changed")
    text, truncated = content.get("text"), content.get("truncated")
    if (not isinstance(text, str) or not text.strip() or len(text) > MAX_DOCUMENT_CONTENT_LENGTH
            or type(truncated) is not bool):
        raise ValueError("Invalid document content text")
    parse_timestamp(content.get("captured_at"))
    return RecordDocumentContent(
        record_id, DocumentContent(source, content["captured_at"], text, truncated))


class DocumentContentClient(JsonRequest):
    """단일 상세 요청을 유지하고 선택 전환 시 이전 요청과 비교 기준을 함께 제거한다."""

    content_received = Signal(object)
    content_failed = Signal(str)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        """공통 HTTP 계층의 timeout/취소를 재사용하고 문서 본문 검증만 추가한다."""
        super().__init__(port, parent)
        self.record_id: str | None = None
        self.document: LocalDocument | None = None
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def fetch(self, record_id: str, document: LocalDocument) -> None:
        """파일 경로를 요청에 넣지 않고 loopback에 인코딩한 작업 ID만 보낸다."""
        self.close()
        self.record_id, self.document = record_id, document
        self.get(f"{RECORD_DOCUMENT_CONTENT_PATH}?record_id={quote(record_id, safe='')}")

    def _received(self, payload: bytes) -> None:
        """취소된 요청은 무시하고 출처 변경과 일반 계약 오류를 구분해 안내한다."""
        if self.record_id is None or self.document is None:
            return
        try:
            result = read_record_document_content(payload, self.record_id, self.document)
        except DocumentSourceChangedError:
            self.content_failed.emit("파일 출처가 변경되었습니다. 최근 기록을 새로고침해 주세요.")
            return
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        self.content_received.emit(result)

    def _failed(self, reason: str, status: int) -> None:
        """서버 오류 본문을 노출하지 않고 조회 불가·거부·시간 초과를 구분한다."""
        if reason == "http" and status == 404:
            message = "조회 불가 — 기능 미지원 또는 삭제된 기록입니다. 최근 기록을 새로고침해 주세요."
        elif reason == "http" and status == 410:
            message = "문서 출처를 조회할 수 없습니다. 이동·삭제 여부를 확인하고 최근 기록을 새로고침해 주세요."
        elif reason == "http" and status == 403:
            message = "문서 본문 조회가 허용되지 않았습니다. 개인정보 설정을 확인해 주세요."
        else:
            message = {
                "timeout": "문서 본문 조회 시간 초과 — 다시 확인해 주세요.",
                "http": "문서 본문 조회 실패 — 서버 오류입니다.",
                "network": "연결 안 됨 — Backend 실행 후 다시 확인해 주세요.",
                "content_type": "호환되지 않는 문서 본문 응답 — 다시 확인해 주세요.",
            }[reason]
        self.content_failed.emit(message)

    def close(self) -> None:
        """선택 해제/재연결/종료 시 늦은 응답이 이전 출처와 본문을 복원하지 못하게 한다."""
        super().close()
        self.record_id, self.document = None, None
