
"""SQLite persistence for activity records."""

import json
import math
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from backend.activity_deletion import ActivityDeletionMixin
from backend.privacy_settings import StoredPrivacySettings
from shared.activity import (
    ActiveWindow,
    ActivityRecord,
    BrowserContentRecord,
    BrowserSourceRecord,
    ClipboardRecord,
    DocumentRecord,
)
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.records import ContextRecord
from shared.search_data import (
    MAX_CHUNK_TEXT_LENGTH,
    DocumentChunk,
    SourceMetadata,
)
from shared.semantic_search import MIN_SEMANTIC_SIMILARITY, SEMANTIC_PREVIEW_LENGTH
from shared.sessions import SESSION_GAP_SECONDS


def _activity_time_key(value: str) -> str | None:
    """시간대와 소수초를 보존한 UTC 고정 길이 키로 실제 마지막 활성 순간을 비교한다."""
    try:
        instant = datetime.fromisoformat(value)
        # 시간대가 없는 과거 기록은 기존 SQLite 날짜 함수와 같이 UTC로 해석한다.
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, OverflowError):
        # 해석 불가인 기존 값은 julianday와 같이 NULL로 정렬한다. 저장 원문은 바꾸지 않는다.
        return None


class ActivityStore(ActivityDeletionMixin):
    """Persist activity, clipboard, browser, and document records."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        # 표시명 변경 후에도 기존 기록·보호 설정을 같은 DB에서 읽는다.
        self._db_path = (
            Path(db_path)
            if db_path is not None
            else Path.home() / ".contexttrace" / "activity.db"
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        """Open a database connection with row access and foreign keys enabled."""
        connection = sqlite3.connect(self._db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """기존 원문·실제 연결을 보존하면서 세션·검색 스키마를 추가하고 파생 자료 수명을 관리한다."""
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS activity_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        application TEXT NOT NULL,
                        process_name TEXT NOT NULL,
                        process_id INTEGER NOT NULL,
                        window_title TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        ended_at TEXT NOT NULL,
                        active_duration_ms INTEGER NOT NULL
                            CHECK (active_duration_ms >= 0)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        started_at TEXT NOT NULL,
                        ended_at TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                # Add the session relationship without rebuilding or losing the
                # activity table in databases created by earlier project phases.
                activity_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(activity_records)"
                    ).fetchall()
                }
                if "session_id" not in activity_columns:
                    connection.execute(
                        """
                        ALTER TABLE activity_records
                        ADD COLUMN session_id INTEGER
                        REFERENCES sessions(id) ON DELETE SET NULL
                        """
                    )

                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_activity_started_at
                    ON activity_records(started_at DESC, id DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_activity_session_id
                    ON activity_records(session_id, started_at, id)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_sessions_started_at
                    ON sessions(started_at DESC, id DESC)
                    """
                )

                self._backfill_activity_sessions(connection)

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS clipboard_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        application TEXT NOT NULL,
                        activity_started_at TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        content TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_clipboard_captured_at
                    ON clipboard_records(captured_at DESC, id DESC)
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS browser_source_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        browser TEXT NOT NULL,
                        url TEXT NOT NULL,
                        page_title TEXT NOT NULL,
                        captured_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_browser_source_captured_at
                    ON browser_source_records(captured_at DESC, id DESC)
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS browser_content_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        browser_source_id INTEGER NOT NULL
                            REFERENCES browser_source_records(id)
                            ON DELETE CASCADE,
                        content_text TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        UNIQUE(browser_source_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_browser_content_captured_at
                    ON browser_content_records(captured_at DESC, id DESC)
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        context_id INTEGER
                            REFERENCES activity_records(id)
                            ON DELETE CASCADE,
                        file_path TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        extracted_text TEXT NOT NULL,
                        captured_at TEXT NOT NULL
                    )
                    """
                )

                # Migrate existing databases without losing old documents.
                document_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(document_records)"
                    ).fetchall()
                }

                if "context_id" not in document_columns:
                    connection.execute(
                        """
                        ALTER TABLE document_records
                        ADD COLUMN context_id INTEGER
                        REFERENCES activity_records(id)
                        ON DELETE CASCADE
                        """
                    )

                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_document_captured_at
                    ON document_records(captured_at DESC, id DESC)
                    """
                )
                # 기존 데이터를 추측해 연결하지 않고 명시적인 연결만 새 테이블에 보존한다.
                for kind, source_table in (("browser", "browser_source_records"),
                                           ("document", "document_records")):
                    connection.execute(
                        f"CREATE TABLE IF NOT EXISTS record_{kind}_sources ("
                        "record_id INTEGER NOT NULL REFERENCES activity_records(id) ON DELETE CASCADE, "
                        f"source_id INTEGER NOT NULL UNIQUE REFERENCES {source_table}(id) "
                        "ON DELETE CASCADE, PRIMARY KEY(record_id, source_id))"
                    )
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(document_records)")}
                if "stored_file_path" not in columns:
                    connection.execute("ALTER TABLE document_records ADD COLUMN stored_file_path TEXT")
                body_columns = {row["name"] for row in connection.execute("PRAGMA table_info(browser_content_records)")}
                if "truncated" not in body_columns:
                    connection.execute("ALTER TABLE browser_content_records ADD COLUMN truncated INTEGER NOT NULL DEFAULT 0")
                conflict = connection.execute(
                    "SELECT 1 FROM record_document_sources l JOIN document_records d ON d.id=l.source_id "
                    "WHERE d.context_id IS NOT NULL AND d.context_id != l.record_id LIMIT 1").fetchone()
                if conflict:
                    raise ValueError("Conflicting persisted document links")
                connection.execute("UPDATE document_records SET context_id=(SELECT record_id FROM "
                    "record_document_sources WHERE source_id=document_records.id) WHERE context_id IS NULL")
                connection.execute("INSERT OR IGNORE INTO record_document_sources SELECT context_id,id "
                    "FROM document_records WHERE context_id IS NOT NULL")
                # 설정만 한 행에 저장하며 기존 작업·출처 행에는 손대지 않는다.
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS privacy_settings ("
                    "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), payload TEXT NOT NULL)"
                )

                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_document_context_id
                    ON document_records(context_id)
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_chunks (
                        id TEXT PRIMARY KEY,
                        document_id INTEGER NOT NULL
                            REFERENCES document_records(id)
                            ON DELETE CASCADE,
                        context_id INTEGER NOT NULL
                            REFERENCES activity_records(id)
                            ON DELETE CASCADE,
                        chunk_index INTEGER NOT NULL
                            CHECK (chunk_index >= 0),
                        text TEXT NOT NULL,
                        semantic_data_id TEXT,
                        UNIQUE(document_id, chunk_index)
                    )
                    """
                )

                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_document_chunks_context
                    ON document_chunks(context_id, chunk_index)
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_sources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,

                        source_kind TEXT NOT NULL
                            CHECK (source_kind IN ('web', 'document')),

                        document_id INTEGER
                            REFERENCES document_records(id)
                            ON DELETE CASCADE,

                        browser_source_id INTEGER
                            REFERENCES browser_source_records(id)
                            ON DELETE CASCADE,

                        context_id INTEGER
                            REFERENCES activity_records(id)
                            ON DELETE CASCADE,

                        captured_at TEXT NOT NULL,

                        content_truncated INTEGER NOT NULL DEFAULT 0
                            CHECK (content_truncated IN (0, 1)),

                        metadata_json TEXT NOT NULL DEFAULT '{}',

                        CHECK (
                            (
                                source_kind = 'document'
                                AND document_id IS NOT NULL
                                AND browser_source_id IS NULL
                            )
                            OR
                            (
                                source_kind = 'web'
                                AND browser_source_id IS NOT NULL
                                AND document_id IS NULL
                            )
                        ),

                        UNIQUE(document_id),
                        UNIQUE(browser_source_id)
                    )
                    """
                )

                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_search_sources_context
                    ON search_sources(context_id, captured_at DESC)
                    """
                )

                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_search_sources_kind
                    ON search_sources(source_kind, captured_at DESC)
                    """
                )

                chunk_columns = {row["name"] for row in connection.execute("PRAGMA table_info(search_chunks)")}
                if chunk_columns and "search_source_id" not in chunk_columns:
                    if "record_id" not in chunk_columns:
                        raise ValueError("Unknown search_chunks schema")
                    connection.execute("ALTER TABLE search_chunks RENAME TO legacy_search_chunks_v1")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_chunks (
                        id TEXT PRIMARY KEY,

                        search_source_id INTEGER NOT NULL
                            REFERENCES search_sources(id)
                            ON DELETE CASCADE,

                        chunk_index INTEGER NOT NULL
                            CHECK (chunk_index >= 0),

                        text TEXT NOT NULL,

                        semantic_data_id TEXT,

                        UNIQUE(search_source_id, chunk_index)
                    )
                    """
                )

                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_search_chunks_source
                    ON search_chunks(search_source_id, chunk_index)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_embeddings (
                        semantic_data_id TEXT PRIMARY KEY,

                        chunk_id TEXT NOT NULL UNIQUE
                            REFERENCES search_chunks(id)
                            ON DELETE CASCADE,

                        model_name TEXT NOT NULL,

                        dimension INTEGER NOT NULL
                            CHECK (dimension > 0),

                        vector_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_semantic_embeddings_model
                    ON semantic_embeddings(model_name, dimension)
                    """
                )
                conflict = connection.execute(
                    "SELECT 1 FROM record_browser_sources l JOIN search_sources ss ON ss.browser_source_id=l.source_id "
                    "WHERE ss.context_id IS NOT NULL AND ss.context_id!=l.record_id LIMIT 1").fetchone()
                if conflict:
                    raise ValueError("Conflicting persisted browser links")
                connection.execute("INSERT OR IGNORE INTO record_browser_sources SELECT context_id,browser_source_id "
                    "FROM search_sources WHERE context_id IS NOT NULL AND browser_source_id IS NOT NULL")
                for name, table, columns, predicate in (
                    ("web_index_stale", "browser_content_records", "content_text,captured_at,truncated", "browser_source_id=NEW.browser_source_id"),
                    ("document_index_stale", "document_records", "extracted_text,file_path,captured_at,context_id", "document_id=NEW.id"),
                    ("privacy_index_stale", "privacy_settings", "payload", "1=1"),
                ):
                    connection.execute(f"CREATE TRIGGER IF NOT EXISTS {name} AFTER UPDATE OF {columns} "
                        f"ON {table} BEGIN DELETE FROM search_sources WHERE {predicate}; END")
        finally:
            connection.close()

    def load_privacy_settings(self) -> StoredPrivacySettings | None:
        """저장 행 없음과 잘못된 저장 값을 구분하여 복원 실패를 호출자에게 알린다."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload FROM privacy_settings WHERE singleton = 1"
            ).fetchone()
            return StoredPrivacySettings.model_validate_json(row["payload"]) if row else None
        finally:
            connection.close()

    def get_document_record(self, source_id: int) -> DocumentRecord | None:
        """최근 목록 제한과 무관하게 실제 문서 한 개를 읽는다."""
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM document_records WHERE id=?", (source_id,)).fetchone()
        finally:
            connection.close()
        return DocumentRecord(**{name: row[name] for name in DocumentRecord.__dataclass_fields__}) if row else None

    def browser_content_truncated(self, source_id: int) -> bool:
        """수집 단계에서 전달된 잘림 상태를 검색·본문 조회까지 유지한다."""
        connection = self._connect()
        try:
            row = connection.execute("SELECT truncated FROM browser_content_records WHERE browser_source_id=?",
                                     (source_id,)).fetchone()
            return bool(row[0]) if row else False
        finally:
            connection.close()

    def pending_index_materials(self, model_name: str) -> list[tuple[str, int, int | None]]:
        """존재하는 원본 중 검색 출처나 모델 벡터가 빠진 항목의 ID만 조회한다."""
        connection = self._connect()
        try:
            result = []
            for kind, source_table, id_column in (
                ("web", "browser_source_records", "browser_source_id"),
                ("document", "document_records", "document_id"),
            ):
                if kind == "web":
                    relation = ("JOIN browser_content_records body ON body.browser_source_id=r.id "
                                "LEFT JOIN record_browser_sources link ON link.source_id=r.id")
                    context = "COALESCE(link.record_id,ss.context_id)"
                    condition = "1=1"
                else:
                    relation, context, condition = "", "r.context_id", "r.context_id IS NOT NULL"
                rows = connection.execute(
                    f"SELECT r.id,{context} AS context_id,COUNT(c.id) AS total,COUNT(e.chunk_id) AS vectors "
                    f"FROM {source_table} r {relation} "
                    f"LEFT JOIN search_sources ss ON ss.{id_column}=r.id "
                    "LEFT JOIN search_chunks c ON c.search_source_id=ss.id "
                    "LEFT JOIN semantic_embeddings e ON e.chunk_id=c.id AND e.model_name=? "
                    f"WHERE {condition} GROUP BY r.id HAVING total=0 OR total!=vectors",
                    (model_name,),
                ).fetchall()
                result.extend((kind, row["id"], row["context_id"]) for row in rows)
            return result
        finally:
            connection.close()

    def get_chunk_provenance(self, chunk_id: str):
        """근거가 가진 실제 작업 연결과 확보 당시 메타데이터를 함께 반환한다."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT ss.context_id,ss.metadata_json FROM search_sources ss "
                "JOIN search_chunks c ON c.search_source_id=ss.id WHERE c.id=?", (chunk_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        raw = json.loads(row["metadata_json"])
        browser = BrowserPage(**raw["browser"]) if raw.get("browser") else None
        document = LocalDocument(**raw["document"]) if raw.get("document") else None
        return (str(row["context_id"]) if row["context_id"] is not None else None,
                SourceMetadata(**{**raw, "browser": browser, "document": document}))

    def update_privacy_settings(
        self, changes: dict, defaults: StoredPrivacySettings,
    ) -> StoredPrivacySettings:
        """최신 저장 상태에 요청 필드만 원자적으로 적용하고 커밋된 전체 설정을 반환한다."""
        connection = self._connect()
        try:
            with connection:
                # 읽기 전에 쓰기 잠금을 잡아 다른 필드의 동시 갱신을 덮어쓰지 않는다.
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT payload FROM privacy_settings WHERE singleton = 1"
                ).fetchone()
                current = (StoredPrivacySettings.model_validate_json(row["payload"])
                           if row else defaults)
                updated = StoredPrivacySettings.model_validate({**current.model_dump(), **changes})
                connection.execute(
                    "INSERT INTO privacy_settings(singleton, payload) VALUES (1, ?) "
                    "ON CONFLICT(singleton) DO UPDATE SET payload = excluded.payload",
                    (updated.model_dump_json(),),
                )
            return updated
        finally:
            connection.close()

    def save_search_source_and_chunks(
        self,
        source_kind: str,
        captured_at: str,
        chunks: list[str],
        document_id: int | None = None,
        browser_source_id: int | None = None,
        context_id: int | None = None,
        content_truncated: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> tuple[int, list[str]]:
        """Save a common search source and its chunks atomically."""

        if source_kind not in {"web", "document"}:
            raise ValueError("source_kind must be 'web' or 'document'")

        if not captured_at.strip():
            raise ValueError("captured_at must not be empty")

        if source_kind == "document":
            if document_id is None or browser_source_id is not None:
                raise ValueError(
                    "document source requires only document_id"
                )

        if source_kind == "web":
            if browser_source_id is None or document_id is not None:
                raise ValueError(
                    "web source requires only browser_source_id"
                )

        for value, name in (
            (document_id, "document_id"),
            (browser_source_id, "browser_source_id"),
            (context_id, "context_id"),
        ):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(f"{name} must be an integer")
                if value < 1:
                    raise ValueError(f"{name} must be positive")

        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list")

        for chunk in chunks:
            if not isinstance(chunk, str):
                raise TypeError("every chunk must be a string")

            if not chunk.strip():
                raise ValueError("chunks must not contain empty text")

            if len(chunk) > MAX_CHUNK_TEXT_LENGTH:
                raise ValueError(
                    f"chunk text must not exceed "
                    f"{MAX_CHUNK_TEXT_LENGTH} characters"
                )

        if not isinstance(content_truncated, bool):
            raise TypeError("content_truncated must be a boolean")

        metadata_json = json.dumps(
            metadata or {},
            ensure_ascii=False,
        )

        connection = self._connect()

        try:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO search_sources (
                        source_kind,
                        document_id,
                        browser_source_id,
                        context_id,
                        captured_at,
                        content_truncated,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_kind,
                        document_id,
                        browser_source_id,
                        context_id,
                        captured_at,
                        int(content_truncated),
                        metadata_json,
                    ),
                )

                search_source_id = int(cursor.lastrowid)
                chunk_ids = []

                for chunk_index, chunk_text in enumerate(chunks):
                    chunk_id = str(uuid.uuid4())

                    connection.execute(
                        """
                        INSERT INTO search_chunks (
                            id,
                            search_source_id,
                            chunk_index,
                            text,
                            semantic_data_id
                        )
                        VALUES (?, ?, ?, ?, NULL)
                        """,
                        (
                            chunk_id,
                            search_source_id,
                            chunk_index,
                            chunk_text,
                        ),
                    )

                    chunk_ids.append(chunk_id)

                return search_source_id, chunk_ids

        finally:
            connection.close()

    @staticmethod
    def _session_timestamp(value: str) -> datetime | None:
        """Parse an ISO timestamp for session grouping.

        Historical records without an explicit timezone are interpreted as UTC,
        matching the timestamp convention used by ActivityTracker.
        """
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _session_created_at() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _backfill_activity_sessions(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """Group legacy activity rows into sessions without changing the rows."""
        rows = connection.execute(
            """
            SELECT id, started_at, ended_at
            FROM activity_records
            WHERE session_id IS NULL
            """
        ).fetchall()
        if not rows:
            return

        parsed_rows = []
        invalid_rows = []
        for row in rows:
            started = self._session_timestamp(row["started_at"])
            ended = self._session_timestamp(row["ended_at"])
            if started is None or ended is None or ended < started:
                invalid_rows.append(row)
                continue
            parsed_rows.append((started, ended, row))

        parsed_rows.sort(key=lambda item: (item[0], item[2]["id"]))
        groups: list[list[tuple[datetime, datetime, sqlite3.Row]]] = []
        for item in parsed_rows:
            if not groups:
                groups.append([item])
                continue
            current_group = groups[-1]
            current_end = max(entry[1] for entry in current_group)
            if (item[0] - current_end).total_seconds() <= SESSION_GAP_SECONDS:
                current_group.append(item)
            else:
                groups.append([item])

        created_at = self._session_created_at()
        for group in groups:
            first = min(group, key=lambda item: (item[0], item[2]["id"]))
            last = max(group, key=lambda item: (item[1], item[2]["id"]))
            cursor = connection.execute(
                """
                INSERT INTO sessions (started_at, ended_at, created_at)
                VALUES (?, ?, ?)
                """,
                (first[2]["started_at"], last[2]["ended_at"], created_at),
            )
            session_id = int(cursor.lastrowid)
            connection.executemany(
                "UPDATE activity_records SET session_id = ? WHERE id = ?",
                [(session_id, item[2]["id"]) for item in group],
            )

        # Malformed legacy timestamps are retained and isolated rather than
        # preventing database initialization or being silently discarded.
        for row in invalid_rows:
            cursor = connection.execute(
                """
                INSERT INTO sessions (started_at, ended_at, created_at)
                VALUES (?, ?, ?)
                """,
                (row["started_at"], row["ended_at"], created_at),
            )
            connection.execute(
                "UPDATE activity_records SET session_id = ? WHERE id = ?",
                (int(cursor.lastrowid), row["id"]),
            )

    def _find_or_create_session(
        self,
        connection: sqlite3.Connection,
        started_at: str,
        ended_at: str,
    ) -> int:
        """Attach a record to any temporally compatible session.

        Activity records can be persisted out of chronological order (for
        example, when a long-running activity is flushed at shutdown). Compare
        parsed UTC timestamps rather than relying on insertion order or
        lexicographic ISO strings.
        """
        record_start = self._session_timestamp(started_at)
        record_end = self._session_timestamp(ended_at)
        if record_start is None or record_end is None or record_end < record_start:
            cursor = connection.execute(
                """
                INSERT INTO sessions (started_at, ended_at, created_at)
                VALUES (?, ?, ?)
                """,
                (started_at, ended_at, self._session_created_at()),
            )
            return int(cursor.lastrowid)

        rows = connection.execute(
            """
            SELECT s.id, s.started_at, s.ended_at
            FROM sessions AS s
            WHERE EXISTS (
                SELECT 1 FROM activity_records AS a WHERE a.session_id = s.id
            )
            """
        ).fetchall()

        compatible: list[tuple[int, datetime, datetime]] = []
        for row in rows:
            session_start = self._session_timestamp(row["started_at"])
            session_end = self._session_timestamp(row["ended_at"])
            if session_start is None or session_end is None or session_end < session_start:
                continue

            if record_end < session_start:
                gap = (session_start - record_end).total_seconds()
            elif record_start > session_end:
                gap = (record_start - session_end).total_seconds()
            else:
                gap = 0.0

            if gap <= SESSION_GAP_SECONDS:
                compatible.append((int(row["id"]), session_start, session_end))

        if not compatible:
            cursor = connection.execute(
                """
                INSERT INTO sessions (started_at, ended_at, created_at)
                VALUES (?, ?, ?)
                """,
                (started_at, ended_at, self._session_created_at()),
            )
            return int(cursor.lastrowid)

        # Keep the smallest existing ID stable and merge every compatible
        # session. A newly inserted record can bridge two formerly separate
        # sessions; leaving them split would make session membership depend on
        # record insertion order.
        compatible.sort(key=lambda item: item[0])
        primary_id = compatible[0][0]
        start_candidates = [(record_start, started_at)]
        end_candidates = [(record_end, ended_at)]
        for row in rows:
            row_id = int(row["id"])
            if row_id not in {item[0] for item in compatible}:
                continue
            parsed_start = self._session_timestamp(row["started_at"])
            parsed_end = self._session_timestamp(row["ended_at"])
            if parsed_start is not None:
                start_candidates.append((parsed_start, str(row["started_at"])))
            if parsed_end is not None:
                end_candidates.append((parsed_end, str(row["ended_at"])))
        updated_start = min(start_candidates, key=lambda item: item[0])[1]
        updated_end = max(end_candidates, key=lambda item: item[0])[1]

        merged_ids = [item[0] for item in compatible[1:]]
        if merged_ids:
            placeholders = ",".join("?" for _ in merged_ids)
            connection.execute(
                f"UPDATE activity_records SET session_id = ? "
                f"WHERE session_id IN ({placeholders})",
                (primary_id, *merged_ids),
            )
            connection.execute(
                f"DELETE FROM sessions WHERE id IN ({placeholders})",
                merged_ids,
            )

        connection.execute(
            "UPDATE sessions SET started_at = ?, ended_at = ? WHERE id = ?",
            (updated_start, updated_end, primary_id),
        )
        return primary_id

    def save_record(
        self,
        window: ActiveWindow,
        started_at: str,
        ended_at: str,
        active_duration_ms: int,
    ) -> int:
        """Save one completed activity and return its database ID."""
        if active_duration_ms < 0:
            raise ValueError("active_duration_ms must be non-negative")

        connection = self._connect()
        try:
            with connection:
                session_id = self._find_or_create_session(
                    connection,
                    started_at,
                    ended_at,
                )
                cursor = connection.execute(
                    """
                    INSERT INTO activity_records (
                        application,
                        process_name,
                        process_id,
                        window_title,
                        started_at,
                        ended_at,
                        active_duration_ms,
                        session_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        window.application,
                        window.process_name,
                        window.process_id,
                        window.window_title,
                        started_at,
                        ended_at,
                        active_duration_ms,
                        session_id,
                    ),
                )
                return int(cursor.lastrowid)
        finally:
            connection.close()

    def get_recent_sessions(self, limit: int = 50) -> list[dict[str, object]]:
        """Return recent work sessions with their activity counts."""
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    s.id,
                    s.started_at,
                    s.ended_at,
                    COUNT(a.id) AS activity_count
                FROM sessions AS s
                LEFT JOIN activity_records AS a ON a.session_id = s.id
                GROUP BY s.id, s.started_at, s.ended_at
                HAVING COUNT(a.id) > 0
                ORDER BY s.started_at DESC, s.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return [
            {
                "id": int(row["id"]),
                "started_at": str(row["started_at"]),
                "ended_at": str(row["ended_at"]),
                "activity_count": int(row["activity_count"]),
            }
            for row in rows
        ]

    def get_session(self, session_id: int) -> dict[str, object] | None:
        """Return one session summary, or None when it does not exist."""
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise TypeError("session_id must be an integer")
        if session_id < 1:
            raise ValueError("session_id must be positive")

        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT
                    s.id,
                    s.started_at,
                    s.ended_at,
                    COUNT(a.id) AS activity_count
                FROM sessions AS s
                LEFT JOIN activity_records AS a ON a.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id, s.started_at, s.ended_at
                """,
                (session_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None or int(row["activity_count"]) == 0:
            return None
        return {
            "id": int(row["id"]),
            "started_at": str(row["started_at"]),
            "ended_at": str(row["ended_at"]),
            "activity_count": int(row["activity_count"]),
        }

    def get_session_records(
        self,
        session_id: int,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ActivityRecord]:
        """Return a page of activity records belonging to one session."""
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise TypeError("session_id must be an integer")
        if session_id < 1:
            raise ValueError("session_id must be positive")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise TypeError("offset must be an integer")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    application,
                    process_name,
                    process_id,
                    window_title,
                    started_at,
                    ended_at,
                    active_duration_ms
                FROM activity_records
                WHERE session_id = ?
                ORDER BY started_at ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            ).fetchall()
        finally:
            connection.close()

        return [
            ActivityRecord(
                id=row["id"],
                application=row["application"],
                process_name=row["process_name"],
                process_id=row["process_id"],
                window_title=row["window_title"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                active_duration_ms=row["active_duration_ms"],
            )
            for row in rows
        ]

    def get_session_materials(self, session_id: int) -> dict[str, list[dict[str, object]]]:
        """Return document and browser source metadata associated with a session.

        Documents are linked through their activity context. Browser records
        have no activity FK in the existing schema, so they are associated by
        capture time within the session boundaries and by any search-source
        context link available in the database.
        """
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise TypeError("session_id must be an integer")
        if session_id < 1:
            raise ValueError("session_id must be positive")

        connection = self._connect()
        try:
            session = connection.execute(
                "SELECT started_at, ended_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                return {"documents": [], "web_pages": []}

            document_rows = connection.execute(
                """
                SELECT DISTINCT d.id, d.file_name, d.file_type, d.file_path,
                    d.captured_at, d.context_id
                FROM document_records AS d
                JOIN activity_records AS a ON a.id = d.context_id
                WHERE a.session_id = ?
                ORDER BY d.captured_at DESC, d.id DESC
                """,
                (session_id,),
            ).fetchall()

            # 같은 시각에 수집됐다는 이유로 다른 세션의 웹 출처를 연결하지 않는다.
            browser_rows = connection.execute(
                "SELECT DISTINCT b.id,b.browser,b.url,b.page_title,b.captured_at,"
                "CASE WHEN c.id IS NULL THEN 0 ELSE 1 END AS has_content "
                "FROM browser_source_records b "
                "JOIN record_browser_sources link ON link.source_id=b.id "
                "JOIN activity_records a ON a.id=link.record_id "
                "LEFT JOIN browser_content_records c ON c.browser_source_id=b.id "
                "WHERE a.session_id=? ORDER BY b.captured_at DESC,b.id DESC", (session_id,),
            ).fetchall()
        finally:
            connection.close()

        return {
            "documents": [
                {
                    "id": int(row["id"]),
                    "file_name": str(row["file_name"]),
                    "file_type": str(row["file_type"]),
                    "file_path": str(row["file_path"]),
                    "captured_at": str(row["captured_at"]),
                    "context_id": int(row["context_id"]) if row["context_id"] is not None else None,
                }
                for row in document_rows
            ],
            "web_pages": [
                {
                    "id": int(row["id"]),
                    "browser": str(row["browser"]),
                    "url": str(row["url"]),
                    "page_title": str(row["page_title"]),
                    "captured_at": str(row["captured_at"]),
                    "has_content": bool(row["has_content"]),
                }
                for row in browser_rows
            ],
        }

    def get_document_file_path(self, document_id: int) -> str | None:
        """Return the stored copy path for a document record."""
        self._validate_record_id(document_id, "document_id")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT stored_file_path AS file_path FROM document_records WHERE id = ?",
                (document_id,),
            ).fetchone()
        finally:
            connection.close()
        return str(row["file_path"]) if row is not None else None

    def get_activity_document_paths(self, activity_id: int) -> list[str]:
        """Return document-copy paths linked to an activity record."""
        self._validate_record_id(activity_id, "activity_id")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT stored_file_path AS file_path FROM document_records WHERE context_id = ? AND stored_file_path IS NOT NULL",
                (activity_id,),
            ).fetchall()
        finally:
            connection.close()
        return [str(row["file_path"]) for row in rows]

    def get_all_document_file_paths(self) -> list[str]:
        """Return paths of application-stored document copies."""
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT stored_file_path AS file_path FROM document_records WHERE stored_file_path IS NOT NULL"
            ).fetchall()
        finally:
            connection.close()
        return [str(row["file_path"]) for row in rows]

    def get_recent_records(self, limit: int = 50) -> list[ActivityRecord]:
        """실제 마지막 활성 순간과 문자열 ID로 정렬한 뒤 요청한 개수만 반환한다."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        connection = self._connect()
        try:
            # julianday의 부동소수점 변환은 서로 다른 마이크로초를 동률로 만들 수 있다.
            # SQLite에서 정밀한 키로 정렬해야 LIMIT 밖으로 빠진 기록을 Client가 잃지 않는다.
            connection.create_function("activity_time_key", 1, _activity_time_key, deterministic=True)
            rows = connection.execute(
                """
                SELECT
                    id,
                    application,
                    process_name,
                    process_id,
                    window_title,
                    started_at,
                    ended_at,
                    active_duration_ms
                FROM activity_records
                ORDER BY activity_time_key(ended_at) DESC, CAST(id AS TEXT) ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return [
            ActivityRecord(
                id=row["id"],
                application=row["application"],
                process_name=row["process_name"],
                process_id=row["process_id"],
                window_title=row["window_title"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                active_duration_ms=row["active_duration_ms"],
            )
            for row in rows
        ]

    def update_record(self, record_id: int, ended_at: str, active_duration_ms: int) -> None:
        """수집 중 저장 ID를 유지하며 마지막 관측 시각과 경과 시간만 갱신한다."""
        if active_duration_ms < 0:
            raise ValueError("Invalid duration")
        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    "UPDATE activity_records SET ended_at = ?, active_duration_ms = ? WHERE id = ?",
                    (ended_at, active_duration_ms, record_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Activity record not found")
                row = connection.execute("SELECT started_at FROM activity_records WHERE id=?", (record_id,)).fetchone()
                session_id = self._find_or_create_session(connection, row["started_at"], ended_at)
                connection.execute("UPDATE activity_records SET session_id=? WHERE id=?", (session_id, record_id))
        finally:
            connection.close()

    def _linked_source(self, kind: str, record_id: int):
        """고정된 내부 테이블 이름과 매개변수화한 실제 ID로 최신 출처를 조회한다."""
        table, model = {"browser": ("browser_source_records", BrowserSourceRecord),
                        "document": ("document_records", DocumentRecord)}[kind]
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT source.* FROM {table} AS source JOIN record_{kind}_sources AS link "
                "ON link.source_id = source.id WHERE link.record_id = ? "
                "ORDER BY source.id DESC LIMIT 1", (record_id,),
            ).fetchone()
        finally:
            connection.close()
        return model(**{name: row[name] for name in model.__dataclass_fields__}) if row is not None else None

    def get_record_browser(self, record_id: int) -> BrowserSourceRecord | None:
        """실제 외래 키로 연결된 브라우저 출처만 반환한다."""
        return self._linked_source("browser", record_id)

    def get_record_document(self, record_id: int) -> DocumentRecord | None:
        """명시적으로 연결한 문서 중 최신 항목을 반환한다. 이전 연결도 DB에 보존한다."""
        return self._linked_source("document", record_id)

    def source_record_id(self, kind: str, source_id: int) -> int | None:
        """출처가 속한 작업을 확인하여 늦은 본문이 다른 작업에 저장되지 않게 한다."""
        if kind not in ("browser", "document"):
            raise ValueError("Invalid source kind")
        connection = self._connect()
        try:
            row = connection.execute(f"SELECT record_id FROM record_{kind}_sources WHERE source_id = ?",
                                     (source_id,)).fetchone()
        finally:
            connection.close()
        return row[0] if row else None

    def get_record(self, record_id: int) -> ActivityRecord | None:
        """목록 제한과 무관하게 실제 저장 ID 하나를 조회한다. 외부 값을 SQL에 보간하지 않는다."""
        if type(record_id) is not int:
            raise TypeError("record_id must be an integer")
        if record_id < 1:
            raise ValueError("record_id must be positive")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM activity_records WHERE id = ?", (record_id,),
            ).fetchone()
        finally:
            connection.close()
        return ActivityRecord(**{name: row[name] for name in ActivityRecord.__dataclass_fields__}) if row else None

    def get_record_clipboard(self, record: ActivityRecord, limit: int) -> list[ClipboardRecord]:
        """기존 DB의 애플리케이션·세션 시작 키로 연결된 복사 항목만 조회한다.

        과거 스키마에 작업 외래 키가 없으므로 동일 키의 작업이 여러 개면 연결을 추측하지
        않는다. 제목이나 단순한 시간 근접도로 다른 작업의 텍스트를 가져오지 않는다.
        """
        connection = self._connect()
        try:
            count = connection.execute(
                "SELECT count(*) FROM activity_records WHERE application = ? AND started_at = ?",
                (record.application, record.started_at),
            ).fetchone()[0]
            if count != 1:
                return []
            rows = connection.execute(
                "SELECT * FROM clipboard_records WHERE application = ? AND activity_started_at = ? "
                "ORDER BY julianday(captured_at) DESC, id DESC LIMIT ?",
                (record.application, record.started_at, limit),
            ).fetchall()
        finally:
            connection.close()
        return [ClipboardRecord(**dict(row)) for row in rows]

    def save_clipboard_record(
        self,
        application: str,
        activity_started_at: str,
        captured_at: str,
        content: str,
    ) -> int:
        """Save one clipboard record and return its database ID."""
        if not content.strip():
            raise ValueError("content must not be empty")

        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO clipboard_records (
                        application,
                        activity_started_at,
                        captured_at,
                        content
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        application,
                        activity_started_at,
                        captured_at,
                        content,
                    ),
                )
                return int(cursor.lastrowid)
        finally:
            connection.close()

    def get_recent_clipboard_records(
        self,
        limit: int = 50,
    ) -> list[ClipboardRecord]:
        """Return recent clipboard records, newest first."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    application,
                    activity_started_at,
                    captured_at,
                    content
                FROM clipboard_records
                ORDER BY captured_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return [
            ClipboardRecord(
                id=row["id"],
                application=row["application"],
                activity_started_at=row["activity_started_at"],
                captured_at=row["captured_at"],
                content=row["content"],
            )
            for row in rows
        ]

    def save_browser_source_record(
        self,
        browser: str,
        url: str,
        page_title: str,
        captured_at: str,
        activity_record_id: int | None = None,
    ) -> int:
        """브라우저 출처를 저장하고 명시한 작업 연결도 같은 트랜잭션에서 확정한다."""
        if not browser.strip():
            raise ValueError("browser must not be empty")
        if not url.strip():
            raise ValueError("url must not be empty")
        if not page_title.strip():
            raise ValueError("page_title must not be empty")
        if not captured_at.strip():
            raise ValueError("captured_at must not be empty")

        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO browser_source_records (
                        browser,
                        url,
                        page_title,
                        captured_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (browser, url, page_title, captured_at),
                )
                source_id = int(cursor.lastrowid)
                if activity_record_id is not None:
                    connection.execute("INSERT INTO record_browser_sources VALUES (?, ?)",
                                       (activity_record_id, source_id))
                return source_id
        finally:
            connection.close()

    def get_browser_source_record(
        self,
        browser_source_id: int,
    ) -> BrowserSourceRecord | None:
        """Return one browser source record by its ID."""
        if isinstance(browser_source_id, bool) or not isinstance(
            browser_source_id, int
        ):
            raise TypeError("browser_source_id must be an integer")
        if browser_source_id < 1:
            raise ValueError("browser_source_id must be positive")

        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT id, browser, url, page_title, captured_at
                FROM browser_source_records
                WHERE id = ?
                """,
                (browser_source_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return BrowserSourceRecord(
            id=row["id"],
            browser=row["browser"],
            url=row["url"],
            page_title=row["page_title"],
            captured_at=row["captured_at"],
        )

    def get_recent_browser_source_records(
        self,
        limit: int = 50,
    ) -> list[BrowserSourceRecord]:
        """Return recent browser page records, newest first."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, browser, url, page_title, captured_at
                FROM browser_source_records
                ORDER BY captured_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return [
            BrowserSourceRecord(
                id=row["id"],
                browser=row["browser"],
                url=row["url"],
                page_title=row["page_title"],
                captured_at=row["captured_at"],
            )
            for row in rows
        ]

    def save_browser_content_record(
        self,
        browser_source_id: int,
        content_text: str,
        captured_at: str,
        truncated: bool = False,
    ) -> int:
        """Save text content associated with an existing browser source."""
        if browser_source_id < 1:
            raise ValueError("browser_source_id must be positive")
        if not content_text.strip():
            raise ValueError("content_text must not be empty")
        if not captured_at.strip():
            raise ValueError("captured_at must not be empty")

        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO browser_content_records (
                        browser_source_id,
                        content_text,
                        captured_at, truncated
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(browser_source_id) DO UPDATE SET
                        content_text = excluded.content_text, captured_at = excluded.captured_at, truncated = excluded.truncated
                    """,
                    (browser_source_id, content_text, captured_at, int(truncated)),
                )
                return connection.execute(
                    "SELECT id FROM browser_content_records WHERE browser_source_id = ?",
                    (browser_source_id,),
                ).fetchone()[0]
        finally:
            connection.close()

    def get_browser_content_record(
        self,
        browser_source_id: int,
    ) -> BrowserContentRecord | None:
        """Return content associated with one browser source, if present."""
        if browser_source_id < 1:
            raise ValueError("browser_source_id must be positive")

        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT id, browser_source_id, content_text, captured_at
                FROM browser_content_records
                WHERE browser_source_id = ?
                """,
                (browser_source_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return BrowserContentRecord(
            id=row["id"],
            browser_source_id=row["browser_source_id"],
            content_text=row["content_text"],
            captured_at=row["captured_at"],
        )

    def save_document_record(
        self,
        file_path: str | Path,
        extracted_text: str,
        captured_at: str,
        activity_record_id: int | None = None,
        file_name: str | None = None,
        context_id: int | None = None,
        stored_file_path: str | None = None,
    ) -> int:
        """기존 명시적 링크와 새 context_id를 같은 실제 작업으로 원자적으로 저장한다."""
        if context_id is not None and activity_record_id is not None and context_id != activity_record_id:
            raise ValueError("Conflicting document context IDs")
        context_id = context_id if context_id is not None else activity_record_id
        if context_id is not None and (type(context_id) is not int or context_id < 1):
            raise ValueError("Invalid document context ID")
        activity_record_id = context_id
        windows_path = PureWindowsPath(file_path)
        path = windows_path if windows_path.is_absolute() else Path(file_path)
        stored_file_name = file_name if file_name is not None else path.name

        if not str(file_path).strip():
            raise ValueError("file_path must not be empty")
        if not stored_file_name.strip():
            raise ValueError("file_name must not be empty")
        if not extracted_text.strip():
            raise ValueError("extracted_text must not be empty")
        if not captured_at.strip():
            raise ValueError("captured_at must not be empty")

        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO document_records (
                        context_id,
                        file_path,
                        file_name,
                        file_type,
                        extracted_text,
                        captured_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context_id,
                        str(file_path),
                        stored_file_name,
                        path.suffix.lower(),
                        extracted_text,
                        captured_at,
                    ),
                )
                source_id = int(cursor.lastrowid)
                connection.execute("UPDATE document_records SET stored_file_path=? WHERE id=?",
                                   (stored_file_path, source_id))
                if activity_record_id is not None:
                    connection.execute("INSERT INTO record_document_sources VALUES (?, ?)",
                                       (activity_record_id, source_id))
                return source_id
        finally:
            connection.close()

    def get_recent_document_records(
        self,
        limit: int = 50,
    ) -> list[DocumentRecord]:
        """Return recently saved documents."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    context_id,
                    file_path,
                    file_name,
                    file_type,
                    extracted_text,
                    captured_at
                FROM document_records
                ORDER BY captured_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return [
            DocumentRecord(
                id=row["id"],
                context_id=row["context_id"],
                file_path=row["file_path"],
                file_name=row["file_name"],
                file_type=row["file_type"],
                extracted_text=row["extracted_text"],
                captured_at=row["captured_at"],
            )
            for row in rows
        ]

    def save_document_chunks(
        self,
        document_id: int,
        chunks: list[str],
    ) -> list[str]:
        """Save text chunks linked to an existing document and activity."""
        if isinstance(document_id, bool) or not isinstance(document_id, int):
            raise TypeError("document_id must be an integer")

        if document_id < 1:
            raise ValueError("document_id must be positive")

        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list")

        for chunk in chunks:
            if not isinstance(chunk, str):
                raise TypeError("every chunk must be a string")

            if not chunk.strip():
                raise ValueError("chunks must not contain empty text")

            if len(chunk) > MAX_CHUNK_TEXT_LENGTH:
                raise ValueError(
                    f"chunk text must not exceed "
                    f"{MAX_CHUNK_TEXT_LENGTH} characters"
                )

        connection = self._connect()

        try:
            with connection:
                document = connection.execute(
                    """
                    SELECT id, context_id
                    FROM document_records
                    WHERE id = ?
                    """,
                    (document_id,),
                ).fetchone()

                if document is None:
                    raise ValueError("document does not exist")

                context_id = document["context_id"]

                if context_id is None:
                    raise ValueError(
                        "document must be linked to an activity record"
                    )

                connection.execute(
                    """
                    DELETE FROM document_chunks
                    WHERE document_id = ?
                    """,
                    (document_id,),
                )

                chunk_ids = []

                for chunk_index, chunk_text in enumerate(chunks):
                    chunk_id = str(uuid.uuid4())

                    connection.execute(
                        """
                        INSERT INTO document_chunks (
                            id,
                            document_id,
                            context_id,
                            chunk_index,
                            text,
                            semantic_data_id
                        )
                        VALUES (?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            chunk_id,
                            document_id,
                            context_id,
                            chunk_index,
                            chunk_text,
                        ),
                    )

                    chunk_ids.append(chunk_id)

                return chunk_ids

        finally:
            connection.close()

    def get_document_chunks(
        self,
        document_id: int,
    ) -> list[dict]:
        """Return document chunks in their original order."""
        if isinstance(document_id, bool) or not isinstance(document_id, int):
            raise TypeError("document_id must be an integer")

        if document_id < 1:
            raise ValueError("document_id must be positive")

        connection = self._connect()

        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    document_id,
                    context_id,
                    chunk_index,
                    text,
                    semantic_data_id
                FROM document_chunks
                WHERE document_id = ?
                ORDER BY chunk_index ASC
                """,
                (document_id,),
            ).fetchall()

            return [dict(row) for row in rows]

        finally:
            connection.close()

    def save_search_source_from_models(
        self,
        context_id: int | None,
        source_metadata: SourceMetadata,
        chunks: list[DocumentChunk],
        document_id: int | None = None,
        browser_source_id: int | None = None,
        embeddings: list[list[float]] | None = None,
        model_name: str = "intfloat/multilingual-e5-small",
    ) -> int:
        """Save a search source and its chunks atomically.

        Document sources must reference an activity record. Browser sources may
        be indexed without an activity record because browser collection is
        independent of active-window tracking. Re-indexing replaces the
        previous chunks and their embeddings in the same transaction.
        """
        if context_id is not None:
            if isinstance(context_id, bool) or not isinstance(context_id, int):
                raise TypeError("context_id must be an integer or None")
            if context_id < 1:
                raise ValueError("context_id must be positive")

        if not isinstance(source_metadata, SourceMetadata):
            raise TypeError("source_metadata must be SourceMetadata")
        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list")

        if source_metadata.kind == "document":
            if context_id is None:
                raise ValueError("document source requires context_id")
            if document_id is None or browser_source_id is not None:
                raise ValueError("document source requires document_id only")
            if (
                source_metadata.document is None
                or source_metadata.browser is not None
            ):
                raise ValueError("invalid document source metadata")
            source_id_column = "document_id"
            source_record_id = document_id
        elif source_metadata.kind == "web":
            if browser_source_id is None or document_id is not None:
                raise ValueError("web source requires browser_source_id only")
            if (
                source_metadata.browser is None
                or source_metadata.document is not None
            ):
                raise ValueError("invalid web source metadata")
            source_id_column = "browser_source_id"
            source_record_id = browser_source_id
        else:
            raise ValueError("unsupported search source kind")

        if isinstance(source_record_id, bool) or not isinstance(
            source_record_id, int
        ):
            raise TypeError("source record ID must be an integer")
        if source_record_id < 1:
            raise ValueError("source record ID must be positive")

        expected_context_id = str(context_id) if context_id is not None else None
        seen_ids: set[str] = set()
        seen_indexes: set[int] = set()

        for chunk in chunks:
            if not isinstance(chunk, DocumentChunk):
                raise TypeError("each chunk must be DocumentChunk")
            if chunk.context_id != expected_context_id:
                raise ValueError("chunk belongs to another activity")
            if chunk.source != source_metadata:
                raise ValueError("chunk source metadata does not match")
            if not isinstance(chunk.id, str) or not chunk.id.strip():
                raise ValueError("chunk ID must not be empty")
            if chunk.id in seen_ids:
                raise ValueError("duplicate chunk ID")
            seen_ids.add(chunk.id)
            if (
                isinstance(chunk.chunk_index, bool)
                or not isinstance(chunk.chunk_index, int)
                or chunk.chunk_index < 0
            ):
                raise ValueError("invalid chunk index")
            if chunk.chunk_index in seen_indexes:
                raise ValueError("duplicate chunk index")
            seen_indexes.add(chunk.chunk_index)
            if (
                not isinstance(chunk.text, str)
                or not chunk.text.strip()
                or len(chunk.text) > MAX_CHUNK_TEXT_LENGTH
            ):
                raise ValueError("invalid chunk text")
            if chunk.semantic_data_id is not None and (
                not isinstance(chunk.semantic_data_id, str)
                or not chunk.semantic_data_id.strip()
            ):
                raise ValueError("invalid semantic_data_id")

        if embeddings is not None:
            if not isinstance(embeddings, list):
                raise TypeError("embeddings must be a list")
            if len(embeddings) != len(chunks):
                raise ValueError("embedding count must match chunk count")
            if not isinstance(model_name, str) or not model_name.strip():
                raise ValueError("model_name must not be empty")
            for vector in embeddings:
                if not isinstance(vector, list):
                    raise TypeError("each embedding must be a list")
                if len(vector) != 384:
                    raise ValueError("embedding dimension must be 384")
                for value in vector:
                    if isinstance(value, bool) or not isinstance(
                        value, (int, float)
                    ):
                        raise TypeError("embedding values must be numeric")
                    if not math.isfinite(value):
                        raise ValueError("embedding values must be finite")

        metadata_json = json.dumps(asdict(source_metadata), ensure_ascii=False)
        connection = self._connect()
        try:
            with connection:
                if context_id is not None:
                    activity = connection.execute(
                        "SELECT id FROM activity_records WHERE id = ?",
                        (context_id,),
                    ).fetchone()
                    if activity is None:
                        raise ValueError("activity record does not exist")

                if source_metadata.kind == "document":
                    source_record = connection.execute(
                        """
                        SELECT id, context_id
                        FROM document_records
                        WHERE id = ?
                        """,
                        (source_record_id,),
                    ).fetchone()
                    if source_record is None:
                        raise ValueError("document record does not exist")
                    if source_record["context_id"] != context_id:
                        raise ValueError("document belongs to another activity")
                else:
                    source_record = connection.execute(
                        """
                        SELECT id, browser, url, page_title
                        FROM browser_source_records
                        WHERE id = ?
                        """,
                        (source_record_id,),
                    ).fetchone()
                    if source_record is None:
                        raise ValueError("browser source record does not exist")
                    browser = source_metadata.browser
                    assert browser is not None
                    if (
                        source_record["browser"] != browser.browser
                        or source_record["url"] != browser.url
                        or source_record["page_title"] != browser.page_title
                    ):
                        raise ValueError("browser source metadata does not match")

                existing = connection.execute(
                    f"SELECT id FROM search_sources WHERE {source_id_column} = ?",
                    (source_record_id,),
                ).fetchone()

                if existing is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO search_sources (
                            source_kind, document_id, browser_source_id,
                            context_id, captured_at, content_truncated,
                            metadata_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            source_metadata.kind,
                            document_id,
                            browser_source_id,
                            context_id,
                            source_metadata.captured_at,
                            int(source_metadata.content_truncated),
                            metadata_json,
                        ),
                    )
                    search_source_id = int(cursor.lastrowid)
                else:
                    search_source_id = int(existing["id"])
                    connection.execute(
                        """
                        UPDATE search_sources
                        SET context_id = ?, captured_at = ?,
                            content_truncated = ?, metadata_json = ?
                        WHERE id = ?
                        """,
                        (
                            context_id,
                            source_metadata.captured_at,
                            int(source_metadata.content_truncated),
                            metadata_json,
                            search_source_id,
                        ),
                    )
                    connection.execute(
                        "DELETE FROM search_chunks WHERE search_source_id = ?",
                        (search_source_id,),
                    )

                for index, chunk in enumerate(chunks):
                    semantic_data_id = chunk.semantic_data_id
                    vector = None
                    if embeddings is not None:
                        semantic_data_id = str(uuid.uuid4())
                        vector = [float(value) for value in embeddings[index]]

                    connection.execute(
                        """
                        INSERT INTO search_chunks (
                            id, search_source_id, chunk_index, text,
                            semantic_data_id
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            chunk.id,
                            search_source_id,
                            chunk.chunk_index,
                            chunk.text,
                            semantic_data_id,
                        ),
                    )
                    if vector is not None:
                        connection.execute(
                            """
                            INSERT INTO semantic_embeddings (
                                semantic_data_id, chunk_id, model_name,
                                dimension, vector_json
                            )
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                semantic_data_id,
                                chunk.id,
                                model_name,
                                len(vector),
                                json.dumps(vector),
                            ),
                        )

                return search_source_id
        finally:
            connection.close()


    @staticmethod
    def _search_instant(value: str) -> datetime:
        """Parse an ISO-8601 timestamp as an aware UTC instant."""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return parsed.astimezone(timezone.utc)

    def search_records(
        self,
        *,
        keyword: str = "",
        process_name: str = "",
        source_type: str = "all",
        active_from: str | None = None,
        active_before: str | None = None,
        sort: str = "recent",
        limit: int = 20,
        privacy_policy=None,
    ) -> tuple[list[ContextRecord], bool]:
        """Search saved activity and browser metadata without returning content."""
        if source_type not in {"all", "web", "document", "pdf", "docx"}:
            raise ValueError("unsupported source_type")
        if sort not in {"recent", "oldest"}:
            raise ValueError("unsupported sort")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 20
        ):
            raise ValueError("limit must be between 1 and 20")

        lower = self._search_instant(active_from) if active_from is not None else None
        upper = (
            self._search_instant(active_before)
            if active_before is not None
            else None
        )
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError("active_from must be earlier than active_before")

        normalized_keyword = keyword.casefold()
        normalized_process = process_name.casefold()
        connection = self._connect()
        results: list[tuple[ContextRecord, datetime]] = []
        try:
            # Pick the latest document for each activity so one activity ID never
            # appears more than once in the ContextRecord response.
            if source_type in {"all", "document", "pdf", "docx"}:
                rows = connection.execute(
                    """
                    SELECT
                        a.id, a.application, a.process_name, a.window_title,
                        a.started_at, a.ended_at, a.active_duration_ms,
                        d.file_path, d.file_type
                    FROM activity_records AS a
                    LEFT JOIN document_records AS d
                      ON d.id = (
                        SELECT d2.id
                        FROM document_records AS d2
                        WHERE d2.context_id = a.id
                        ORDER BY d2.captured_at DESC, d2.id DESC
                        LIMIT 1
                      )
                    ORDER BY a.id ASC
                    """
                ).fetchall()

                for row in rows:
                    file_type = (row["file_type"] or "").lower().lstrip(".")
                    has_document = (
                        file_type in {"pdf", "docx"} and bool(row["file_path"])
                    )
                    if source_type in {"document", "pdf", "docx"} and not has_document:
                        continue
                    if source_type in {"pdf", "docx"} and file_type != source_type:
                        continue

                    application = row["application"]
                    process = row["process_name"]
                    if (
                        privacy_policy is not None
                        and privacy_policy.is_blocked(application, process)
                    ):
                        continue
                    title = row["window_title"]
                    if privacy_policy is not None:
                        title = privacy_policy.sanitize_title(title)
                    if normalized_process and process.casefold() != normalized_process:
                        continue
                    if (
                        normalized_keyword
                        and normalized_keyword not in title.casefold()
                    ):
                        continue

                    instant = self._search_instant(row["ended_at"])
                    if lower is not None and instant < lower:
                        continue
                    if upper is not None and instant >= upper:
                        continue

                    document = (
                        LocalDocument(
                            file_path=row["file_path"],
                            file_type=file_type,
                        )
                        if has_document
                        else None
                    )
                    record = ContextRecord(
                        id=str(row["id"]),
                        application=application,
                        process_name=process,
                        window_title=title,
                        started_at=row["started_at"],
                        last_active_at=row["ended_at"],
                        active_duration_ms=row["active_duration_ms"],
                        foreground_count=1,
                        browser=None,
                        document=document,
                    )
                    results.append((record, instant))

            # Browser capture is independent from active-window tracking in Phase 10.
            # Represent each saved browser page as a metadata-only ContextRecord.
            if source_type in {"all", "web"}:
                rows = connection.execute(
                    """
                    SELECT
                        b.id, b.browser, b.url, b.page_title, b.captured_at,
                        s.metadata_json
                    FROM browser_source_records AS b
                    LEFT JOIN search_sources AS s
                      ON s.browser_source_id = b.id
                    ORDER BY b.id ASC
                    """
                ).fetchall()

                for row in rows:
                    url = row["url"]
                    if (
                        not isinstance(url, str)
                        or not url.lower().startswith(("http://", "https://"))
                    ):
                        continue
                    browser_name = row["browser"]
                    application = (
                        "Google Chrome" if browser_name == "chrome"
                        else "Microsoft Edge"
                    )
                    process = "chrome.exe" if browser_name == "chrome" else "msedge.exe"
                    if (
                        privacy_policy is not None
                        and privacy_policy.is_blocked(application, process)
                    ):
                        continue

                    metadata = {}
                    if row["metadata_json"]:
                        try:
                            metadata = json.loads(row["metadata_json"])
                        except (TypeError, ValueError):
                            metadata = {}
                    title = metadata.get("window_title") or row["page_title"]
                    if privacy_policy is not None:
                        title = privacy_policy.sanitize_title(title)
                    page_title = row["page_title"]
                    if privacy_policy is not None:
                        page_title = privacy_policy.sanitize_title(page_title)

                    if normalized_process and process.casefold() != normalized_process:
                        continue
                    if normalized_keyword and normalized_keyword not in (
                        title.casefold() + "\n" + page_title.casefold()
                    ):
                        continue

                    instant = self._search_instant(row["captured_at"])
                    if lower is not None and instant < lower:
                        continue
                    if upper is not None and instant >= upper:
                        continue

                    record = ContextRecord(
                        id=f"web-{row['id']}",
                        application=application,
                        process_name=process,
                        window_title=title,
                        started_at=row["captured_at"],
                        last_active_at=row["captured_at"],
                        active_duration_ms=0,
                        foreground_count=1,
                        browser=BrowserPage(
                            browser=browser_name,
                            page_title=page_title,
                            url=url,
                        ),
                        document=None,
                    )
                    results.append((record, instant))
        finally:
            connection.close()

        # Stable tie-break: ID ascending even when timestamps are equal.
        results.sort(key=lambda item: item[0].id)
        results.sort(
            key=lambda item: item[1],
            reverse=(sort == "recent"),
        )
        has_more = len(results) > limit
        return [record for record, _ in results[:limit]], has_more

    def get_search_chunks(
        self,
        search_source_id: int,
    ) -> list[dict]:
        """Return search chunks in their original order."""
        if (
            isinstance(search_source_id, bool)
            or not isinstance(search_source_id, int)
        ):
            raise TypeError("search_source_id must be an integer")

        if search_source_id < 1:
            raise ValueError("search_source_id must be positive")

        connection = self._connect()

        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    search_source_id,
                    chunk_index,
                    text,
                    semantic_data_id
                FROM search_chunks
                WHERE search_source_id = ?
                ORDER BY chunk_index ASC
                """,
                (search_source_id,),
            ).fetchall()

            return [dict(row) for row in rows]

        finally:
            connection.close()

    def save_semantic_embedding(
        self,
        chunk_id: str,
        vector: list[float],
        model_name: str = "intfloat/multilingual-e5-small",
    ) -> str:
        """Save an embedding vector for an existing search chunk."""

        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("chunk_id must not be empty")

        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must not be empty")

        if not isinstance(vector, list):
            raise TypeError("vector must be a list")

        if len(vector) != 384:
            raise ValueError("embedding dimension must be 384")

        values = []

        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("embedding values must be numeric")

            if not math.isfinite(value):
                raise ValueError("embedding values must be finite")

            values.append(float(value))

        semantic_data_id = str(uuid.uuid4())
        vector_json = json.dumps(values)

        connection = self._connect()

        try:
            with connection:
                chunk = connection.execute(
                    "SELECT id FROM search_chunks WHERE id = ?",
                    (chunk_id,),
                ).fetchone()

                if chunk is None:
                    raise ValueError("search chunk does not exist")

                existing = connection.execute(
                    """
                    SELECT semantic_data_id
                    FROM semantic_embeddings
                    WHERE chunk_id = ?
                    """,
                    (chunk_id,),
                ).fetchone()

                if existing is not None:
                    semantic_data_id = existing["semantic_data_id"]

                    connection.execute(
                        """
                        UPDATE semantic_embeddings
                        SET
                            model_name = ?,
                            dimension = ?,
                            vector_json = ?
                        WHERE chunk_id = ?
                        """,
                        (
                            model_name,
                            len(values),
                            vector_json,
                            chunk_id,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO semantic_embeddings (
                            semantic_data_id,
                            chunk_id,
                            model_name,
                            dimension,
                            vector_json
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            semantic_data_id,
                            chunk_id,
                            model_name,
                            len(values),
                            vector_json,
                        ),
                    )

                connection.execute(
                    """
                    UPDATE search_chunks
                    SET semantic_data_id = ?
                    WHERE id = ?
                    """,
                    (semantic_data_id, chunk_id),
                )

            return semantic_data_id

        finally:
            connection.close()


    def search_semantic_chunks(
        self,
        query_vector: list[float],
        *,
        model_name: str = "intfloat/multilingual-e5-small",
        process_name: str = "",
        source_type: str = "all",
        active_from: str | None = None,
        active_before: str | None = None,
        sort: str = "relevance",
        limit: int = 20,
        privacy_policy=None,
    ) -> tuple[list[dict], bool]:
        """Rank indexed passages by cosine similarity and restore source metadata.

        Cosine similarity is computed from stored vectors. Filtering is applied
        before ranking; tie-breaking is
        deterministic. Only metadata snapshots and bounded text previews leave
        this method, never full source documents.
        """
        if not isinstance(query_vector, list) or len(query_vector) != 384:
            raise ValueError("query_vector must contain 384 values")
        query_values = []
        for value in query_vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("query vector values must be numeric")
            if not math.isfinite(value):
                raise ValueError("query vector values must be finite")
            query_values.append(float(value))
        if source_type not in {"all", "web", "document", "pdf", "docx"}:
            raise ValueError("unsupported source_type")
        if sort not in {"relevance", "recent"}:
            raise ValueError("unsupported sort")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        normalized_process = process_name.strip().casefold()
        lower = self._search_instant(active_from) if active_from is not None else None
        upper = self._search_instant(active_before) if active_before is not None else None
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError("active_from must be earlier than active_before")

        connection = self._connect()
        ranked: list[tuple[dict, float, datetime]] = []
        try:
            rows = connection.execute(
                """
                SELECT
                    c.id AS chunk_id,
                    c.chunk_index,
                    c.text AS chunk_text,
                    ss.source_kind,
                    ss.context_id,
                    ss.document_id,
                    ss.browser_source_id,
                    ss.captured_at AS source_captured_at,
                    ss.content_truncated,
                    ss.metadata_json,
                    e.model_name,
                    e.dimension,
                    e.vector_json,
                    a.active_duration_ms
                FROM search_chunks AS c
                JOIN search_sources AS ss ON ss.id = c.search_source_id
                JOIN semantic_embeddings AS e ON e.chunk_id = c.id
                LEFT JOIN activity_records AS a ON a.id = ss.context_id
                WHERE e.model_name = ? AND e.dimension = 384
                """,
                (model_name,),
            ).fetchall()

            for row in rows:
                try:
                    metadata = json.loads(row["metadata_json"] or "{}")
                    vector = json.loads(row["vector_json"])
                    if not isinstance(metadata, dict) or not isinstance(vector, list):
                        continue
                    if len(vector) != 384:
                        continue
                    vector_values = [float(value) for value in vector]
                    if not all(math.isfinite(value) for value in vector_values):
                        continue
                    query_norm = math.sqrt(sum(value * value for value in query_values))
                    vector_norm = math.sqrt(sum(value * value for value in vector_values))
                    if query_norm == 0 or vector_norm == 0:
                        continue
                    score = sum(
                        query_values[index] * vector_values[index]
                        for index in range(384)
                    ) / (query_norm * vector_norm)
                    if not math.isfinite(score) or score < MIN_SEMANTIC_SIMILARITY:
                        continue
                    kind = row["source_kind"]
                    if source_type == "web" and kind != "web":
                        continue
                    if source_type in {"document", "pdf", "docx"} and kind != "document":
                        continue

                    document_data = metadata.get("document")
                    browser_data = metadata.get("browser")
                    if kind == "document":
                        if not isinstance(document_data, dict) or browser_data is not None:
                            continue
                        file_type = str(document_data.get("file_type", "")).lower().lstrip(".")
                        if file_type not in {"pdf", "docx"}:
                            continue
                        if source_type in {"pdf", "docx"} and file_type != source_type:
                            continue
                        document = LocalDocument(
                            file_path=str(document_data.get("file_path", "")),
                            file_type=file_type,
                        )
                        browser = None
                    elif kind == "web":
                        if not isinstance(browser_data, dict) or document_data is not None:
                            continue
                        browser_name = browser_data.get("browser")
                        url = browser_data.get("url")
                        page_title = browser_data.get("page_title")
                        if browser_name not in {"chrome", "edge"}:
                            continue
                        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
                            continue
                        if not isinstance(page_title, str):
                            continue
                        browser = BrowserPage(
                            browser=browser_name,
                            page_title=page_title,
                            url=url,
                        )
                        document = None
                    else:
                        continue

                    application = str(metadata.get("application", ""))
                    process = str(metadata.get("process_name", ""))
                    title = str(metadata.get("window_title", ""))
                    if not application or not process:
                        continue
                    if privacy_policy is not None:
                        if privacy_policy.is_blocked(application, process):
                            continue
                        if privacy_policy.contains_sensitive_data(row["chunk_text"]):
                            continue
                        title = privacy_policy.sanitize_title(title)
                        if browser is not None:
                            try:
                                safe_url = privacy_policy.sanitize_browser_url(browser.url)
                            except ValueError:
                                continue
                            browser = BrowserPage(
                                browser=browser.browser,
                                page_title=privacy_policy.sanitize_title(browser.page_title),
                                url=safe_url,
                            )
                    if normalized_process and process.casefold() != normalized_process:
                        continue

                    started_at = str(metadata.get("started_at") or row["source_captured_at"])
                    last_active_at = str(metadata.get("last_active_at") or row["source_captured_at"])
                    instant = self._search_instant(last_active_at)
                    if lower is not None and instant < lower:
                        continue
                    if upper is not None and instant >= upper:
                        continue
                    context_id = row["context_id"]
                    record_id = (
                        f"web-{row['browser_source_id']}"
                        if kind == "web" and context_id is None
                        else str(context_id)
                    )
                    if kind == "document" and context_id is None:
                        continue
                    record = ContextRecord(
                        id=record_id,
                        application=application,
                        process_name=process,
                        window_title=title,
                        started_at=started_at,
                        last_active_at=last_active_at,
                        active_duration_ms=int(row["active_duration_ms"] or 0),
                        foreground_count=1,
                        browser=browser,
                        document=document,
                    )
                    hit = {
                        "chunk_id": row["chunk_id"],
                        "chunk_index": int(row["chunk_index"]),
                        "preview": str(row["chunk_text"])[:SEMANTIC_PREVIEW_LENGTH],
                        "similarity": max(-1.0, min(1.0, score)),
                        "record": record,
                        "content_truncated": bool(row["content_truncated"]),
                        "context_id": str(context_id) if context_id is not None else None,
                        "source": SourceMetadata(
                            kind, application, process, title, started_at, last_active_at,
                            row["source_captured_at"], bool(row["content_truncated"]), browser, document,
                        ),
                    }
                    ranked.append((hit, score, instant))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    # A malformed legacy snapshot must not break other search hits.
                    continue
        finally:
            connection.close()

        if sort == "recent":
            ranked.sort(key=lambda item: item[0]["chunk_id"])
            ranked.sort(key=lambda item: item[2], reverse=True)
        else:
            ranked.sort(key=lambda item: item[0]["chunk_id"])
            ranked.sort(key=lambda item: item[1], reverse=True)
        has_more = len(ranked) > limit
        return [item[0] for item in ranked[:limit]], has_more

    def get_search_chunk_text(self, chunk_id: str) -> str | None:
        """Return the full text of an indexed search chunk.

        This method is intended for internal RAG evidence assembly.
        Public semantic-search responses continue to expose bounded previews.
        """
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("chunk_id must not be empty")

        if len(chunk_id) > 128:
            raise ValueError("chunk_id is too long")

        connection = self._connect()

        try:
            row = connection.execute(
                """
                SELECT c.text
                FROM search_chunks AS c
                JOIN search_sources AS s
                    ON s.id = c.search_source_id
                WHERE c.id = ?
                """,
                (chunk_id,),
            ).fetchone()

            if row is None:
                return None

            return str(row["text"])

        finally:
            connection.close()

    def get_semantic_embedding(
        self,
        chunk_id: str,
    ) -> dict | None:
        """Return the stored embedding for a search chunk."""

        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("chunk_id must not be empty")

        connection = self._connect()

        try:
            row = connection.execute(
                """
                SELECT
                    semantic_data_id,
                    chunk_id,
                    model_name,
                    dimension,
                    vector_json
                FROM semantic_embeddings
                WHERE chunk_id = ?
                """,
                (chunk_id,),
            ).fetchone()

            if row is None:
                return None

            result = dict(row)
            result["vector"] = json.loads(result.pop("vector_json"))

            return result

        finally:
            connection.close()
