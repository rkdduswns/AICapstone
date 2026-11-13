"""저장된 작업의 웹·문서 본문을 검색용 텍스트와 조각으로 준비하는 로컬 진입점."""

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Iterator

from backend.privacy import PrivacyPolicy
from backend.privacy_settings import StoredPrivacySettings
from backend.text_processing import normalize_text
from shared.browser import BrowserPage
from shared.browser_values import read_browser
from shared.document import MAX_DOCUMENT_CONTENT_LENGTH, LocalDocument, read_document
from shared.search_data import DocumentChunk, SourceKind, SourceMetadata
from shared.time_values import parse_timestamp
from shared.web_content import MAX_WEB_CONTENT_LENGTH

SEARCH_CHUNK_SIZE = 1000
CHUNK_ID_VERSION = "v1"


@dataclass(frozen=True)
class PreparedSearchText:
    """실제 작업·출처 ID와 본문 확보 시각이 붙은 분할 전 검색용 텍스트."""

    context_id: str
    source_id: str
    kind: SourceKind
    captured_at: str
    text: str
    browser: BrowserPage | None = None
    document: LocalDocument | None = None


@dataclass(frozen=True)
class _PreparedSource:
    """정규화 본문과 원문 길이로 확인한 기존 상세 조회 표시 상태."""

    body: PreparedSearchText
    content_truncated: bool


def _read_policy(connection: sqlite3.Connection, tables: set[str]) -> PrivacyPolicy:
    """같은 읽기 시점의 저장 정책을 사용하며 설정이 없는 구형 DB는 기본값을 따른다."""
    if "privacy_settings" not in tables:
        return PrivacyPolicy()
    row = connection.execute(
        "SELECT payload FROM privacy_settings WHERE singleton = 1"
    ).fetchone()
    if row is None:
        return PrivacyPolicy()
    settings = StoredPrivacySettings.model_validate_json(row["payload"])
    return PrivacyPolicy(
        collection_paused=settings.paused,
        blocked_applications=set(settings.blocked_processes),
    )


def _prepare_body(text: str, captured_at: str, policy: PrivacyPolicy) -> str | None:
    """확보 시각과 정규화 전후의 본문을 확인해 유효한 검색용 텍스트만 반환한다."""
    try:
        captured = datetime.fromisoformat(captured_at)
    except (TypeError, ValueError):
        return None
    if captured.utcoffset() is None or policy.contains_sensitive_data(text):
        return None
    prepared = normalize_text(text)
    # NUL 제거로 합쳐진 문자열에 민감 패턴이 새로 나타날 수 있다.
    return prepared if prepared and not policy.contains_sensitive_data(prepared) else None


def _read_prepared_sources(
    db_path: Path, record_id: int,
) -> tuple[sqlite3.Row, PrivacyPolicy, list[_PreparedSource]] | None:
    """보호 정책·작업·연결 본문을 같은 읽기 스냅샷에서 확인한다."""
    if not 1 <= record_id <= 2**63 - 1:
        raise ValueError("작업 ID가 범위를 벗어났습니다.")

    # 원본 DB를 생성하거나 마이그레이션하지 않고 정책·작업·본문을 한 시점에서 읽는다.
    database = f"{db_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(database, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        tables = {
            row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        policy = _read_policy(connection, tables)
        record = connection.execute(
            "SELECT application, process_name, window_title, started_at, ended_at "
            "FROM activity_records WHERE id = ?", (record_id,),
        ).fetchone()
        if record is None:
            return None
        if not isinstance(record["application"], str) or not isinstance(record["process_name"], str):
            raise ValueError("작업의 프로그램 정보를 읽을 수 없습니다.")
        if policy.collection_paused or policy.is_blocked(
            record["application"], record["process_name"]
        ):
            return record, policy, []

        results = []
        if "record_browser_sources" in tables:
            rows = connection.execute(
                """SELECT source.id, source.browser, source.page_title, source.url,
                          body.captured_at, body.content_text
                   FROM record_browser_sources AS link
                   JOIN browser_source_records AS source ON source.id = link.source_id
                   JOIN browser_content_records AS body ON body.browser_source_id = source.id
                   WHERE link.record_id = ? ORDER BY source.id""",
                (record_id,),
            )
            for row in rows:
                # 출처를 재구성하지 않는다. 기존 저장 정책과 맞지 않는 출처는 건너뛴다.
                try:
                    if policy.sanitize_browser_url(row["url"]) != row["url"]:
                        continue
                except ValueError:
                    continue
                if row["browser"] not in ("chrome", "edge") or policy.contains_sensitive_data(
                    row["page_title"]
                ):
                    continue
                raw_text = row["content_text"]
                prepared = _prepare_body(raw_text, row["captured_at"], policy)
                if prepared is not None:
                    results.append(_PreparedSource(
                        PreparedSearchText(
                            str(record_id), str(row["id"]), "web", row["captured_at"], prepared,
                            browser=BrowserPage(row["browser"], row["page_title"], row["url"]),
                        ),
                        len(raw_text) > MAX_WEB_CONTENT_LENGTH,
                    ))

        if "record_document_sources" in tables:
            rows = connection.execute(
                """SELECT source.id, source.file_path, source.file_type,
                          source.captured_at, source.extracted_text
                   FROM record_document_sources AS link
                   JOIN document_records AS source ON source.id = link.source_id
                   WHERE link.record_id = ? ORDER BY source.id""",
                (record_id,),
            )
            for row in rows:
                if policy.contains_sensitive_data(row["file_path"]):
                    continue
                try:
                    document = read_document({
                        "file_path": row["file_path"], "file_type": row["file_type"][1:],
                    })
                except ValueError:
                    continue
                raw_text = row["extracted_text"]
                prepared = _prepare_body(raw_text, row["captured_at"], policy)
                if prepared is not None:
                    results.append(_PreparedSource(
                        PreparedSearchText(
                            str(record_id), str(row["id"]), "document", row["captured_at"], prepared,
                            document=document,
                        ),
                        len(raw_text) > MAX_DOCUMENT_CONTENT_LENGTH,
                    ))
        return record, policy, results


