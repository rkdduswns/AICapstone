
"""활동, 문서, 브라우저 원본의 삭제 기능."""

class ActivityDeletionMixin:
    """ActivityStore에 원본 및 연관 데이터 삭제 기능을 제공한다."""

    @staticmethod
    def _validate_record_id(
        record_id: int,
        name: str,
    ) -> None:
        """DB 레코드 ID가 양의 정수인지 확인한다."""
        if isinstance(record_id, bool) or not isinstance(
            record_id,
            int,
        ):
            raise TypeError(f"{name} must be an integer")

        if record_id < 1:
            raise ValueError(f"{name} must be positive")

    def delete_document_record(
        self,
        document_id: int,
    ) -> bool:
        """문서 원본과 연결된 검색 데이터를 삭제한다.

        외래 키 CASCADE를 통해 다음 데이터도 함께 삭제된다.
        - document_chunks
        - search_sources
        - search_chunks
        - semantic_embeddings

        실제 사용자 파일은 삭제하지 않는다.

        Returns:
            삭제된 문서가 있으면 True, 없으면 False.
        """
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

    def delete_browser_content_record(
        self,
        content_id: int,
    ) -> bool:
        """브라우저 원문 레코드 하나만 삭제한다."""
        self._validate_record_id(content_id, "content_id")

        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM browser_content_records WHERE id = ?",
                    (content_id,),
                )
                return cursor.rowcount > 0
        finally:
            connection.close()

    def delete_browser_source_record(
        self,
        browser_source_id: int,
    ) -> bool:
        """브라우저 원본과 연결된 검색 데이터를 삭제한다.

        외래 키 CASCADE를 통해 다음 데이터도 함께 삭제된다.
        - browser_content_records
        - search_sources
        - search_chunks
        - semantic_embeddings

        Returns:
            삭제된 브라우저 원본이 있으면 True, 없으면 False.
        """
        self._validate_record_id(
            browser_source_id,
            "browser_source_id",
        )

        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    DELETE FROM browser_source_records
                    WHERE id = ?
                    """,
                    (browser_source_id,),
                )
                return cursor.rowcount > 0
        finally:
            connection.close()

    def delete_activity_record(
        self,
        activity_id: int,
    ) -> bool:
        """활동 원본과 해당 활동에 연결된 데이터를 삭제한다.

        외래 키 CASCADE를 통해 연관 데이터도 함께 삭제된다.

        Returns:
            삭제된 활동이 있으면 True, 없으면 False.
        """
        self._validate_record_id(activity_id, "activity_id")

        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    DELETE FROM activity_records
                    WHERE id = ?
                    """,
                    (activity_id,),
                )
                return cursor.rowcount > 0
        finally:
            connection.close()
