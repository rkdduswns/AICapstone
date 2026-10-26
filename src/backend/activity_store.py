
"""SQLite persistence for activity records."""

import sqlite3
from pathlib import Path, PureWindowsPath

from shared.activity import (
    ActiveWindow,
    ActivityRecord,
    BrowserContentRecord,
    BrowserSourceRecord,
    ClipboardRecord,
    DocumentRecord,
)


class ActivityStore:
    """Persist activity, clipboard, browser, and document records."""

    def __init__(self, db_path: str | Path | None = None) -> None:
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
        """Create database tables and indexes if they do not exist."""
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
                    CREATE INDEX IF NOT EXISTS idx_activity_started_at
                    ON activity_records(started_at DESC, id DESC)
                    """
                )

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

                # B: Create a separate table for extracted document text.
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        extracted_text TEXT NOT NULL,
                        captured_at TEXT NOT NULL
                    )
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
        finally:
            connection.close()

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
                cursor = connection.execute(
                    """
                    INSERT INTO activity_records (
                        application,
                        process_name,
                        process_id,
                        window_title,
                        started_at,
                        ended_at,
                        active_duration_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        window.application,
                        window.process_name,
                        window.process_id,
                        window.window_title,
                        started_at,
                        ended_at,
                        active_duration_ms,
                    ),
                )
                return int(cursor.lastrowid)
        finally:
            connection.close()

    def get_recent_records(self, limit: int = 50) -> list[ActivityRecord]:
        """Return recent activity records, newest first."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

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
                ORDER BY julianday(ended_at) DESC, id DESC
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
        return model(**dict(row)) if row is not None else None

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
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM activity_records WHERE id = ?", (record_id,),
            ).fetchone()
        finally:
            connection.close()
        return ActivityRecord(**dict(row)) if row is not None else None

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
                        captured_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(browser_source_id) DO UPDATE SET
                        content_text = excluded.content_text, captured_at = excluded.captured_at
                    """,
                    (browser_source_id, content_text, captured_at),
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

    # C: Save extracted document information and return its database ID.
    def save_document_record(
        self,
        file_path: str | Path,
        extracted_text: str,
        captured_at: str,
        activity_record_id: int | None = None,
    ) -> int:
        """원문 경로·추출 본문을 보존하고 명시한 작업 연결도 함께 저장한다."""
        windows_path = PureWindowsPath(file_path)
        path = windows_path if windows_path.is_absolute() else Path(file_path)

        if not str(file_path).strip():
            raise ValueError("file_path must not be empty")
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
                        file_path,
                        file_name,
                        file_type,
                        extracted_text,
                        captured_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(file_path),
                        path.name,
                        path.suffix.lower(),
                        extracted_text,
                        captured_at,
                    ),
                )
                source_id = int(cursor.lastrowid)
                if activity_record_id is not None:
                    connection.execute("INSERT INTO record_document_sources VALUES (?, ?)",
                                       (activity_record_id, source_id))
                return source_id
        finally:
            connection.close()

    # C: Retrieve recently saved documents, newest first.
    def get_recent_document_records(
        self,
        limit: int = 50,
    ) -> list[DocumentRecord]:
        """Return recently saved document records."""
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    id,
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
                file_path=row["file_path"],
                file_name=row["file_name"],
                file_type=row["file_type"],
                extracted_text=row["extracted_text"],
                captured_at=row["captured_at"],
            )
            for row in rows
        ]
