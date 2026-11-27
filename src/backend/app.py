"""Local HTTP boundary for health, activity, browser, and document APIs."""

import asyncio
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
from typing import Callable, Literal

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
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
from backend.embedding import EmbeddingService
from backend.history_sources import (
    context_record,
    install_source_routes,
    require_browser_activity,
    save_linked_browser,
)
from backend.indexing_runtime import index_collected_source, prepare_search_index
from backend.ollama_answer_generator import OllamaAnswerGenerator
from backend.privacy import PrivacyPolicy
from backend.privacy_settings import StoredPrivacySettings
from backend.rag_service import AnswerGenerator, RAGService
from shared.activity import (
    ACTIVITY_HISTORY_PATH,
    ACTIVITY_PATH,
    BROWSER_CONTENT_PATH,
    BROWSER_SOURCE_PATH,
)
from shared.browser import BrowserPage
from shared.document import LocalDocument, read_document
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
    # 기존 수신 전용 요청은 None이다. 새 연결 요청은 관측한 실제 작업 ID를 반드시 보낸다.
    record_id: int | None = Field(default=None, ge=1, le=2**63 - 1)
    context_id: int | None = Field(default=None, ge=1, le=2**63 - 1)

    @field_validator("record_id", "context_id", mode="before")
    @classmethod
    def actual_context_id(cls, value):
        """불리언·실수·잘못된 문자열을 다른 작업 ID로 강제 변환하지 않는다."""
        if value is None or type(value) is int:
            return value
        if isinstance(value, str) and value.isascii() and value.isdecimal() and not value.startswith("0"):
            return int(value)
        raise ValueError("Invalid context ID")


