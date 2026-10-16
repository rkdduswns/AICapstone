"""Windows 문서 출처의 조회용 검증. 로컬 파일 존재 확인이나 경로 해석 실행은 하지 않는다."""

import re
from pathlib import PureWindowsPath

from shared.document import LocalDocument


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
