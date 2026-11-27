"""Backend 기본 응답에 실제로 있는 값만 보관하는 UI 표시 모델."""

from dataclasses import dataclass
from pathlib import PureWindowsPath

from client.records_client import read_context_records
from shared.browser_values import normalize_http_url
from shared.document import read_document
from shared.time_values import parse_timestamp


@dataclass(frozen=True)
class BasicSource:
    """작업 시각·본문 확보 시각·원본 파일 경로가 없는 응답을 구분한다."""

    title: str
    kind_label: str
    address: str
    last_active_at: str | None
    content_truncated: bool
    reported_time: str | None = None


def read_basic_source(row, preview):
    """기본 검색 record 또는 기본 RAG 근거를 검사하고 응답 시각의 의미를 추정하지 않는다."""
    if preview:
        record = read_context_records([row["record"]], 1)[0]
        if bool(record.browser) == bool(record.document):
            raise ValueError("Ambiguous search source")
        if record.browser:
            if not record.browser.url:
                raise ValueError("Missing URL")
            return BasicSource(record.browser.page_title, "웹", record.browser.url,
                               None if record.id.startswith("web-") else record.last_active_at,
                               row["content_truncated"])
        return BasicSource(record.window_title, record.document.file_type.upper(), record.document.file_path,
                           record.last_active_at, row["content_truncated"])
    title = row["title"]
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Invalid evidence title")
    parse_timestamp(row["captured_at"])
    url, path = row.get("url"), row.get("file_path")
    if row["source_kind"] == "web" and isinstance(url, str) and path is None:
        normalize_http_url(url)
        kind, address = "웹", url
    elif row["source_kind"] == "document" and isinstance(path, str) and url is None:
        suffix = PureWindowsPath(path).suffix.lower()[1:]
        read_document({"file_path": path, "file_type": suffix})
        kind, address = suffix.upper(), path
    else:
        raise ValueError("Invalid basic evidence location")
    return BasicSource(title, kind, address, None, row["content_truncated"], row["captured_at"])
