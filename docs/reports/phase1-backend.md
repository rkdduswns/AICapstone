# Phase 1A — 공통 응답 및 Backend 상태 API

## 준비 재확인

- 최신 main: `942cc2c5ce96cd4142837ef4a0c852727af661c6`.
- 작업 브랜치 원격 기준: `3292a1d10540b3befdf3ca35ba8d8d0e3d49ce08`.
- 로컬 준비 결과의 tree와 원격 커밋 tree 일치 확인.
- 기존 기획·지침·Phase 1·통신 규격과 설치 의존성 재확인. 1A 진행을 막는 항목 없음.
- Client PySide6 최종 선택은 미확인이나 Backend와 독립되어 1A 진행 가능.
- 사용자 결정: Phase 1 개발 및 테스트 완료 후 main 병합. Draft PR #1에서 계속 작업.

## 구현

- `src/shared/protocol.py`: 프레임워크 독립적인 정상/실패 응답 및 상태 dataclass.
- `src/backend/app.py`: GET /health, 404/405/422/500 공통 JSON 응답. 내부 오류 상세를 응답에서 제외.
- `src/backend/__main__.py`: 독립 실행, loopback 고정, --port 검증. Uvicorn 시작/종료/바인딩 오류 로그.
- 앱 버전은 설치 메타데이터 사용. 새로운 의존성 추가 없음.

## 검증

환경: Linux / Python 3.12.14.

| 검사 | 결과 |
|---|---|
| pip check | 의존성 충돌 없음 |
| pytest -q | 13개 통과 |
| ruff check src tests | 통과 |
| git diff --check | 통과 |
| 별도 프로세스 HTTP | 정상 상태, 404, 405 및 후속 정상 요청 통과 |
| 시작/종료 | 잘못된 포트 4종, 점유 포트 실패, SIGTERM 정상 종료 로그 확인 |
| 내부 오류 | 500 응답의 상세 정보 비노출 및 정상 요청 복구 확인 |

테스트 실행 시 설치된 Starlette의 httpx 및 AnyIO 관련 deprecation warning 2건이 발생했다.
현재 테스트 실패는 없으며 이 단계에서 의존성을 임의 교체하지 않았다.

## 완료 범위 및 다음 작업

1A는 Linux 기준 구현·검증 완료. Phase 1 전체는 IN_PROGRESS.
Windows 10/11 및 Python 3.11 실행, Client UI, 연결 실패/복구, CI는 미검증 또는 미구현이다.
다음은 1B Client 진입점 및 상태 화면이며 최종 Client 기술을 확인해야 한다.
기존 Phase 1 완료 체크리스트는 Windows와 Client 검증 전 완료 처리하지 않는다.
