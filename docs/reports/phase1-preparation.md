# Phase 1 준비 검증 결과

기준일: 2026-09-19 KST
기준 main: `942cc2c5ce96cd4142837ef4a0c852727af661c6`
작업 브랜치: `chore/phase1-preparation`

## 변경

- PySide6 임시 구성안과 이번 Backend/통신 구현 선택 기록. 사용자 최종 선택은 미확인.
- pyproject의 설치 설정, 실행/개발 의존성, pytest/Ruff 설정 추가.
- 기존 src 구조를 유지하고 Client/Backend/Shared의 패키지 경계 추가.
- Windows 설치 절차, 상태 API 계약, 작은 구현 순서, 실패 시나리오 작성.
- 기존 기획/추상설계와 Phase 원문 체크리스트 보존.

## 수행한 검증

검증 환경: Linux, Python 3.12.14, 새 `.venv`.

| 검증 | 결과 |
|---|---|
| `python -m pip install -e '.[dev]'` | 성공 |
| `python -m pip check` | 의존성 충돌 없음 |
| QtCore/QtWidgets/QtNetwork, fastapi, uvicorn import | 성공 |
| client/backend/shared import | 성공 |
| `python -m ruff check src tests` | 통과 |
| `git diff --check` | 통과 |

설치 확인 버전: PySide6 6.11.2, FastAPI 0.141.1, Uvicorn 0.53.0.
이 값은 이번 환경에서 확인한 값이며 Windows 검증 또는 lock 파일을 의미하지 않는다.

## 아직 검증하지 않은 항목

- Windows 10/11 설치 및 실제 UI 표시
- Python 3.11에서의 설치 및 실행
- Backend 서버와 Client의 독립 실행
- 실제 HTTP 왕복 및 실패/복구 시나리오
- 동작 테스트 및 CI

실행 기능은 아직 작성하지 않았으므로 앱 실행, 기능 테스트, Phase 1 완료를 주장하지 않는다.
다음 작업은 `phase1-preparation.md`의 1A(shared 응답 구조 + Backend /health)다.
