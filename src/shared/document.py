"""로컬 문서 출처와 저장 본문 조회 계약. 파일 탐색·추출·저장은 Backend 책임이다."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

RECORD_DOCUMENT_CONTENT_PATH = "/records/document-content"
MAX_DOCUMENT_CONTENT_LENGTH = 50000


@dataclass(frozen=True)
class LocalDocument:
    """Backend가 식별한 Windows 절대 경로와 지원 문서 유형. Client는 파일을 읽지 않는다."""

    file_path: str
    file_type: Literal["pdf", "docx"]


@dataclass(frozen=True)
class DocumentContent:
    """추출 시점의 출처와 저장 텍스트. 일부만 보관했다면 truncated로 구분한다."""

    document: LocalDocument
    captured_at: str
    text: str
    truncated: bool


@dataclass(frozen=True)
class RecordDocumentContent:
    """작업 출처에 연결된 최신 저장 본문. None은 정상 조회했지만 저장 본문이 없는 경우다."""

    record_id: str
    content: DocumentContent | None
    service: str = SERVICE_NAME
    api_version: int = API_VERSION


@dataclass(frozen=True)
class RecordDocumentContentResponse:
    """다른 상세 조회와 같은 성공 envelope. 미지원과 조회 거부는 HTTP 오류로 전달한다."""

    data: RecordDocumentContent
    ok: Literal[True] = True
    error: None = None
