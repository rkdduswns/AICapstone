"""Local HTTP boundary for health, activity, browser, and document APIs."""

import hmac
import logging
import os
import shutil
import sqlite3
import tempfile
import uuid
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
from backend.privacy import PrivacyPolicy
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
from shared.records import RECENT_RECORDS_LIMIT, RECENT_RECORDS_PATH
from shared.search_data import SourceMetadata

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
) -> FastAPI:
    """Create the FastAPI application with injectable dependencies."""
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
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

    app.state.activity_tracker = (
        activity_tracker
        if activity_tracker is not None
        else ActivityTracker()
    )
    if browser_token is not None:
        app.state.browser_token = browser_token
    elif "CONTEXTTRACE_BROWSER_TOKEN" in os.environ:
        app.state.browser_token = os.environ["CONTEXTTRACE_BROWSER_TOKEN"]
    else:
        app.state.browser_token = load_or_create_browser_token()

    app.state.activity_store = activity_store
    app.state.browser_privacy_policy = (
        privacy_policy
        if privacy_policy is not None
        else PrivacyPolicy()
    )
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