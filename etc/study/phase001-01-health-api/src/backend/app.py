# 학습용 사본 — 실행/테스트에서 참조하는 구현 기준이 아닙니다.
# 주제: Client–Backend HTTP와 FastAPI
# 원본 경로: src/backend/app.py
# 원본 브랜치: chore/phase1-preparation
# 원본 commit SHA: 011095a7db696e558c70b2e566d1b25cb78ddb6c
# 복사 날짜: 2026-10-15 (Asia/Seoul)
# 원본과 다른 점: 한국어 설명 주석만 추가. 코드·문자열·기존 docstring은 보존.
# 읽는 방법: 번호가 붙은 주석을 따라가고 같은 폴더의 explanation.md를 함께 읽습니다.
# import는 실제 프로젝트 패키지를 가리킵니다. 이 사본은 독립 실행용 앱/테스트가 아닙니다.

"""Local HTTP boundary; no UI or collection dependencies."""

# [1단계: HTTP 경계에 필요한 도구 가져오기]
# logging은 개발자용 진단, asdict는 dataclass를 사전으로 변환하는 기능이다.
# importlib.metadata.version은 설치된 배포 패키지의 버전 정보를 읽는다.
# 이 모듈은 GUI 위젯이나 Windows 창 감지기를 가져오지 않는다.
import logging
from dataclasses import asdict
from importlib.metadata import version

# FastAPI는 경로와 예외 처리기를 묶는 앱 객체를 만든다.
# Request는 들어온 HTTP 요청의 타입이다. 아래 핸들러에서 인자로 받지만 현재 사용하지 않는다.
# JSONResponse는 HTTP 상태 코드·헤더·JSON 본문을 직접 지정할 때 사용한다.
# Starlette의 HTTPException을 받아 프레임워크가 만든 404/405도 같은 형태로 바꾼다.
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

# 응답 모양은 shared/protocol.py에 정의되어 있다.
# 성공은 HealthResponse(data=HealthStatus(...)), 실패는 ErrorResponse(error=ApiError(...))다.
# API를 만드는 코드와 데이터 구조를 나누어 클라이언트와 같은 규격을 공유한다.
from shared.protocol import ApiError, ErrorResponse, HealthResponse, HealthStatus

# __name__은 이 모듈의 이름이다. 어느 모듈에서 발생한 로그인지 구분할 수 있게 한다.
# 여기서는 로거만 얻는다. 서버 실행이나 로그 파일 생성이 시작되는 것은 아니다.
logger = logging.getLogger(__name__)


# [2단계: 상태 응답 데이터 만들기]
# 입력 인자는 없고 HealthResponse 객체를 반환한다. 아직 HTTP 바이트를 직접 쓰지 않는다.
# 안쪽 HealthStatus에 패키지 버전을 넣고, 바깥 HealthResponse의 기본 ok/error를 사용한다.
# 프로젝트가 설치되지 않으면 version('contexttrace')에서 패키지 조회 오류가 날 수 있다.
# '서버가 실행 중'이라는 상태이지, 후속 Phase의 모든 기능이 완성되었다는 뜻은 아니다.
def get_health() -> HealthResponse:
    return HealthResponse(data=HealthStatus(version=version("contexttrace")))


# [3단계: 모든 오류의 바깥 형태를 통일하기]
# status는 HTTP 상태 코드, code는 프로그램이 구분할 오류 코드, message는 안내 문구다.
# headers는 헤더 사전 또는 None이다. dict[str, str] 표기 자체가 값을 검사하지는 않는다.
# 404·405·422·500 핸들러가 이 함수를 재사용해 각기 다른 JSON 형태가 생기지 않게 한다.
def error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        # 안쪽 오류 객체를 바깥 응답에 담고 asdict로 중첩 dataclass까지 사전으로 바꾼다.
        # 예: {'ok': False, 'data': None, 'error': {'code': 'NOT_FOUND', 'message': '...'}}.
        # JSONResponse는 이 사전을 JSON 본문으로 만들고 None을 null로 표현한다.
        # HTTP status_code와 본문의 error.code는 서로 다른 정보다.
        content=asdict(ErrorResponse(error=ApiError(code=code, message=message))),
        headers=headers,
    )


# [4단계: 앱을 만들고 처리할 주소를 등록하기]
# 앱 팩토리 함수다. 호출할 때마다 별도 FastAPI 앱을 만들 수 있어 테스트에도 유리하다.
# docs/redoc/openapi 주소를 끄고, 뒤의 '/' 유무로 자동 이동시키는 동작도 끈다.
# 이것만으로 인증이나 접근 제어가 생기지는 않는다. 서버 bind 주소는 진입점의 책임이다.
def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    # 장식자는 GET /health 요청을 health 함수와 연결한다.
    # 이 시점에는 경로를 등록하며 함수 본문은 요청이 들어왔을 때 실행한다.
    # response_model은 성공 응답의 검증·직렬화에 쓰인다.
    # async def는 코루틴 함수 선언이다. 이 짧은 함수에는 await나 별도 스레드 생성이 없다.
    # 비동기 함수라는 이유만으로 내부의 무거운 동기 작업까지 비차단으로 바뀌지는 않는다.
    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return get_health()

    # [5단계: HTTP 오류를 공통 응답으로 변환하기]
    # 주소가 없으면 404, 메서드가 맞지 않으면 405 등을 이 처리기가 받는다.
    # .get(key, fallback)은 알려진 상태 코드의 문구를 고르고 없으면 일반 문구를 사용한다.
    # exc.headers도 전달해 원래 오류의 필요한 HTTP 헤더를 보존한다.
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code, message = {
            404: ("NOT_FOUND", "요청한 경로를 찾을 수 없습니다."),
            405: ("METHOD_NOT_ALLOWED", "지원하지 않는 요청 방식입니다."),
        }.get(exc.status_code, ("HTTP_ERROR", "요청을 처리할 수 없습니다."))
        return error_response(exc.status_code, code, message, exc.headers)

    # 요청 인자 검증에 실패하면 422와 INVALID_REQUEST로 통일한다.
    # 이 health 경로 자체에는 입력 필드가 없지만 앱의 공통 예외 처리 기준을 둔 것이다.
    # 검증 예외의 원문에는 입력값이 포함될 수 있으므로 그대로 응답에 넣지 않는다.
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "INVALID_REQUEST", "올바르지 않은 요청입니다.")

    # 예상하지 못한 서버 오류는 500과 INTERNAL_ERROR로 처리한다.
    # 사용자에게는 고정 문구를 보내고, 로그에는 예외 타입명만 남긴다.
    # traceback·로컬 경로·임의의 예외 메시지를 이 응답 본문에 복사하지 않는다.
    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        # Do not copy arbitrary exception details into the API response or app log.
        logger.error("Health request failed (%s)", type(exc).__name__)
        return error_response(500, "INTERNAL_ERROR", "상태 확인 중 오류가 발생했습니다.")

    # 등록이 끝난 앱을 호출자에게 넘긴다. 이 함수 안에서 서버를 실행하지는 않는다.
    return app


# [6단계: 모듈에서 사용할 앱 인스턴스 준비]
# import 시 앱 생성과 경로 등록은 일어나지만 네트워크 서버가 시작되지는 않는다.
# python -m backend 실행 시 진입점이 Uvicorn으로 이 앱을 서비스한다.
# 요청 순서: GET /health 수신 → health() → get_health() → 모델 직렬화 → 응답 전송.
app = create_app()
