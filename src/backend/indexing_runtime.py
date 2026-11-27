"""수집과 모델 실행을 분리하고 실제 저장 자료만 새 검색 API의 색인으로 전달한다."""

from backend.embedding import EmbeddingService
from backend.search_indexer import SearchIndexer
from backend.search_processor import create_document_chunks
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.search_data import SourceMetadata


def index_collected_source(store, embedding, policy, metadata, text, context_id,
                           *, document_id=None, browser_source_id=None):
    """모델 로드 전 수집은 텍스트 색인까지만 저장하고 가짜 임베딩으로 성공시키지 않는다."""
    if policy.collection_paused or policy.is_blocked(metadata.application, metadata.process_name):
        raise ValueError("Collection is restricted")
    if isinstance(embedding, EmbeddingService):
        chunks = create_document_chunks(text, context_id, metadata, max_chunk_length=1000,
                                         privacy_policy=policy)
        if not chunks:
            return None
        return store.save_search_source_from_models(
            context_id=context_id, source_metadata=metadata, chunks=chunks,
            document_id=document_id, browser_source_id=browser_source_id,
        )
    return SearchIndexer(store, embedding, policy).index_source(
        context_id, metadata, text, document_id, browser_source_id,
    )


def prepare_search_index(store, embedding, policy):
    """누락된 벡터가 있는 실제 원본만 모델의 tokenizer로 다시 나눠 색인한다."""
    if policy.collection_paused:
        return
    for kind, source_id, context_id in store.pending_index_materials(embedding.model_name):
        record = store.get_record(context_id) if context_id else None
        if kind == "document":
            source = store.get_document_record(source_id)
            if source is None or record is None:
                continue
            text = source.extracted_text
            location = {"document": LocalDocument(source.original_file_path or source.file_path, source.file_type[1:]),
                        "original_file_path": source.original_file_path}
            captured = source.captured_at
        else:
            source = store.get_browser_source_record(source_id)
            body = store.get_browser_content_record(source_id)
            if source is None or body is None:
                continue
            text = body.content_text
            location = {"browser": BrowserPage(source.browser, source.page_title, source.url)}
            captured = body.captured_at
        if policy.contains_sensitive_data(text):
            continue
        browser = location.get("browser")
        application = record.application if record else (
            "Google Chrome" if source.browser == "chrome" else "Microsoft Edge")
        process = record.process_name if record else (
            "chrome.exe" if source.browser == "chrome" else "msedge.exe")
        if policy.is_blocked(application, process):
            continue
        metadata = SourceMetadata(
            kind, application, process, record.window_title if record else source.page_title,
            record.started_at if record else source.captured_at,
            record.ended_at if record else source.captured_at, captured,
            store.browser_content_truncated(source_id) if browser else False, **location,
        )
        # 조회 시점에도 실제 원문으로 생성한다. 이전 벡터를 다른 청크 ID에 재사용하지 않는다.
        SearchIndexer(store, embedding, policy).index_source(
            context_id, metadata, text,
            document_id=source_id if kind == "document" else None,
            browser_source_id=source_id if kind == "web" else None,
        )
