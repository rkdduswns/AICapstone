
"""SQLite persistence for activity records."""

import sqlite3
from pathlib import Path

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
                ORDER BY started_at DESC, id DESC
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
    ) -> int:
        """Save one browser page record and return its database ID."""
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
                return int(cursor.lastrowid)
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
                cursor = connection.execute(
                    """
                    INSERT INTO browser_content_records (
                        browser_source_id,
                        content_text,
                        captured_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (browser_source_id, content_text, captured_at),
                )
                return int(cursor.lastrowid)
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
    ) -> int:
        """Save document metadata and extracted text."""
        path = Path(file_path)

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
                        str(path),
                        path.name,
                        path.suffix.lower(),
                        extracted_text,
                        captured_at,
                    ),
                )
                return int(cursor.lastrowid)
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