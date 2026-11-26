"""Delete activity and source records with their dependent indexed data."""


class ActivityDeletionMixin:
    """ActivityStore deletion operations that preserve database consistency."""

    @staticmethod
    def _validate_record_id(record_id: int, name: str) -> None:
        """Validate a positive integer database identifier."""
        if isinstance(record_id, bool) or not isinstance(record_id, int):
            raise TypeError(f"{name} must be an integer")
        if record_id < 1:
            raise ValueError(f"{name} must be positive")

    def delete_document_record(self, document_id: int) -> bool:
        """Delete a document record and its indexed chunks, not its file copy."""
        self._validate_record_id(document_id, "document_id")
        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM document_records WHERE id = ?",
                    (document_id,),
                )
                return cursor.rowcount > 0
        finally:
            connection.close()

    def delete_browser_content_record(self, content_id: int) -> bool:
        """Delete one captured page body while retaining its source URL record."""
        self._validate_record_id(content_id, "content_id")
        connection = self._connect()
        try:
            with connection:
                row = connection.execute(
                    "SELECT browser_source_id FROM browser_content_records WHERE id = ?",
                    (content_id,),
                ).fetchone()
                if row is None:
                    return False
                # The body is indexed separately. Remove its search source and
                # dependent chunks/embeddings too, while retaining the URL row.
                connection.execute(
                    "DELETE FROM search_sources WHERE browser_source_id = ?",
                    (row["browser_source_id"],),
                )
                connection.execute(
                    "DELETE FROM browser_content_records WHERE id = ?",
                    (content_id,),
                )
                return True
        finally:
            connection.close()

    def delete_browser_source_record(self, browser_source_id: int) -> bool:
        """Delete a browser source and all its dependent content/index data."""
        self._validate_record_id(browser_source_id, "browser_source_id")
        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM browser_source_records WHERE id = ?",
                    (browser_source_id,),
                )
                return cursor.rowcount > 0
        finally:
            connection.close()

    def delete_activity_record(self, activity_id: int) -> bool:
        """Delete an activity and its clipboard, document, and search records.

        Documents and semantic chunks cascade through the existing foreign-key
        relationships. Clipboard records use the historical timestamp/app
        relationship, so those are explicitly removed here. Session boundaries
        are recalculated from remaining activities, and empty sessions vanish.
        """
        self._validate_record_id(activity_id, "activity_id")
        connection = self._connect()
        try:
            with connection:
                row = connection.execute(
                    """SELECT application, started_at, session_id
                    FROM activity_records WHERE id = ?""",
                    (activity_id,),
                ).fetchone()
                if row is None:
                    return False

                connection.execute(
                    """DELETE FROM clipboard_records
                    WHERE application = ? AND activity_started_at = ?""",
                    (row["application"], row["started_at"]),
                )
                linked_browser_sources = connection.execute(
                    "SELECT browser_source_id FROM search_sources WHERE context_id = ? "
                    "AND browser_source_id IS NOT NULL",
                    (activity_id,),
                ).fetchall()
                if linked_browser_sources:
                    source_ids = [int(item["browser_source_id"]) for item in linked_browser_sources]
                    placeholders = ",".join("?" for _ in source_ids)
                    connection.execute(
                        f"DELETE FROM browser_source_records WHERE id IN ({placeholders})",
                        source_ids,
                    )
                connection.execute(
                    "DELETE FROM activity_records WHERE id = ?",
                    (activity_id,),
                )

                session_id = row["session_id"]
                if session_id is not None:
                    remaining = connection.execute(
                        """SELECT started_at, ended_at
                        FROM activity_records WHERE session_id = ?""",
                        (session_id,),
                    ).fetchall()
                    if not remaining:
                        connection.execute(
                            "DELETE FROM sessions WHERE id = ?",
                            (session_id,),
                        )
                    else:
                        parsed_starts = [
                            (self._session_timestamp(item["started_at"]), item["started_at"])
                            for item in remaining
                        ]
                        parsed_ends = [
                            (self._session_timestamp(item["ended_at"]), item["ended_at"])
                            for item in remaining
                        ]
                        valid_starts = [item for item in parsed_starts if item[0] is not None]
                        valid_ends = [item for item in parsed_ends if item[0] is not None]
                        if valid_starts and valid_ends:
                            session_start = min(valid_starts, key=lambda item: item[0])[1]
                            session_end = max(valid_ends, key=lambda item: item[0])[1]
                        else:
                            session_start = min(item[1] for item in parsed_starts)
                            session_end = max(item[1] for item in parsed_ends)
                        connection.execute(
                            "UPDATE sessions SET started_at = ?, ended_at = ? WHERE id = ?",
                            (session_start, session_end, session_id),
                        )
                return True
        finally:
            connection.close()

    def delete_all_records(self) -> dict[str, int]:
        """Delete all collected records while preserving tables and indexes."""
        table_order = (
            "semantic_embeddings",
            "search_chunks",
            "search_sources",
            "document_chunks",
            "document_records",
            "browser_content_records",
            "browser_source_records",
            "clipboard_records",
            "activity_records",
            "sessions",
        )
        connection = self._connect()
        try:
            counts: dict[str, int] = {}
            with connection:
                for table in table_order:
                    cursor = connection.execute(f"DELETE FROM {table}")
                    counts[table] = max(0, cursor.rowcount)
            return counts
        finally:
            connection.close()
