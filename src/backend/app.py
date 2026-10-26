
"""Local HTTP boundary for health, activity, browser, and document APIs."""

import asyncio
import hmac
import logging
import os
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path, PureWindowsPath
from typing import Callable, Literal

from fastapi import FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.client_api import install_client_routes
from backend.clipboard_collector import ClipboardCollector
from backend.document_extractor import (
    MAX_DOCUMENT_SIZE,
    SUPPORTED_EXTENSIONS,
    extract_document_text,
)
from backend.history_sources import (
    context_record,
    install_source_routes,
    require_browser_activity,
    save_linked_browser,
)
from backend.privacy import PrivacyPolicy
from shared.activity import (
    ACTIVITY_HISTORY_PATH,
    ACTIVITY_PATH,
    BROWSER_CONTENT_PATH,
    BROWSER_SOURCE_PATH,
)
from shared.document import read_document
from shared.protocol import (
    API_VERSION,
    SERVICE_NAME,
    ApiError,
    ErrorResponse,
    HealthResponse,
    HealthStatus,
)
from shared.records import RECENT_RECORDS_LIMIT, RECENT_RECORDS_PATH

logger = logging.getLogger(__name__)


class BrowserSourceRequest(BaseModel):
    """Validated data received from a browser extension."""

    browser: Literal["chrome", "edge"]
    url: str = Field(min_length=1, max_length=4096)
    page_title: str = Field(min_length=1, max_length=500)
    # 기존 수신 전용 요청은 None이다. 새 연결 요청은 관측한 실제 작업 ID를 반드시 보낸다.
    record_id: int | None = Field(default=None, ge=1, le=2**63 - 1)


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
    clipboard_reader: Callable[[], str | None] | None = None,
    collection_interval: float | None = 1.0,
) -> FastAPI:
    """추적·설정·업로드가 같은 정책/저장소를 사용하며 수집 수명은 서버가 관리한다.

    테스트는 감지기와 저장소를 주입하고 collection_interval=None으로 자동 폴링을 끈다.
    실제 실행은 Client 탭/연결과 관계없이 수집하며 정상 종료 시 마지막 세션을 저장한다.
    """
    if collection_interval is not None and collection_interval <= 0:
        raise ValueError("collection_interval must be positive")
    tracker = activity_tracker or ActivityTracker()
    policy = privacy_policy or tracker.privacy_policy
    tracker.configure(store=activity_store, privacy_policy=policy)
    collector = ClipboardCollector(tracker, privacy_policy=policy, clipboard_reader=clipboard_reader)

    def sample_activity():
        """한 스냅샷을 공유하고 클립보드 실패가 현재 창 조회를 중단하지 않게 한다."""
        activity = tracker.get_current_activity()
        try:
            collector.collect_once(activity)
        except Exception as exc:
            logger.warning("Clipboard collection failed (%s)", type(exc).__name__)
        return activity

    async def collect_loop():
        """동일 이벤트 루프에서 설정 변경과 직렬화하여 변경 완료 후 옛 정책으로 쓰지 않는다."""
        while True:
            sample_activity()
            await asyncio.sleep(collection_interval)

    @asynccontextmanager
    async def lifespan(app):
        """서버 시작 시 수집을 예약하고 종료 시 타이머와 마지막 기록을 정리한다."""
        task = asyncio.create_task(collect_loop()) if collection_interval is not None else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # 정상 종료 시 취소한 수집 루프의 완료를 기다린 결과다.
            tracker.finish()

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.state.activity_tracker = tracker
    app.state.clipboard_collector = collector
    app.state.clipboard_enabled = False
    app.state.browser_token = (
        browser_token
        if browser_token is not None
        else os.environ.get("CONTEXTTRACE_BROWSER_TOKEN", "")
    )
    app.state.activity_store = activity_store
    app.state.browser_privacy_policy = policy
    install_client_routes(app)
    install_source_routes(app)

    def get_store():
        """추적기와 업로드 API가 같은 저장소를 지연 생성해 사용한다."""
        store = tracker.store
        app.state.activity_store = store
        return store

    def check_collection(text: str | None = None) -> None:
        """수신 시작과 저장 직전에 같은 정책을 확인하여 일시정지 중 새 자료를 쓰지 않는다."""
        if policy.collection_paused or (text is not None and policy.contains_sensitive_data(text)):
            raise HTTPException(403)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return get_health()

    @app.get(ACTIVITY_PATH)
    async def current_activity():
        activity = sample_activity()
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
        limit: int = Query(default=RECENT_RECORDS_LIMIT, ge=1, le=RECENT_RECORDS_LIMIT),
    ):
        records = app.state.activity_tracker.get_recent_records(limit)

        return {
            "ok": True,
            "data": {
                "service": SERVICE_NAME,
                "api_version": API_VERSION,
                "records": [asdict(context_record(get_store(), record)) for record in records],
            },
            "error": None,
        }

    @app.post("/documents", status_code=201)
    async def upload_document(
        request: Request,
        file: UploadFile = File(...),
        record_id: int | None = Form(default=None, ge=1, le=2**63 - 1),
        file_path: str | None = Form(default=None, max_length=8192),
    ):
        """선택한 문서를 추출하고 명시된 작업에만 경로와 함께 연결한다. 경로로 파일을 읽지 않는다."""
        check_collection()
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

        if record_id is not None:
            if (request.headers.get("origin") is not None
                    or request.headers.get("x-contexttrace-client") != "desktop"):
                raise HTTPException(403)
            if get_store().get_record(record_id) is None:
                raise HTTPException(404)
            try:
                source = read_document({"file_path": file_path, "file_type": suffix[1:]})
                if PureWindowsPath(source.file_path).name.casefold() != original_filename.casefold():
                    raise ValueError("Filename does not match source")
            except ValueError as exc:
                raise HTTPException(422) from exc
        else:
            file_path = None  # 연결 없는 기존 업로드에는 출처 경로를 임의로 부여하지 않는다.

        temporary_path: Path | None = None

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

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Unable to extract document text",
            ) from exc

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            await file.close()

        captured_at = datetime.now(timezone.utc).isoformat()

        store = get_store()
        check_collection(extracted_text)

        try:
            document_id = store.save_document_record(
                file_path=file_path or original_filename,
                extracted_text=extracted_text,
                captured_at=captured_at,
                activity_record_id=record_id,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(404) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid document data",
            ) from exc

        return {
            "ok": True,
            "data": {
                "id": document_id,
                "file_name": original_filename,
                "file_type": suffix,
                "extracted_text": extracted_text,
                "captured_at": captured_at,
                "activity_record_id": record_id,
                "file_path": file_path,
            },
            "error": None,
        }

    @app.get("/documents")
    async def list_documents(
        limit: int = Query(default=50, ge=1, le=200),
    ):
        """최근 가져온 문서와 실제로 연결된 작업 ID를 함께 반환한다."""
        store = get_store()

        records = store.get_recent_document_records(limit)

        return {
            "ok": True,
            "data": {"documents": [dict(asdict(record),
                activity_record_id=store.source_record_id("document", record.id)) for record in records]},
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
        check_collection()
        try:
            sanitized_url = policy.sanitize_browser_url(url)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid or disallowed browser URL",
            ) from exc

        sanitized_title = policy.sanitize_title(page_title)
        captured_at = datetime.now(timezone.utc).isoformat()

        store = get_store()

        linked_record_id = payload.record_id
        if linked_record_id is not None:
            record_id, linked_record_id = save_linked_browser(
                tracker, linked_record_id, payload.browser, sanitized_url, sanitized_title, captured_at)
            captured_at = store.get_record_browser(linked_record_id).captured_at
        else:
            record_id = store.save_browser_source_record(
                payload.browser, sanitized_url, sanitized_title, captured_at)

        return {
            "ok": True,
            "data": {
                "id": record_id,
                "browser": payload.browser,
                "url": sanitized_url,
                "page_title": sanitized_title,
                "captured_at": captured_at,
                "activity_record_id": str(linked_record_id) if linked_record_id is not None else None,
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
        check_collection(content_text)
        if not content_text:
            raise HTTPException(
                status_code=422,
                detail="Page content must not be empty",
            )

        store = get_store()

        captured_at = datetime.now(timezone.utc).isoformat()

        linked_record_id = store.source_record_id("browser", payload.browser_source_id)
        if linked_record_id is not None:
            page = store.get_record_browser(linked_record_id)
            if page is None or page.id != payload.browser_source_id:
                raise HTTPException(409)
            require_browser_activity(tracker, linked_record_id, page.browser)

        try:
            content_id = store.save_browser_content_record(
                browser_source_id=payload.browser_source_id,
                content_text=content_text,
                captured_at=captured_at,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid browser content",
            ) from exc
        except Exception as exc:
            # A missing source ID violates the SQLite foreign-key constraint.
            import sqlite3

            if isinstance(exc, sqlite3.IntegrityError):
                raise HTTPException(
                    status_code=404,
                    detail="Browser source was not found",
                ) from exc
            raise

        return {
            "ok": True,
            "data": {
                "id": content_id,
                "browser_source_id": payload.browser_source_id,
                "captured_at": captured_at,
            },
            "error": None,
        }

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code, message = {
            404: ("NOT_FOUND", "요청한 경로를 찾을 수 없습니다."),
            405: ("METHOD_NOT_ALLOWED", "지원하지 않는 요청 방식입니다."),
        }.get(exc.status_code, ("HTTP_ERROR", "요청을 처리할 수 없습니다."))
        return error_response(exc.status_code, code, message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(422, "INVALID_REQUEST", "올바르지 않은 요청입니다.")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
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
