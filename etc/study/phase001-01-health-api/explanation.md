# 학습 주제: Client–Backend HTTP와 FastAPI

Phase 001 학습 자료 · `chore/study-workspace`

## 0. 출처와 범위

- 원본 경로: `src/backend/app.py`
- 원본 브랜치: `chore/phase1-preparation`
- 원본 commit SHA: `011095a7db696e558c70b2e566d1b25cb78ddb6c`
- 원본 blob SHA: `0d831ef1082bfdfa69ae7c24571f86b35b51a2cd`
- 복사 날짜: 2026-10-15 (Asia/Seoul)
- 사본 파일: [src/backend/app.py](src/backend/app.py)
- 자료 정리일: 2026-10-16 (Asia/Seoul)
- 보관 브랜치: `chore/study-workspace`
- [전체 학습 순서](../00-learning-path.md) · [Study 안내](../README.md)
- [원본 고정 스냅샷](https://github.com/rkdduswns/AICapstone/blob/011095a7db696e558c70b2e566d1b25cb78ddb6c/src/backend/app.py)
- 원본과 다른 부분: 단계별 한국어 `#` 주석만 추가했습니다. 실행 코드, 문자열, 기존 docstring을 보존했습니다.

이 자료는 해당 브랜치·커밋의 학습용 스냅샷입니다. `src/`와 `tests/`의 구현 기준으로 참조하거나 자동 동기화하지 않습니다.
원래 import 경로도 보존했으므로 사본은 독립 실행용 프로젝트가 아닙니다. 실제 코드/테스트에서는 이 사본을 import하거나 실행하지 않습니다.

## 1. 코드가 해결하는 문제

로컬 Backend가 실행 중인지 확인하는 GET /health와 공통 오류 응답을 제공합니다. GUI나 수집 기능과 분리된 가장 작은 HTTP 경계입니다.

## 2. 먼저 알아야 할 개념

- HTTP 상태 코드와 JSON 본문은 서로 다른 정보입니다.
- `@app.get(...)`은 주소에 함수를 등록하는 장식자입니다.
- `async def`는 코루틴 선언이며 자동 스레드 생성이나 내부 동기 작업의 비차단화를 뜻하지 않습니다.
- `asdict()`는 중첩 dataclass를 사전으로 변환합니다.
- `create_app()`은 구성된 앱을 반환하는 팩토리이고, `app = create_app()` 자체는 서버 기동 명령이 아닙니다.

## 3. 전체 실행 순서

1. 서버 진입점이 이 모듈의 앱을 사용합니다. import 시 앱 생성과 경로 등록이 이루어집니다.
2. `GET /health`가 들어오면 등록된 `health()`가 호출됩니다.
3. `get_health()`가 설치된 `contexttrace` 패키지 버전을 조회합니다.
4. `HealthStatus`를 `HealthResponse`에 담아 반환합니다.
5. FastAPI가 성공 응답 모델을 직렬화해 HTTP 응답으로 전송합니다.
6. 경로/메서드/입력 검증/내부 오류는 각각의 예외 처리기를 거쳐 공통 JSON 형태가 됩니다.

## 4. 함수별 / 코드 블록별 설명

| 함수 | 입력 | 출력/설계 이유 |
|---|---|---|
| `get_health` | 없음 | 버전과 서비스 상태 모델. 통신 처리와 데이터 생성을 분리합니다. |
| `error_response` | 상태 코드, 오류 코드/문구, 선택적 헤더 | 공통 JSONResponse. 예외 종류마다 형식이 갈라지지 않게 합니다. |
| `create_app` | 없음 | 경로와 예외 처리기가 등록된 FastAPI 객체. |
| `health` | HTTP 요청에 대응한 호출 | 상태 모델을 반환합니다. |
| `http_error` | HTTPException | 404/405 등을 프로젝트 오류 형식으로 바꿉니다. |
| `validation_error` | RequestValidationError | 422 응답으로 통일합니다. |
| `internal_error` | 예상하지 못한 Exception | 500과 고정 문구를 반환합니다. |

## 5. 하나의 예시를 끝까지 따라가기

설치된 앱 버전이 `0.1.0`이고 `/health` 요청이 성공하면 HTTP 200과 다음 본문을 받습니다. JSON 필드 순서는 의미가 없습니다.

```json
{"ok":true,"data":{"version":"0.1.0","service":"contexttrace-backend","status":"running","api_version":1},"error":null}
```

없는 주소를 요청하면 HTTP 404와 `ok:false`, `data:null`, `error.code:NOT_FOUND`를 받습니다.
실제 상태 코드를 200으로 유지한 채 본문 문구만 바꾸는 흐름이 아닙니다.

## 6. 실패 및 경계 상황

- 패키지 메타데이터가 설치되지 않았으면 버전 조회가 실패할 수 있습니다. 설치 방법은 해당 브랜치의 개발 환경 문서를 따릅니다.
- 이 상태 응답만으로 Windows 감지·저장 기능의 완성을 판단할 수 없습니다.
- `/health`와 `/health/`의 자동 리다이렉트는 비활성화되어 있습니다.
- RequestValidationError 처리는 공통 기준입니다. 입력 인자가 없는 health 요청으로 모든 검증 오류가 발생하는 것은 아닙니다.
- 서버 시작/포트/bind 주소는 `src/backend/__main__.py`의 책임입니다.

## 7. 이해 확인과 작은 실습

1. `app = create_app()`이 실행되면 무엇이 준비되고, 무엇은 아직 시작되지 않는지 설명합니다.
2. 성공 모델과 JSONResponse 오류 응답이 만들어지는 경로를 각각 따라갑니다.
3. HTTP 404와 `error.code`의 차이를 적습니다.
4. 이해 기준: 버튼에서 보낸 요청이 어떤 함수로 연결되어 어떤 형태로 반환되는지 설명할 수 있습니다.

## 검증 범위

- 원본 blob SHA를 확인하고 사본의 Python 문법을 파싱했습니다.
- 원본/사본의 AST와 주석을 제외한 실행 토큰을 비교했습니다. 주석 이외의 코드 변경은 없습니다.
- 학습 자료 작성은 기능 구현/Phase 완료 처리와 별개입니다. 사본을 실행하거나 새 Windows 동작 검증을 수행한 것은 아닙니다.
- 자세한 줄별 설명은 사본 코드의 번호 주석을 따라 읽습니다.