def prepare_search_texts(db_path: Path, record_id: int) -> list[PreparedSearchText] | None:
    """지정 작업의 분할 전 본문을 기존 출력 형식으로 반환한다."""
    snapshot = _read_prepared_sources(db_path, record_id)
    if snapshot is None:
        return None
    _, _, sources = snapshot
    return [source.body for source in sources]


def _split_text(text: str) -> Iterator[str]:
    """최대 크기의 후반부에서 줄바꿈과 공백을 우선하여 겹치지 않게 나눈다."""
    start = 0
    while start < len(text):
        end = min(start + SEARCH_CHUNK_SIZE, len(text))
        if end < len(text):
            midpoint = start + SEARCH_CHUNK_SIZE // 2
            line_end = text.rfind("\n", midpoint, end)
            if line_end >= 0:
                end = line_end + 1
            else:
                for position in range(end - 1, midpoint - 1, -1):
                    if text[position].isspace():
                        end = position + 1
                        break
        part = text[start:end].strip()
        if part:
            yield part
        start = end


def prepare_search_chunks(db_path: Path, record_id: int) -> list[DocumentChunk] | None:
    """실제 작업과 본문 확보 당시 출처를 붙인 검색 조각을 생성한다."""
    snapshot = _read_prepared_sources(db_path, record_id)
    if snapshot is None:
        return None
    record, policy, sources = snapshot
    if not sources:
        return []
    application, process, title = record["application"], record["process_name"], record["window_title"]
    if not all(isinstance(value, str) for value in (application, process, title)):
        return []
    if not application.strip() or not process.strip() or any(
        policy.contains_sensitive_data(value) for value in (application, process, title)
    ):
        return []
    try:
        if parse_timestamp(record["ended_at"]) < parse_timestamp(record["started_at"]):
            return []
    except ValueError:
        return []

    chunks = []
    for source in sources:
        body = source.body
        try:
            parse_timestamp(body.captured_at)
            if body.browser is not None:
                # Client와 동일한 URL 계약을 검사하고 원래 저장 주소를 유지한다.
                read_browser(asdict(body.browser))
        except ValueError:
            continue
        parts = list(dict.fromkeys(_split_text(body.text)))
        # 분할 경계에서 민감 패턴의 단어 시작점이 새로 드러나면 해당 출처를 제외한다.
        if any(policy.contains_sensitive_data(part) for part in parts):
            continue
        metadata = SourceMetadata(
            body.kind, application, process, title, record["started_at"], record["ended_at"],
            body.captured_at, source.content_truncated, body.browser, body.document,
        )
        # 확보 시각과 본문에 고정하여 같은 출처의 재전송을 구분한다.
        # 작업의 마지막 활성 시각 갱신은 본문 스냅샷의 조각 ID를 바꾸지 않는다.
        snapshot_key = json.dumps(
            [CHUNK_ID_VERSION, SEARCH_CHUNK_SIZE, body.context_id, body.kind,
             body.source_id, body.captured_at, body.text],
            ensure_ascii=False, separators=(",", ":"),
        )
        digest = sha256(snapshot_key.encode("utf-8")).hexdigest()
        chunks.extend(
            DocumentChunk(f"{CHUNK_ID_VERSION}-{digest}-{index}", body.context_id, index, part, metadata)
            for index, part in enumerate(parts)
        )
    return chunks


def main() -> None:
    """작업 하나의 준비 결과를 UTF-8 JSON으로 출력하고 오류에는 원문을 노출하지 않는다."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="저장된 작업 본문을 검색용으로 준비합니다.")
    parser.add_argument("--db-path", required=True, type=Path, help="기존 SQLite 작업 DB")
    parser.add_argument("--record-id", required=True, type=int, help="준비할 작업 ID")
    parser.add_argument("--chunks", action="store_true", help="출처가 붙은 검색 조각으로 출력")
    args = parser.parse_args()
    if not 1 <= args.record_id <= 2**63 - 1:
        parser.error("작업 ID는 1 이상의 SQLite 정수여야 합니다.")
    try:
        prepare = prepare_search_chunks if args.chunks else prepare_search_texts
        items = prepare(args.db_path, args.record_id)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        parser.exit(1, "작업 DB 또는 저장된 보호 설정을 읽지 못했습니다.\n")
    if items is None:
        parser.exit(1, "지정한 작업 ID가 없습니다.\n")
    print(json.dumps([asdict(item) for item in items], ensure_ascii=False))


if __name__ == "__main__":
    main()
