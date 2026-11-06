"""저장된 작업의 웹·문서 본문을 검색용 텍스트로 준비하는 로컬 진입점."""

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from backend.privacy import PrivacyPolicy
from backend.privacy_settings import StoredPrivacySettings
from backend.text_processing import normalize_text
from shared.browser import BrowserPage
from shared.document import LocalDocument, read_document


@dataclass(frozen=True)
class PreparedSearchText:
    """실제 작업·출처 ID와 본문 확보 시각이 붙은 분할 전 검색용 텍스트."""

    context_id: str
    source_id: str
    kind: Literal["web", "document"]
    captured_at: str
    text: str
    browser: BrowserPage | None = None
    document: LocalDocument | None = None


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


def prepare_search_texts(db_path: Path, record_id: int) -> list[PreparedSearchText] | None:
    """지정 작업의 실제 연결 본문을 읽어 준비한다. 작업이 없을 때만 None을 반환한다."""
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
            "SELECT application, process_name FROM activity_records WHERE id = ?", (record_id,)
        ).fetchone()
        if record is None:
            return None
        if policy.collection_paused or policy.is_blocked(
            record["application"], record["process_name"]
        ):
            return []

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
                prepared = _prepare_body(row["content_text"], row["captured_at"], policy)
                if prepared is not None:
                    results.append(PreparedSearchText(
                        str(record_id), str(row["id"]), "web", row["captured_at"], prepared,
                        browser=BrowserPage(row["browser"], row["page_title"], row["url"]),
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
                prepared = _prepare_body(row["extracted_text"], row["captured_at"], policy)
                if prepared is not None:
                    results.append(PreparedSearchText(
                        str(record_id), str(row["id"]), "document", row["captured_at"], prepared,
                        document=document,
                    ))
        return results


def main() -> None:
    """작업 하나의 준비 결과를 UTF-8 JSON으로 출력하고 오류에는 원문을 노출하지 않는다."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="저장된 작업 본문을 검색용으로 준비합니다.")
    parser.add_argument("--db-path", required=True, type=Path, help="기존 SQLite 작업 DB")
    parser.add_argument("--record-id", required=True, type=int, help="준비할 작업 ID")
    args = parser.parse_args()
    if not 1 <= args.record_id <= 2**63 - 1:
        parser.error("작업 ID는 1 이상의 SQLite 정수여야 합니다.")
    try:
        texts = prepare_search_texts(args.db_path, args.record_id)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        parser.exit(1, "작업 DB 또는 저장된 보호 설정을 읽지 못했습니다.\n")
    if texts is None:
        parser.exit(1, "지정한 작업 ID가 없습니다.\n")
    print(json.dumps([asdict(item) for item in texts], ensure_ascii=False))


if __name__ == "__main__":
    main()
