"""명시적으로 선택한 문서를 Backend에 전송하고 저장된 문서 목록을 조회한다."""

import json
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice, QObject, QUrl, Signal
from PySide6.QtNetwork import QHttpMultiPart, QHttpPart, QNetworkRequest

from client.json_request import JsonRequest
from client.time_values import parse_timestamp
from shared.document import (
    DOCUMENT_LIST_LIMIT,
    DOCUMENTS_PATH,
    MAX_DOCUMENT_UPLOAD_BYTES,
    ImportedDocument,
    read_document,
)


def read_imported_document(row: object) -> ImportedDocument:
    """실제 업로드 API의 필드를 검사하고 이름만 받은 파일을 절대 경로로 꾸미지 않는다."""
    if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1:
        raise ValueError("Invalid document ID")
    name, kind, text = row.get("file_name"), row.get("file_type"), row.get("extracted_text")
    if (not isinstance(name, str) or not name.strip() or kind not in (".pdf", ".docx")
            or not isinstance(text, str) or not text.strip()):
        raise ValueError("Invalid imported document")
    parse_timestamp(row.get("captured_at"))
    record_id = row.get("activity_record_id")
    path = None
    if record_id is not None:
        if type(record_id) is not int or record_id < 1:
            raise ValueError("Invalid linked record ID")
        path = read_document({"file_path": row.get("file_path"), "file_type": kind[1:]}).file_path
    return ImportedDocument(row["id"], name, kind[1:], row["captured_at"], text,
                            str(record_id) if record_id is not None else None, path)


class DocumentsClient(JsonRequest):
    """Qt multipart로 파일을 스트리밍하고 업로드는 자동 재전송하지 않는다."""

    success_statuses = (200, 201)
    documents_received = Signal(object)
    document_uploaded = Signal(object)
    documents_failed = Signal(str)

    def __init__(self, port: int, parent: QObject | None = None) -> None:
        """기존 loopback·프록시 차단·요청 취소를 재사용한다."""
        super().__init__(port, parent)
        self.operation = "list"
        self.expected_record_id: str | None = None
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def refresh(self) -> None:
        """업로드 도중에는 목록 요청을 만들지 않는다."""
        if self.reply is None:
            self.operation = "list"
            self.timer.setInterval(3000)
            self.get(f"{DOCUMENTS_PATH}?limit={DOCUMENT_LIST_LIMIT}")

    def upload(self, path: str, record_id: str | None = None, source_path: str | None = None) -> None:
        """사용자가 고른 파일 하나만 읽으며 문서 추출과 저장은 Backend에 맡긴다."""
        if self.reply is not None:
            return
        name = Path(path).name
        if (Path(name).suffix.lower() not in (".pdf", ".docx")
                or any(c in '\r\n"' for c in name)):
            self.documents_failed.emit("PDF 또는 DOCX 파일을 선택해 주세요.")
            return
        if record_id is not None:
            try:
                if not record_id.isascii() or not record_id.isdecimal() or int(record_id) < 1:
                    raise ValueError("Invalid record ID")
                source_path = source_path or str(Path(path).absolute())
                read_document({"file_path": source_path, "file_type": Path(name).suffix.lower()[1:]})
            except (ValueError, AttributeError):
                self.documents_failed.emit("연결할 실제 작업과 Windows 파일 경로를 확인해 주세요.")
                return
        multipart = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)
        source = QFile(path, multipart)
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            multipart.deleteLater()
            self.documents_failed.emit("선택한 파일을 읽을 수 없습니다.")
            return
        if source.size() == 0 or source.size() > MAX_DOCUMENT_UPLOAD_BYTES:
            multipart.deleteLater()
            self.documents_failed.emit("내용이 있는 20 MiB 이하의 문서를 선택해 주세요.")
            return
        part = QHttpPart()
        part.setRawHeader(b"Content-Disposition", f'form-data; name="file"; filename="{name}"'.encode())
        part.setBodyDevice(source)
        multipart.append(part)
        if record_id is not None:
            for key, value in (("record_id", record_id), ("file_path", source_path)):
                field = QHttpPart()
                field.setRawHeader(b"Content-Disposition", f'form-data; name="{key}"'.encode())
                field.setBody(value.encode())
                multipart.append(field)
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self.port}{DOCUMENTS_PATH}"))
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"X-ContextTrace-Client", b"desktop")
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.operation = "upload"
        self.expected_record_id = record_id
        self.timed_out = False
        self.reply = self.manager.post(request, multipart)
        multipart.setParent(self.reply)
        self.reply.finished.connect(self._finished)
        self.timer.start(30000)

    def _received(self, payload: bytes) -> None:
        """업로드와 목록 응답을 구분하고 유효한 전체 결과만 화면에 전달한다."""
        try:
            body = json.loads(payload)
            if (not isinstance(body, dict) or body.get("ok") is not True
                    or "error" not in body or body["error"] is not None):
                raise ValueError("Invalid document envelope")
            data = body.get("data")
            if self.operation == "upload":
                result = read_imported_document(data)
                if result.record_id != self.expected_record_id:
                    raise ValueError("Linked record does not match upload request")
            else:
                rows = data.get("documents") if isinstance(data, dict) else None
                if not isinstance(rows, list) or len(rows) > DOCUMENT_LIST_LIMIT:
                    raise ValueError("Invalid document list")
                result = [read_imported_document(row) for row in rows]
                if len({row.id for row in result}) != len(result):
                    raise ValueError("Duplicate document ID")
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        if self.operation == "upload":
            self.document_uploaded.emit(result)
        else:
            self.documents_received.emit(result)

    def _failed(self, reason: str, status: int) -> None:
        """서버 본문 대신 오류 종류를 알리고 응답 불명확 시 중복 업로드를 유도하지 않는다."""
        if reason == "http":
            message = {
                403: "가져오기가 허용되지 않았습니다. 일시정지·민감정보 여부를 확인해 주세요.",
                404: "기능 준비 중 — Backend가 문서 가져오기를 지원하지 않습니다.",
                413: "20 MiB 이하의 문서를 선택해 주세요.",
                415: "PDF 또는 DOCX 파일만 지원합니다.",
                422: "문서에서 텍스트를 추출할 수 없습니다. 파일 내용과 암호 설정을 확인해 주세요.",
            }.get(status, "문서 요청에 실패했습니다.")
        elif reason == "content_type":
            message = "호환되지 않는 문서 응답입니다."
        else:
            message = "문서 응답을 확인하지 못했습니다. 다시 가져오기 전에 목록을 새로고침해 주세요."
        self.documents_failed.emit(message)
