"""Local HTTP boundary for health, activity, browser, and document APIs."""

import hmac
import logging
import os
import shutil
import sqlite3
import tempfile
import unicodedata
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path, PureWindowsPath
from typing import Literal

from fastapi import FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.browser_auth import load_or_create_browser_token
from backend.document_extractor import (
    MAX_DOCUMENT_SIZE,
    SUPPORTED_EXTENSIONS,
    extract_document_text,
)
from backend.embedding import EmbeddingService
from backend.ollama_answer_generator import OllamaAnswerGenerator
from backend.privacy import PrivacyPolicy
from backend.rag_service import AnswerGenerator, RAGService
from backend.search_indexer import SearchIndexer
from shared.activity import (
    ACTIVITY_HISTORY_PATH,
    ACTIVITY_PATH,
    BROWSER_CONTENT_PATH,
    BROWSER_SOURCE_PATH,
)
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.protocol import (
    API_VERSION,
    SERVICE_NAME,
    ApiError,
    ErrorResponse,
    HealthResponse,
    HealthStatus,
)
from shared.rag import (
    MAX_RAG_EVIDENCE_COUNT,
    MAX_RAG_QUERY_LENGTH,
    RAGRequest,
    RAGResponse,
)
from shared.records import RECENT_RECORDS_LIMIT, RECENT_RECORDS_PATH
from shared.search import (
    MAX_SEARCH_KEYWORD,
    MAX_SEARCH_PROCESS,
    SEARCH_LIMIT,
    SEARCH_PATH,
    SearchRequest,
    SearchResponse,
    SearchResults,
)
from shared.search_data import SourceMetadata
from shared.semantic_search import (
    MAX_SEMANTIC_QUERY_LENGTH,
    SEMANTIC_SEARCH_LIMIT,
    SEMANTIC_SEARCH_PATH,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchResults,
)
from shared.sessions import (
    ACTIVITY_RECORD_DELETE_PATH,
    ALL_RECORDS_DELETE_PATH,
    BROWSER_CONTENT_DELETE_PATH,
    BROWSER_SOURCE_DELETE_PATH,
    DOCUMENT_RECORD_DELETE_PATH,
    SESSION_DETAIL_PATH,
    SESSION_MATERIALS_PATH,
    SESSIONS_PATH,
)

logger = logging.getLogger(__name__)


class BrowserSourceRequest(BaseModel):
    """Validated data received from a browser extension."""

    browser: Literal["chrome", "edge"]
    url: str = Field(min_length=1, max_length=4096)
    page_title: str = Field(min_length=1, max_length=500)


class BrowserContentRequest(BaseModel):
    """Validated text content received from a browser extension."""

    browser_source_id: int = Field(ge=1)
    content_text: str = Field(min_length=1, max_length=100_000)


class SemanticSearchBody(BaseModel):
    """Natural-language semantic query with optional Phase 11 filters."""

    query: str = Field(min_length=1, max_length=MAX_SEMANTIC_QUERY_LENGTH)
    process_name: str = Field(default="", max_length=MAX_SEARCH_PROCESS)
    source_type: Literal["all", "web", "document", "pdf", "docx"] = "all"
    active_from: str | None = None
    active_before: str | None = None
    sort: Literal["relevance", "recent"] = "relevance"
    limit: int = Field(default=SEMANTIC_SEARCH_LIMIT, ge=1, le=SEMANTIC_SEARCH_LIMIT)

class RAGAnswerBody(BaseModel):
    """Validated request for evidence-grounded answer generation."""

    query: str = Field(min_length=1, max_length=MAX_RAG_QUERY_LENGTH)
    process_name: str = Field(default="", max_length=100)
    source_type: Literal["all", "web", "document", "pdf", "docx"] = "all"
    active_from: str | None = None
    active_before: str | None = None
    limit: int = Field(
        default=MAX_RAG_EVIDENCE_COUNT,
        ge=1,
        le=MAX_RAG_EVIDENCE_COUNT,
    )

def get_health() -> HealthResponse:
    """Return the backend health status."""
    return HealthResponse(data=HealthStatus(version=version("contexttrace")))


