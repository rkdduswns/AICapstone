"""로컬 문서 출처와 저장 본문 조회 계약. 파일 탐색·추출·저장은 Backend 책임이다."""

import re
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

RECORD_DOCUMENT_CONTENT_PATH = "/records/document-content"
MAX_DOCUMENT_CONTENT_LENGTH = 50000
DOCUMENTS_PATH = "/documents"
MAX_DOCUMENT_UPLOAD_BYTES = 20 * 1024 * 1024
DOCUMENT_LIST_LIMIT = 20


@dataclass(frozen=True)
class ImportedDocument:
    """명시적으로 가져온 문서. 저장 시각만 알며 원본 경로나 작업 열람 시각을 추정하지 않는다."""

    id: int
    file_name: str
    file_type: Literal["pdf", "docx"]
    captured_at: str
    extracted_text: str
    record_id: str | None = None
    file_path: str | None = None


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


def read_document(raw: object) -> LocalDocument | None:
    """선택적 출처를 검사하며 상대 경로·장치 경로·유형 불일치는 오류로 처리한다.

    PureWindowsPath는 Linux에서도 Windows 경로를 문자열로 검사할 수 있다.
    resolve/exists를 쓰지 않아 다른 PC의 파일을 읽거나 UNC 서버에 접속하지 않는다.
    원문 경로는 목록/본문 출처를 정확히 대조할 수 있도록 수정하지 않고 반환한다.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Invalid document source")
    path, file_type = raw.get("file_path"), raw.get("file_type")
    if (not isinstance(path, str) or not path or file_type not in ("pdf", "docx")
            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise ValueError("Invalid document path or type")
    windows_path = PureWindowsPath(path)
    # 드라이브 절대 경로와 UNC 공유 경로만 지원하며 확장 장치 네임스페이스는 제외한다.
    drive = windows_path.drive
    if (not windows_path.is_absolute() or path.replace("/", "\\").startswith(("\\\\?\\", "\\\\.\\"))
            or not (re.fullmatch(r"[A-Za-z]:", drive) or drive.startswith("\\\\"))):
        raise ValueError("Expected Windows absolute file path")
    # UNC 서버/공유 이름도 파일 경로의 일부이므로 동일한 문자 검사를 적용한다.
    parts = windows_path.parts[1:]
    if drive.startswith("\\\\"):
        parts = tuple(drive[2:].split("\\")) + parts
    if (not parts or any(part in (".", "..") or any(c in '<>:"|?*' for c in part)
                         or part.endswith((" ", ".")) for part in parts)
            or windows_path.suffix.lower() != f".{file_type}"):
        raise ValueError("Invalid document path or extension")
    return LocalDocument(path, file_type)
