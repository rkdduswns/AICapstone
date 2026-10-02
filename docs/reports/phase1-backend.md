# Phase 1A — 공통 응답 및 Backend 상태 API

작업 브랜치: `chore/phase1-preparation`.
이 보고서는 Backend 구현 단계의 검증 기록이다. Phase 1 최종 완료 결과는
[Client 및 Windows 검증](phase1-client-windows.md)을 따른다.

## 초기 환경 검증

Linux / Python 3.12.14의 새 가상환경에서 editable 설치, pip check,
QtCore/QtWidgets/QtNetwork·FastAPI·Uvicorn 및 프로젝트 패키지 import, Ruff, diff 검사를 통과했다.
설치 확인 버전은 PySide6 6.11.2, FastAPI 0.141.1, Uvicorn 0.53.0이다.
이는 2026-09-19 환경 기록이며 Windows 실행 검증이나 버전 고정을 의미하지 않는다.

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

## 검증 범위

이 단계는 Linux의 Shared 응답 구조와 Backend 실행/API 검증을 다룬다.
Client UI, Windows 실행 및 연결 실패·복구 검증은 [후속 보고서](phase1-client-windows.md)에 기록했다.