def error_response(
    status: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a consistent API error response."""
    return JSONResponse(
        status_code=status,
        content=asdict(ErrorResponse(error=ApiError(code=code, message=message))),
        headers=headers,
    )


def create_app(
    activity_tracker: ActivityTracker | None = None,
    browser_token: str | None = None,
    activity_store: ActivityStore | None = None,
    privacy_policy: PrivacyPolicy | None = None,
    document_storage_dir: str | Path | None = None,
    embedding_service: EmbeddingService | None = None,
    answer_generator: AnswerGenerator | None = None,
) -> FastAPI:
    """Create the FastAPI application with injectable dependencies."""
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        """Flush an active activity when the server shuts down cleanly."""
        yield
        finish = getattr(application.state.activity_tracker, "finish", None)
        if callable(finish):
            finish()

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )

    # Chrome extensions use a chrome-extension:// origin and require CORS
    # preflight for the Authorization + JSON headers used by the connector.
    # The bearer token remains mandatory on both browser endpoints.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"chrome-extension://[a-p]{32}",
        allow_methods=["POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    resolved_privacy_policy = privacy_policy if privacy_policy is not None else PrivacyPolicy()
    app.state.activity_store = activity_store
    app.state.browser_privacy_policy = resolved_privacy_policy
    app.state.activity_tracker = (
        activity_tracker
        if activity_tracker is not None
        else ActivityTracker(
            store=activity_store,
            privacy_policy=resolved_privacy_policy,
        )
    )
    if browser_token is not None:
        app.state.browser_token = browser_token
    elif "CONTEXTTRACE_BROWSER_TOKEN" in os.environ:
        app.state.browser_token = os.environ["CONTEXTTRACE_BROWSER_TOKEN"]
    else:
        app.state.browser_token = load_or_create_browser_token()

    app.state.document_storage_dir = (
        Path(document_storage_dir)
        if document_storage_dir is not None
        else Path.home() / ".contexttrace" / "documents"
    )
    app.state.embedding_service = (
        embedding_service
        if embedding_service is not None
        else EmbeddingService()
    )
    app.state.answer_generator = (
        answer_generator
        if answer_generator is not None
        else OllamaAnswerGenerator()
    )

    def remove_managed_document_files(paths: list[str]) -> None:
        """Remove only document copies inside ContextTrace's storage folder."""
        storage_root = app.state.document_storage_dir.resolve()
        for raw_path in paths:
            try:
                candidate = Path(raw_path).resolve()
                candidate.relative_to(storage_root)
            except (OSError, ValueError):
                # Never delete an original user file outside app-managed storage.
                continue
            try:
                if candidate.is_file():
                    candidate.unlink()
            except OSError:
                logger.warning("Unable to remove stored document copy")

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return get_health()

    @app.get(ACTIVITY_PATH)
    async def current_activity():
        activity = app.state.activity_tracker.get_current_activity()
        return asdict(activity_response(activity))

    @app.get(ACTIVITY_HISTORY_PATH)
    async def activity_history(limit: int = Query(default=50, ge=1, le=200)):
        records = app.state.activity_tracker.get_recent_records(limit)
        return {
            "ok": True,
            "data": {"records": [asdict(record) for record in records]},
            "error": None,
        }

    @app.get(RECENT_RECORDS_PATH)
    async def recent_records(
        limit: int = Query(default=RECENT_RECORDS_LIMIT, ge=1, le=200),
    ):
        records = app.state.activity_tracker.get_recent_records(limit)

        return {
            "ok": True,
            "data": {
                "service": SERVICE_NAME,
                "api_version": API_VERSION,
                "records": [
                    {
                        "id": str(record.id),
                        "application": record.application,
                        "process_name": record.process_name,
                        "window_title": record.window_title,
                        "started_at": record.started_at,
                        "last_active_at": record.ended_at,
                        "active_duration_ms": record.active_duration_ms,
                        "foreground_count": 1,
                    }
                    for record in records
                ],
            },
            "error": None,
        }

    @app.get(SESSIONS_PATH)
    async def recent_sessions(limit: int = Query(default=50, ge=1, le=200)):
        """Return recent time-gap-based work sessions."""
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        return {
            "ok": True,
            "data": {"sessions": store.get_recent_sessions(limit)},
            "error": None,
        }

    @app.get(SESSION_DETAIL_PATH)
    async def session_detail(
        session_id: int,
        limit: int = Query(default=200, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        """Return one session and a page of its activity timeline."""
        if session_id < 1:
            raise HTTPException(status_code=422, detail="session_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "ok": True,
            "data": {
                "session": session,
                "activities": [
                    asdict(item)
                    for item in store.get_session_records(session_id, limit=limit, offset=offset)
                ],
                "activities_pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": int(session["activity_count"]),
                    "has_more": offset + limit < int(session["activity_count"]),
                },
                "materials": store.get_session_materials(session_id),
            },
            "error": None,
        }

    @app.get(SESSION_MATERIALS_PATH)
    async def session_materials(session_id: int):
        """Return documents and browser pages related to a work session."""
        if session_id < 1:
            raise HTTPException(status_code=422, detail="session_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "ok": True,
            "data": store.get_session_materials(session_id),
            "error": None,
        }

    @app.delete(ACTIVITY_RECORD_DELETE_PATH)
    async def delete_activity_record(record_id: int):
        """Delete one activity and its dependent collected/indexed records."""
        if record_id < 1:
            raise HTTPException(status_code=422, detail="record_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        document_paths = store.get_activity_document_paths(record_id)
        deleted = store.delete_activity_record(record_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Activity record not found")
        remove_managed_document_files(document_paths)
        return {"ok": True, "data": {"deleted": True, "record_id": record_id}, "error": None}

    @app.delete(ALL_RECORDS_DELETE_PATH)
    async def delete_all_records(confirm: bool = Query(default=False)):
        """Delete all collected records; requires explicit confirmation."""
        if not confirm:
            raise HTTPException(status_code=400, detail="Set confirm=true to delete all records")
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        document_paths = store.get_all_document_file_paths()
        counts = store.delete_all_records()
        remove_managed_document_files(document_paths)
        return {"ok": True, "data": {"deleted_counts": counts}, "error": None}

    @app.get(SEARCH_PATH)
    async def search_records(
        keyword: str = Query(default=""),
        process_name: str = Query(default=""),
        source_type: Literal[
            "all", "web", "document", "pdf", "docx"
        ] = Query(default="all"),
        active_from: str | None = Query(default=None),
        active_before: str | None = Query(default=None),
        sort: Literal["recent", "oldest"] = Query(default="recent"),
        limit: int = Query(default=SEARCH_LIMIT, ge=1, le=SEARCH_LIMIT),
    ):
        """Search saved work metadata using explicit, AND-combined conditions."""
        if any(unicodedata.category(char) == "Cc" for char in keyword):
            raise HTTPException(
                status_code=422,
                detail="keyword contains control characters",
            )
        if any(unicodedata.category(char) == "Cc" for char in process_name):
            raise HTTPException(
                status_code=422,
                detail="process_name contains control characters",
            )

        normalized_keyword = keyword.strip()
        normalized_process = process_name.strip().casefold()

        if len(normalized_keyword) > MAX_SEARCH_KEYWORD:
            raise HTTPException(
                status_code=422,
                detail="keyword is too long",
            )
        if len(normalized_process) > MAX_SEARCH_PROCESS:
            raise HTTPException(
                status_code=422,
                detail="process_name is too long",
            )
        def validate_boundary(value: str | None, field_name: str):
            if value is None:
                return None
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name} must be an ISO-8601 timestamp",
                ) from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name} must include a timezone",
                )
            return parsed

        lower = validate_boundary(active_from, "active_from")
        upper = validate_boundary(active_before, "active_before")
        if lower is not None and upper is not None and lower >= upper:
            raise HTTPException(
                status_code=422,
                detail="active_from must be earlier than active_before",
            )

        request_data = SearchRequest(
            keyword=normalized_keyword,
            process_name=normalized_process,
            source_type=source_type,
            active_from=active_from,
            active_before=active_before,
            sort=sort,
            limit=limit,
        )

        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store

        records, has_more = store.search_records(
            keyword=normalized_keyword,
            process_name=normalized_process,
            source_type=source_type,
            active_from=active_from,
            active_before=active_before,
            sort=sort,
            limit=limit,
            privacy_policy=app.state.browser_privacy_policy,
        )
        response = SearchResponse(
            data=SearchResults(
                request=request_data,
                records=records,
                has_more=has_more,
            )
        )
        return asdict(response)


    @app.post(SEMANTIC_SEARCH_PATH)
    async def semantic_search(body: SemanticSearchBody):
        """Find semantically similar indexed passages with optional metadata filters."""
        query = body.query.strip()
        process_name = body.process_name.strip().casefold()
        if not query:
            raise HTTPException(status_code=422, detail="query must not be empty")
        if any(unicodedata.category(char) == "Cc" for char in query):
            raise HTTPException(status_code=422, detail="query contains control characters")
        if any(unicodedata.category(char) == "Cc" for char in process_name):
            raise HTTPException(status_code=422, detail="process_name contains control characters")
        if len(process_name) > 100:
            raise HTTPException(status_code=422, detail="process_name is too long")

        def validate_semantic_boundary(value: str | None, field_name: str):
            if value is None:
                return None
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name} must be an ISO-8601 timestamp",
                ) from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name} must include a timezone",
                )
            return parsed

        lower = validate_semantic_boundary(body.active_from, "active_from")
        upper = validate_semantic_boundary(body.active_before, "active_before")
        if lower is not None and upper is not None and lower >= upper:
            raise HTTPException(
                status_code=422,
                detail="active_from must be earlier than active_before",
            )

        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store

        try:
            query_vector = app.state.embedding_service.embed_query(
                query,
                privacy_policy=app.state.browser_privacy_policy,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="query cannot be used for search") from exc
        except Exception as exc:
            logger.warning("Semantic search model unavailable (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="semantic search is temporarily unavailable",
            ) from exc

        try:
            hits, has_more = store.search_semantic_chunks(
                query_vector,
                model_name=app.state.embedding_service.model_name,
                process_name=process_name,
                source_type=body.source_type,
                active_from=body.active_from,
                active_before=body.active_before,
                sort=body.sort,
                limit=body.limit,
                privacy_policy=app.state.browser_privacy_policy,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid semantic search filters") from exc

        request_data = SemanticSearchRequest(
            query=query,
            process_name=process_name,
            source_type=body.source_type,
            active_from=body.active_from,
            active_before=body.active_before,
            sort=body.sort,
            limit=body.limit,
        )
        response = SemanticSearchResponse(
            data=SemanticSearchResults(
                request=request_data,
                hits=hits,
                has_more=has_more,
            )
        )
        return asdict(response)

    @app.post("/records/answer")
    async def generate_rag_answer(body: RAGAnswerBody):
        """Generate an answer grounded in retrieved work records."""
        query = body.query.strip()
        process_name = body.process_name.strip().casefold()

        if not query:
            raise HTTPException(
                status_code=422,
                detail="query must not be empty",
            )

        if any(
            unicodedata.category(char) == "Cc"
            for char in query
        ):
            raise HTTPException(
                status_code=422,
                detail="query contains control characters",
            )

        if any(
            unicodedata.category(char) == "Cc"
            for char in process_name
        ):
            raise HTTPException(
                status_code=422,
                detail="process_name contains control characters",
            )

        if len(process_name) > 100:
            raise HTTPException(
                status_code=422,
                detail="process_name is too long",
            )

        policy = app.state.browser_privacy_policy

        if policy.contains_sensitive_data(query):
            raise HTTPException(
                status_code=422,
                detail="query contains potentially sensitive data",
            )

        def validate_rag_boundary(
            value: str | None,
            field_name: str,
        ):
            if value is None:
                return None

            try:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name} must be an ISO-8601 timestamp",
                ) from exc

            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field_name} must include a timezone",
                )

            return parsed

        lower = validate_rag_boundary(
            body.active_from,
            "active_from",
        )
        upper = validate_rag_boundary(
            body.active_before,
            "active_before",
        )

        if lower is not None and upper is not None and lower >= upper:
            raise HTTPException(
                status_code=422,
                detail="active_from must be earlier than active_before",
            )

        store = app.state.activity_store

        if store is None:
            store = ActivityStore()
            app.state.activity_store = store

        rag_service = RAGService(
            store=store,
            embedding_service=app.state.embedding_service,
            answer_generator=app.state.answer_generator,
            privacy_policy=policy,
        )

        rag_request = RAGRequest(
            query=query,
            process_name=process_name,
            source_type=body.source_type,
            active_from=body.active_from,
            active_before=body.active_before,
            limit=body.limit,
        )

        try:
            result = rag_service.answer(rag_request)

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Unable to process the RAG request",
            ) from exc

        except Exception as exc:
            logger.exception(
                "RAG answer generation failed (%s)",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Answer generation is temporarily unavailable",
            ) from exc

        response = RAGResponse(data=result)
        return asdict(response)
    @app.post("/documents", status_code=201)
    async def upload_document(
        file: UploadFile = File(...),
        context_id: int = Form(..., ge=1),
    ):
        """Extract, persist, and index an uploaded PDF or DOCX document."""
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store

        activity_record = store.get_record(context_id)

        if activity_record is None:
            raise HTTPException(
                status_code=404,
                detail="Activity record not found",
            )

        original_filename = PureWindowsPath(file.filename or "").name

        if not original_filename or original_filename in {".", ".."}:
            raise HTTPException(
                status_code=422,
                detail="A valid filename is required",
            )

        suffix = Path(original_filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail="Only PDF and DOCX files are supported",
            )

        temporary_path: Path | None = None
        stored_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                prefix="contexttrace-",
                suffix=suffix,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                total_size = 0

                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break

                    total_size += len(chunk)
                    if total_size > MAX_DOCUMENT_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail="Document exceeds the 20 MiB size limit",
                        )

                    temporary_file.write(chunk)

            extracted_text = extract_document_text(temporary_path)

            storage_dir = app.state.document_storage_dir
            storage_dir.mkdir(parents=True, exist_ok=True)

            stored_path = storage_dir / f"{uuid.uuid4().hex}{suffix}"
            shutil.copy2(temporary_path, stored_path)

        except HTTPException:
            raise

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Unable to extract document text",
            ) from exc

        except OSError as exc:
            if stored_path is not None:
                stored_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=500,
                detail="Unable to store document file",
            ) from exc

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            await file.close()

        assert stored_path is not None

        captured_at = datetime.now(timezone.utc).isoformat()

        try:
            document_id = store.save_document_record(
                file_path=stored_path,
                file_name=original_filename,
                extracted_text=extracted_text,
                captured_at=captured_at,
                context_id=context_id,
            )
        except ValueError as exc:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail="Invalid document data",
            ) from exc
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise

        source_metadata = SourceMetadata(
            kind="document",
            application=activity_record.application,
            process_name=activity_record.process_name,
            window_title=activity_record.window_title,
            started_at=activity_record.started_at,
            last_active_at=activity_record.ended_at,
            captured_at=captured_at,
            content_truncated=False,
            document=LocalDocument(
                file_path=str(stored_path.resolve()),
                file_type=suffix.lstrip("."),
            ),
        )

        try:
            search_source_id = SearchIndexer(
                store=store,
                embedding_service=app.state.embedding_service,
                privacy_policy=app.state.browser_privacy_policy,
            ).index_source(
                context_id=context_id,
                source_metadata=source_metadata,
                text=extracted_text,
                document_id=document_id,
            )

        except ValueError as exc:
            store.delete_document_record(document_id)
            stored_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=422,
                detail="Document contains data that cannot be indexed",
            ) from exc

        except Exception as exc:
            logger.exception("Document indexing failed")

            store.delete_document_record(document_id)
            stored_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=503,
                detail="Unable to index document",
            ) from exc

        return {
            "ok": True,
            "data": {
                "id": document_id,
                "file_name": original_filename,
                "file_type": suffix,
                "extracted_text": extracted_text,
                "captured_at": captured_at,
                "search_source_id": search_source_id,
            },
            "error": None,
        }

    @app.get("/documents")
    async def list_documents(
        limit: int = Query(default=50, ge=1, le=200),
    ):
        """Return recently uploaded documents."""
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store

        records = store.get_recent_document_records(limit)

        return {
            "ok": True,
            "data": {"documents": [asdict(record) for record in records]},
            "error": None,
        }

    @app.delete(DOCUMENT_RECORD_DELETE_PATH)
    async def delete_document(document_id: int):
        """Delete a document record, its index, and only its stored copy."""
        if document_id < 1:
            raise HTTPException(status_code=422, detail="document_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        path = store.get_document_file_path(document_id)
        deleted = store.delete_document_record(document_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        if path:
            remove_managed_document_files([path])
        return {"ok": True, "data": {"deleted": True, "document_id": document_id}, "error": None}

    @app.post(BROWSER_SOURCE_PATH)
    async def save_browser_source(
        payload: BrowserSourceRequest,
        authorization: str | None = Header(default=None),
    ):
        """Save a sanitized browser page after verifying its bearer token."""
        token = app.state.browser_token

        if not token:
            raise HTTPException(
                status_code=503,
                detail="Browser collection is not configured",
            )

        scheme, separator, supplied_token = (authorization or "").partition(" ")
        if (
            scheme.lower() != "bearer"
            or not separator
            or not supplied_token
            or not hmac.compare_digest(supplied_token, token)
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        url = payload.url.strip()
        page_title = payload.page_title.strip()

        if not page_title:
            raise HTTPException(
                status_code=422,
                detail="Page title must not be empty",
            )

        policy = app.state.browser_privacy_policy

        try:
            sanitized_url = policy.sanitize_browser_url(url)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid or disallowed browser URL",
            ) from exc

        sanitized_title = policy.sanitize_title(page_title)
        captured_at = datetime.now(timezone.utc).isoformat()

        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store

        record_id = store.save_browser_source_record(
            browser=payload.browser,
            url=sanitized_url,
            page_title=sanitized_title,
            captured_at=captured_at,
        )

        return {
            "ok": True,
            "data": {
                "id": record_id,
                "browser": payload.browser,
                "url": sanitized_url,
                "page_title": sanitized_title,
                "captured_at": captured_at,
            },
            "error": None,
        }

    @app.delete(BROWSER_SOURCE_DELETE_PATH)
    async def delete_browser_source(browser_source_id: int):
        """Delete a browser source and all indexed content derived from it."""
        if browser_source_id < 1:
            raise HTTPException(status_code=422, detail="browser_source_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        if not store.delete_browser_source_record(browser_source_id):
            raise HTTPException(status_code=404, detail="Browser source not found")
        return {
            "ok": True,
            "data": {"deleted": True, "browser_source_id": browser_source_id},
            "error": None,
        }

    @app.post(BROWSER_CONTENT_PATH)
    async def save_browser_content(
        payload: BrowserContentRequest,
        authorization: str | None = Header(default=None),
    ):
        """Save page text associated with an existing browser source."""
        token = app.state.browser_token

        if not token:
            raise HTTPException(
                status_code=503,
                detail="Browser collection is not configured",
            )

        scheme, separator, supplied_token = (authorization or "").partition(" ")
        if (
            scheme.lower() != "bearer"
            or not separator
            or not supplied_token
            or not hmac.compare_digest(supplied_token, token)
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        content_text = payload.content_text.strip()

        if not content_text:
            raise HTTPException(
                status_code=422,
                detail="Page content must not be empty",
            )

        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store

        source_record = store.get_browser_source_record(
            payload.browser_source_id
        )
        if source_record is None:
            raise HTTPException(
                status_code=404,
                detail="Browser source was not found",
            )

        existing_content = store.get_browser_content_record(
            payload.browser_source_id
        )
        if existing_content is not None:
            raise HTTPException(
                status_code=409,
                detail="Browser content has already been captured",
            )

        # Reject sensitive content before either persistence or embedding.
        policy = app.state.browser_privacy_policy
        if policy.contains_sensitive_data(content_text):
            raise HTTPException(
                status_code=422,
                detail="Browser content contains potentially sensitive data",
            )

        captured_at = datetime.now(timezone.utc).isoformat()
        browser_name = (
            "Google Chrome" if source_record.browser == "chrome"
            else "Microsoft Edge"
        )
        process_name = (
            "chrome.exe" if source_record.browser == "chrome"
            else "msedge.exe"
        )
        source_metadata = SourceMetadata(
            kind="web",
            application=browser_name,
            process_name=process_name,
            window_title=source_record.page_title,
            started_at=source_record.captured_at,
            last_active_at=source_record.captured_at,
            captured_at=captured_at,
            content_truncated=False,
            browser=BrowserPage(
                browser=source_record.browser,
                page_title=source_record.page_title,
                url=source_record.url,
            ),
        )

        content_id: int | None = None

        try:
            # Save the original content first. If indexing fails, only this
            # newly created content record is removed.
            content_id = store.save_browser_content_record(
                browser_source_id=payload.browser_source_id,
                content_text=content_text,
                captured_at=captured_at,
            )

            search_source_id = SearchIndexer(
                store=store,
                embedding_service=app.state.embedding_service,
                privacy_policy=policy,
            ).index_source(
                context_id=None,
                source_metadata=source_metadata,
                text=content_text,
                browser_source_id=payload.browser_source_id,
            )

            if search_source_id is None:
                raise ValueError("Browser content produced no searchable text")

        except ValueError as exc:
            if content_id is not None:
                try:
                    store.delete_browser_content_record(content_id)
                except Exception:
                    logger.exception(
                        "Failed to clean up browser content after indexing failure"
                    )

            raise HTTPException(
                status_code=422,
                detail="Invalid or sensitive browser content",
            ) from exc

        except sqlite3.IntegrityError as exc:
            if content_id is not None:
                try:
                    store.delete_browser_content_record(content_id)
                except Exception:
                    logger.exception(
                        "Failed to clean up browser content after indexing failure"
                    )

            raise HTTPException(
                status_code=409,
                detail="Browser content has already been captured",
            ) from exc

        except Exception as exc:
            if content_id is not None:
                try:
                    store.delete_browser_content_record(content_id)
                except Exception:
                    logger.exception(
                        "Failed to clean up browser content after indexing failure"
                    )

            logger.exception("Browser content indexing failed")
            raise HTTPException(
                status_code=503,
                detail="Unable to index browser content",
            ) from exc

        return {
            "ok": True,
            "data": {
                "id": content_id,
                "browser_source_id": payload.browser_source_id,
                "search_source_id": search_source_id,
                "captured_at": captured_at,
            },
            "error": None,
        }

    @app.delete(BROWSER_CONTENT_DELETE_PATH)
    async def delete_browser_content(content_id: int):
        """Delete one browser page body but keep its source URL metadata."""
        if content_id < 1:
            raise HTTPException(status_code=422, detail="content_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = ActivityStore()
            app.state.activity_store = store
        if not store.delete_browser_content_record(content_id):
            raise HTTPException(status_code=404, detail="Browser content not found")
        return {"ok": True, "data": {"deleted": True, "content_id": content_id}, "error": None}

    @app.exception_handler(HTTPException)
    async def http_error(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        code, message = {
            404: ("NOT_FOUND", "요청한 경로를 찾을 수 없습니다."),
            405: ("METHOD_NOT_ALLOWED", "지원하지 않는 요청 방식입니다."),
        }.get(
            exc.status_code,
            ("HTTP_ERROR", "요청을 처리할 수 없습니다."),
        )

        return error_response(
            exc.status_code,
            code,
            message,
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            422,
            "INVALID_REQUEST",
            "올바르지 않은 요청입니다.",
        )

    @app.exception_handler(Exception)
    async def internal_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        # Do not expose internal exception details.
        logger.error("Request failed (%s)", type(exc).__name__)

        return error_response(
            500,
            "INTERNAL_ERROR",
            "요청 처리 중 오류가 발생했습니다.",
        )

    return app


def activity_response(activity):
    """Wrap current activity in the standard success envelope."""
    from shared.activity import CurrentActivityResponse

    return CurrentActivityResponse(data=activity)


app = create_app()