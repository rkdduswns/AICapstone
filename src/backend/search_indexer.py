
"""Search indexing pipeline for web and local document sources."""

from backend.embedding import MODEL_NAME, EmbeddingService
from backend.privacy import PrivacyPolicy
from backend.search_processor import (
    create_document_chunks,
    normalize_search_text,
)
from shared.search_data import (
    MAX_CHUNK_TEXT_LENGTH,
    DocumentChunk,
    SourceMetadata,
)


class SearchIndexer:
    """Normalize, chunk, embed, and persist search sources."""

    def __init__(
        self,
        store,
        embedding_service: EmbeddingService | None = None,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> None:
        self.store = store
        self.embedding_service = (
            embedding_service or EmbeddingService()
        )
        self.privacy_policy = privacy_policy or PrivacyPolicy()

    def index_source(
        self,
        context_id: int | None,
        source_metadata: SourceMetadata,
        text: str,
        document_id: int | None = None,
        browser_source_id: int | None = None,
    ) -> int | None:
        """Index one document or web source and return its search source ID."""

        if context_id is not None:
            if isinstance(context_id, bool) or not isinstance(
                context_id, int
            ):
                raise TypeError("context_id must be an integer or None")

            if context_id < 1:
                raise ValueError("context_id must be positive")

        if not isinstance(source_metadata, SourceMetadata):
            raise TypeError(
                "source_metadata must be SourceMetadata"
            )

        if source_metadata.kind == "document" and context_id is None:
            raise ValueError("document source requires context_id")
        if source_metadata.kind == "web" and context_id is not None:
            # Web sources are allowed to remain independent of activity records.
            pass

        # 개인정보 검사는 정규화와 분할보다 먼저 수행한다.
        normalized = normalize_search_text(
            text,
            privacy_policy=self.privacy_policy,
        )

        if not normalized:
            return None

        # 모델의 실제 tokenizer를 이용해 512 토큰 제한에 맞춘다.
        token_parts = self.embedding_service.split_passage(
            normalized,
            privacy_policy=self.privacy_policy,
        )

        chunks: list[DocumentChunk] = []
        seen_texts: set[str] = set()

        # 토큰 분할 결과를 검색 청크로 변환한다.
        for token_part in token_parts:
            partial_chunks = create_document_chunks(
                text=token_part,
                context_id=context_id,
                source_metadata=source_metadata,
                max_chunk_length=MAX_CHUNK_TEXT_LENGTH,
                privacy_policy=self.privacy_policy,
            )

            for chunk in partial_chunks:
                if chunk.text in seen_texts:
                    continue

                seen_texts.add(chunk.text)

                chunks.append(
                    DocumentChunk(
                        id=chunk.id,
                        context_id=chunk.context_id,
                        chunk_index=len(chunks),
                        text=chunk.text,
                        source=chunk.source,
                    )
                )

        if not chunks:
            return None

        # 청크 본문과 동일한 순서로 임베딩을 생성한다.
        embeddings = self.embedding_service.embed_passages(
            [chunk.text for chunk in chunks],
            privacy_policy=self.privacy_policy,
        )

        # 기존 저장 메서드가 청크와 벡터를 하나의 트랜잭션으로 저장한다.
        return self.store.save_search_source_from_models(
            context_id=context_id,
            source_metadata=source_metadata,
            chunks=chunks,
            document_id=document_id,
            browser_source_id=browser_source_id,
            embeddings=embeddings,
            model_name=getattr(
                self.embedding_service,
                "model_name",
                MODEL_NAME,
            ),
        )
