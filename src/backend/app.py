"""Local HTTP boundary; no UI or collection dependencies."""

import logging
from dataclasses import asdict
from importlib.metadata import version

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from shared.protocol import ApiError, ErrorResponse, HealthResponse, HealthStatus

logger = logging.getLogger(__name__)


def get_health() -> HealthResponse:
    return HealthResponse(data=HealthStatus(version=version("contexttrace")))


def error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=asdict(ErrorResponse(error=ApiError(code=code, message=message))),
        headers=headers,
    )


def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return get_health()

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code, message = {
            404: ("NOT_FOUND", "요청한 경로를 찾을 수 없습니다."),
            405: ("METHOD_NOT_ALLOWED", "지원하지 않는 요청 방식입니다."),
        }.get(exc.status_code, ("HTTP_ERROR", "요청을 처리할 수 없습니다."))
        return error_response(exc.status_code, code, message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "INVALID_REQUEST", "올바르지 않은 요청입니다.")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        # Do not copy arbitrary exception details into the API response or app log.
        logger.error("Health request failed (%s)", type(exc).__name__)
        return error_response(500, "INTERNAL_ERROR", "상태 확인 중 오류가 발생했습니다.")

    return app


app = create_app()
