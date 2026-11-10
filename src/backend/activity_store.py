
"""SQLite persistence for activity records."""

import json
import math
import sqlite3
import uuid
from dataclasses import asdict
from pathlib import Path

from shared.activity import (
    ActiveWindow,
    ActivityRecord,
    BrowserContentRecord,
    BrowserSourceRecord,
    ClipboardRecord,
    DocumentRecord,
)
from shared.search_data import (
    MAX_CHUNK_TEXT_LENGTH,
    DocumentChunk,
    SourceMetadata,
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

    def get_record(self, record_id: int) -> ActivityRecord | None:
        """Return one activity record by ID, or None if it does not exist."""
        if isinstance(record_id, bool) or not isinstance(record_id, int):
            raise TypeError("record_id must be an integer")

        if record_id < 1:
            raise ValueError("record_id must be positive")

        connection = self._connect()
        try:
            row = connection.execute(
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
                WHERE id = ?
                """,
                (record_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return ActivityRecord(
            id=row["id"],
            application=row["application"],
            process_name=row["process_name"],
            process_id=row["process_id"],
            window_title=row["window_title"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            active_duration_ms=row["active_duration_ms"],
        )

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

    def save_document_record(
        self,
        file_path: str | Path,
        extracted_text: str,
        captured_at: str,
        file_name: str | None = None,
        context_id: int | None = None,
    ) -> int:
        """Save document metadata and extracted text linked to an activity."""
        if context_id is not None:
            if isinstance(context_id, bool) or not isinstance(context_id, int):
                raise TypeError("context_id must be an integer")
            if context_id < 1:
                raise ValueError("context_id must be positive")

        path = Path(file_path)
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
                        str(path.resolve()),
                        stored_file_name,
                        path.suffix.lower(),
                        extracted_text,
                        captured_at,
                    ),
                )
                return int(cursor.lastrowid)
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
        context_id: int,
        source_metadata: SourceMetadata,
        chunks: list[DocumentChunk],
        document_id: int | None = None,
        browser_source_id: int | None = None,
        embeddings: list[list[float]] | None = None,
        model_name: str = "intfloat/multilingual-e5-small",
    ) -> int:
        """Save a search source and its chunks atomically."""
        if isinstance(context_id, bool) or not isinstance(context_id, int):
            raise TypeError("context_id must be an integer")
        if context_id < 1:
            raise ValueError("context_id must be positive")

        if not isinstance(source_metadata, SourceMetadata):
            raise TypeError("source_metadata must be SourceMetadata")

        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list")

        if source_metadata.kind == "document":
            if document_id is None or browser_source_id is not None:
                raise ValueError(
                    "document source requires document_id only"
                )
            source_id_column = "document_id"
            source_record_id = document_id

            if source_metadata.document is None or source_metadata.browser is not None:
                raise ValueError("invalid document source metadata")

        elif source_metadata.kind == "web":
            if browser_source_id is None or document_id is not None:
                raise ValueError(
                    "web source requires browser_source_id only"
                )
            source_id_column = "browser_source_id"
            source_record_id = browser_source_id

            if source_metadata.browser is None or source_metadata.document is not None:
                raise ValueError("invalid web source metadata")

        else:
            raise ValueError("unsupported search source kind")

        if (
            isinstance(source_record_id, bool)
            or not isinstance(source_record_id, int)
        ):
            raise TypeError("source record ID must be an integer")

        if source_record_id < 1:
            raise ValueError("source record ID must be positive")

        seen_ids: set[str] = set()
        seen_indexes: set[int] = set()

        for chunk in chunks:
            if not isinstance(chunk, DocumentChunk):
                raise TypeError("each chunk must be DocumentChunk")

            if chunk.context_id != str(context_id):
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
                    raise ValueError(
                        "embedding count must match chunk count"
                    )

                if not isinstance(model_name, str) or not model_name.strip():
                    raise ValueError("model_name must not be empty")

                for vector in embeddings:
                    if not isinstance(vector, list):
                        raise TypeError("each embedding must be a list")

                    if len(vector) != 384:
                        raise ValueError(
                            "embedding dimension must be 384"
                        )

                    for value in vector:
                        if (
                            isinstance(value, bool)
                            or not isinstance(value, (int, float))
                        ):
                            raise TypeError(
                                "embedding values must be numeric"
                            )

                        if not math.isfinite(value):
                            raise ValueError(
                                "embedding values must be finite"
                            )

        metadata_json = json.dumps(
            asdict(source_metadata),
            ensure_ascii=False,
        )

        connection = self._connect()

        try:
            with connection:
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
                        raise ValueError(
                            "document belongs to another activity"
                        )

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
                        raise ValueError(
                            "browser source record does not exist"
                        )

                    browser = source_metadata.browser
                    assert browser is not None

                    if (
                        source_record["browser"] != browser.browser
                        or source_record["url"] != browser.url
                        or source_record["page_title"] != browser.page_title
                    ):
                        raise ValueError(
                            "browser source metadata does not match"
                        )

                existing = connection.execute(
                    f"""
                    SELECT id
                    FROM search_sources
                    WHERE {source_id_column} = ?
                    """,
                    (source_record_id,),
                ).fetchone()

                if existing is None:
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
                        SET
                            context_id = ?,
                            captured_at = ?,
                            content_truncated = ?,
                            metadata_json = ?
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
                        """
                        DELETE FROM search_chunks
                        WHERE search_source_id = ?
                        """,
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
                            id,
                            search_source_id,
                            chunk_index,
                            text,
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
                                chunk.id,
                                model_name,
                                len(vector),
                                json.dumps(vector),
                            ),
                        )

                return search_source_id

        finally:
            connection.close()

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