class BrowserContentRequest(BaseModel):
    """Validated text content received from a browser extension."""

    browser_source_id: int = Field(ge=1)
    content_text: str = Field(min_length=1, max_length=100_000)
    truncated: bool = Field(default=False, strict=True)


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
    """강써치 배포 메타데이터에서 버전을 읽고 기존 API 식별자를 유지한다."""
    return HealthResponse(data=HealthStatus(version=version("gangsearch")))


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
    document_storage_dir: str | Path | None = None,
    embedding_service: EmbeddingService | None = None,
    answer_generator: AnswerGenerator | None = None,
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
    application_blocks = {name for name in policy.blocked_applications if not name.endswith(".exe")}
    initial_settings = StoredPrivacySettings(
        paused=policy.collection_paused,
        blocked_processes=sorted(policy.blocked_applications - application_blocks),
        clipboard_enabled=False,
    )
    settings_loaded = False

    def stop_for_settings_failure() -> None:
        """설정 오류의 수집 중단 구간을 시간에 더하지 않고 복사 수집도 즉시 끈다."""
        tracker.finish()
        policy.collection_paused = True
        collector.set_enabled(False)
        app.state.clipboard_enabled = False

    def apply_settings(settings: StoredPrivacySettings, *, restoring: bool = False) -> None:
        """정책 경계의 세션과 복사 기준을 정리한 뒤 복원·저장된 전체 상태를 적용한다."""
        if restoring:
            # 적용 실패 뒤 내부 사용 여부가 같아도 복원 이전의 복사를 새 이벤트로 읽지 않는다.
            collector.reset_baseline()
        policy_changed = (settings.paused != policy.collection_paused
                          or set(settings.blocked_processes) != policy.blocked_applications - application_blocks)
        if policy_changed:
            tracker.finish()
            if settings.clipboard_enabled == app.state.clipboard_enabled:
                collector.reset_baseline()
        collector.set_enabled(settings.clipboard_enabled)
        policy.collection_paused = settings.paused
        policy.blocked_applications = set(settings.blocked_processes) | application_blocks
        app.state.clipboard_enabled = settings.clipboard_enabled

    def ensure_settings() -> None:
        """생성 시 DB를 열지 않고 최초 수집·요청 전에 저장된 보호 선택을 복원한다."""
        nonlocal settings_loaded
        if settings_loaded:
            return
        try:
            saved = tracker.store.load_privacy_settings()
            apply_settings(saved if saved is not None else initial_settings, restoring=True)
        except Exception:
            # 행 없음만 기본값이다. 손상·읽기 실패는 수집을 막고 저장 원문을 보존한다.
            stop_for_settings_failure()
            raise RuntimeError("개인정보 설정을 복원하지 못해 수집을 중지했습니다.") from None
        settings_loaded = True

    async def require_settings() -> None:
        """lifespan 없는 요청도 수신 처리·저장 로직이나 추적기 호출 전에 설정을 복원한다."""
        try:
            ensure_settings()
        except RuntimeError:
            raise HTTPException(503) from None

    def update_settings(changes: dict) -> None:
        """설정 커밋 성공 이후에만 메모리에 반영하여 저장 실패를 성공으로 표시하지 않는다."""
        nonlocal settings_loaded
        ensure_settings()
        defaults = StoredPrivacySettings(
            paused=policy.collection_paused,
            blocked_processes=sorted(policy.blocked_applications - application_blocks),
            clipboard_enabled=app.state.clipboard_enabled,
        )
        try:
            saved = tracker.store.update_privacy_settings(changes, defaults)
        except Exception:
            raise HTTPException(503) from None
        try:
            apply_settings(saved)
        except Exception:
            # 커밋 후 네이티브 기준 갱신이 실패해도 다음 복원 전까지 수집은 허용하지 않는다.
            settings_loaded = False
            stop_for_settings_failure()
            raise HTTPException(503) from None

    def sample_activity():
        """한 스냅샷을 공유하고 클립보드 실패가 현재 창 조회를 중단하지 않게 한다."""
        ensure_settings()
        activity = tracker.get_current_activity()
        try:
            collector.collect_once(activity)
        except Exception as exc:
            logger.warning("Clipboard collection failed (%s)", type(exc).__name__)
        return activity

    async def collect_loop():
        """동일 이벤트 루프에서 설정 변경과 직렬화하여 변경 완료 후 옛 정책으로 쓰지 않는다."""
        restore_failed = False
        while True:
            try:
                sample_activity()
                restore_failed = False
            except RuntimeError:
                # 설정 적용 오류 뒤에도 루프는 유지하되 복원이 성공하기 전에는 수집하지 않는다.
                if not restore_failed:
                    logger.warning("Privacy settings unavailable; collection remains paused")
                restore_failed = True
            await asyncio.sleep(collection_interval)

    @asynccontextmanager
    async def lifespan(app):
        """서버 시작 시 수집을 예약하고 종료 시 타이머와 마지막 기록을 정리한다."""
        ensure_settings()
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
        dependencies=[Depends(require_settings)],
    )
    app.state.activity_tracker = tracker
    app.state.clipboard_collector = collector
    app.state.clipboard_enabled = False
    # 새 이름이 명시적으로 비어 있으면 구형 토큰으로 되돌리지 않는다.
    app.state.browser_token = (
        browser_token
        if browser_token is not None
        else os.environ.get("GANGSEARCH_BROWSER_TOKEN", os.environ.get("CONTEXTTRACE_BROWSER_TOKEN", ""))
    )

    app.add_middleware(
        CORSMiddleware, allow_origins=[], allow_origin_regex=r"chrome-extension://[a-p]{32}",
        allow_methods=["POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )
    app.state.activity_store = activity_store
    app.state.browser_privacy_policy = policy
    app.state.update_privacy_settings = update_settings
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

    @app.get(SESSIONS_PATH)
    async def recent_sessions(limit: int = Query(default=50, ge=1, le=200)):
        """Return recent time-gap-based work sessions."""
        store = app.state.activity_store
        if store is None:
            store = get_store()
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
            store = get_store()
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
            store = get_store()
            app.state.activity_store = store
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "ok": True,
            "data": store.get_session_materials(session_id),
            "error": None,
        }

    def verify_delete_origin(request: Request) -> None:
        """웹 페이지에서 전송한 삭제 요청을 거부하고 로컬 관리 API 경계를 유지한다."""
        if request.headers.get("origin") is not None:
            raise HTTPException(403)

    @app.delete(ACTIVITY_RECORD_DELETE_PATH)
    async def delete_activity_record(request: Request, record_id: int):
        """Delete one activity and its dependent collected/indexed records."""
        verify_delete_origin(request)
        if record_id < 1:
            raise HTTPException(status_code=422, detail="record_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = get_store()
            app.state.activity_store = store
        document_paths = store.get_activity_document_paths(record_id)
        deleted = store.delete_activity_record(record_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Activity record not found")
        tracker.discard_deleted_record(record_id)
        remove_managed_document_files(document_paths)
        return {"ok": True, "data": {"deleted": True, "record_id": record_id}, "error": None}

    @app.delete(ALL_RECORDS_DELETE_PATH)
    async def delete_all_records(request: Request, confirm: bool = Query(default=False)):
        """Delete all collected records; requires explicit confirmation."""
        verify_delete_origin(request)
        if not confirm:
            raise HTTPException(status_code=400, detail="Set confirm=true to delete all records")
        store = app.state.activity_store
        if store is None:
            store = get_store()
            app.state.activity_store = store
        document_paths = store.get_all_document_file_paths()
        counts = store.delete_all_records()
        tracker.discard_deleted_record()
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
            store = get_store()
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
    def semantic_search(body: SemanticSearchBody):
        """실제 의미 검색을 threadpool에서 실행하고 모델 대기 중에도 관리 API를 유지한다."""
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
            store = get_store()
            app.state.activity_store = store

        try:
            prepare_search_index(store, app.state.embedding_service, policy)
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
    def generate_rag_answer(body: RAGAnswerBody):
        """저장 근거로 답변을 생성하고 조회·출처 재검증을 실제 서비스에 맡긴다."""
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
            store = get_store()
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
            prepare_search_index(store, app.state.embedding_service, policy)
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
        request: Request,
        file: UploadFile = File(...),
        record_id: int | None = Form(default=None, ge=1, le=2**63 - 1),
        file_path: str | None = Form(default=None, max_length=8192),
        original_file_path: str | None = Form(default=None, max_length=8192),
        context_id: int | None = Form(default=None, ge=1, le=2**63 - 1),
    ):
        """선택한 문서를 추출하고 명시된 작업에만 경로와 함께 연결한다. 경로로 파일을 읽지 않는다."""
        check_collection()
        if request.headers.get("origin") is not None:
            raise HTTPException(403)
        if original_file_path is not None:
            if file_path is not None and file_path != original_file_path:
                raise HTTPException(422, detail="Conflicting original paths")
            file_path = original_file_path
        if context_id is not None and record_id is not None and context_id != record_id:
            raise HTTPException(422, detail="Conflicting context IDs")
        # 표준 context_id 업로드는 항상 관리 복사본을 갖는다. 원본 위치는 별도 메타데이터다.
        canonical_upload = context_id is not None
        backend_upload = canonical_upload and file_path is None
        record_id = context_id if context_id is not None else record_id
        store = get_store()
        activity_record = store.get_record(record_id) if record_id is not None else None
        if record_id is not None and activity_record is None:
            raise HTTPException(404)
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

        if record_id is not None and not backend_upload:
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
        elif record_id is None:
            file_path = None  # 연결 없는 기존 업로드에는 출처 경로를 임의로 부여하지 않는다.

        stored_path: Path | None = None
        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                prefix="gangsearch-",
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
            check_collection(extracted_text)
            if canonical_upload:
                storage_dir = app.state.document_storage_dir
                storage_dir.mkdir(parents=True, exist_ok=True)
                stored_path = storage_dir / f"{uuid.uuid4().hex}{suffix}"
                shutil.copy2(temporary_path, stored_path)
                if backend_upload:
                    file_path = str(stored_path.resolve())

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
        check_collection(extracted_text)

        try:
            document_id = store.save_document_record(
                file_path=str(stored_path.resolve()) if stored_path else file_path or original_filename,
                extracted_text=extracted_text,
                captured_at=captured_at,
                activity_record_id=record_id,
                file_name=original_filename,
                stored_file_path=str(stored_path) if stored_path else None,
                original_file_path=file_path if record_id and not backend_upload else None,
            )
        except sqlite3.IntegrityError as exc:
            if stored_path:
                stored_path.unlink(missing_ok=True)
            raise HTTPException(404) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid document data",
            ) from exc

        search_source_id = None
        if activity_record is not None:
            metadata = SourceMetadata(
                kind="document", application=activity_record.application,
                process_name=activity_record.process_name, window_title=activity_record.window_title,
                started_at=activity_record.started_at, last_active_at=activity_record.ended_at,
                captured_at=captured_at, content_truncated=False,
                document=LocalDocument(file_path, suffix[1:]),
                original_file_path=file_path if not backend_upload else None,
            )
            try:
                search_source_id = index_collected_source(
                    store, app.state.embedding_service, policy, metadata, extracted_text,
                    record_id, document_id=document_id,
                )
            except Exception as exc:
                store.delete_document_record(document_id)
                if stored_path:
                    stored_path.unlink(missing_ok=True)
                raise HTTPException(503, detail="Unable to index document") from exc

        return {
            "ok": True,
            "data": {
                "id": document_id,
                "file_name": original_filename,
                "file_type": suffix,
                "extracted_text": extracted_text,
                "captured_at": captured_at,
                "search_source_id": search_source_id,
                "context_id": record_id,
                "activity_record_id": record_id,
                "original_file_path": file_path if record_id and not backend_upload else None,
                "file_path": str(stored_path.resolve()) if stored_path else file_path,
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

    @app.delete(DOCUMENT_RECORD_DELETE_PATH)
    async def delete_document(request: Request, document_id: int):
        """Delete a document record, its index, and only its stored copy."""
        verify_delete_origin(request)
        if document_id < 1:
            raise HTTPException(status_code=422, detail="document_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = get_store()
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

        if payload.record_id is not None and payload.context_id is not None and payload.record_id != payload.context_id:
            raise HTTPException(422, detail="Conflicting context IDs")
        linked_record_id = payload.context_id if payload.context_id is not None else payload.record_id
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

    @app.delete(BROWSER_SOURCE_DELETE_PATH)
    async def delete_browser_source(request: Request, browser_source_id: int):
        """Delete a browser source and all indexed content derived from it."""
        verify_delete_origin(request)
        if browser_source_id < 1:
            raise HTTPException(status_code=422, detail="browser_source_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = get_store()
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
        """현재 출처의 본문·잘림 상태를 저장하고 검색 색인 실패 시 이전 원문을 보존한다."""
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

        source_record = store.get_browser_source_record(
            payload.browser_source_id
        )
        if source_record is None:
            raise HTTPException(
                status_code=404,
                detail="Browser source was not found",
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
            content_truncated=payload.truncated,
            browser=BrowserPage(
                browser=source_record.browser,
                page_title=source_record.page_title,
                url=source_record.url,
            ),
        )

        content_id: int | None = None

        linked_record_id = store.source_record_id("browser", payload.browser_source_id)
        if linked_record_id is not None:
            page = store.get_record_browser(linked_record_id)
            if page is None or page.id != payload.browser_source_id:
                raise HTTPException(409)
            require_browser_activity(tracker, linked_record_id, page.browser)

        previous_body = store.get_browser_content_record(payload.browser_source_id)
        previous_truncated = store.browser_content_truncated(payload.browser_source_id)

        def rollback_body():
            """갱신 실패 시 이전 본문을 복원하고 최초 저장 실패일 때만 새 행을 지운다."""
            if previous_body is not None:
                store.save_browser_content_record(previous_body.browser_source_id,
                    previous_body.content_text, previous_body.captured_at, previous_truncated)
            elif content_id is not None:
                store.delete_browser_content_record(content_id)

        try:
            # 수집 본문·시각·잘림을 함께 저장하고 실패 시 기존 원문을 보존한다.
            content_id = store.save_browser_content_record(
                browser_source_id=payload.browser_source_id,
                content_text=content_text,
                captured_at=captured_at,
                truncated=payload.truncated,
            )

            linked_record_id = store.source_record_id("browser", payload.browser_source_id)
            linked_record = store.get_record(linked_record_id) if linked_record_id else None
            if linked_record is not None:
                source_metadata = SourceMetadata(
                    kind="web", application=linked_record.application,
                    process_name=linked_record.process_name, window_title=linked_record.window_title,
                    started_at=linked_record.started_at, last_active_at=linked_record.ended_at,
                    captured_at=captured_at, content_truncated=payload.truncated,
                    browser=source_metadata.browser,
                )
            search_source_id = index_collected_source(
                store, app.state.embedding_service, policy, source_metadata, content_text,
                linked_record_id, browser_source_id=payload.browser_source_id,
            )

            if search_source_id is None:
                raise ValueError("Browser content produced no searchable text")

        except ValueError as exc:
            if content_id is not None:
                try:
                    rollback_body()
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
                    rollback_body()
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
                    rollback_body()
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
    async def delete_browser_content(request: Request, content_id: int):
        """Delete one browser page body but keep its source URL metadata."""
        verify_delete_origin(request)
        if content_id < 1:
            raise HTTPException(status_code=422, detail="content_id must be positive")
        store = app.state.activity_store
        if store is None:
            store = get_store()
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
