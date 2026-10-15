# Study 학습 순서와 브랜치별 자료

작성일: 2026-10-15 (Asia/Seoul). 아래 6개 주제는 원본이 구현된 각 브랜치의 `etc/study/`에 추가했습니다.
기존 실행 코드와 테스트는 수정하지 않습니다. 각 사본에는 원본 경로·브랜치·commit SHA·복사 날짜와 단계별 한국어 주석을 기록합니다.

## 권장 학습 순서

| 순서 | 주제 | 작업 브랜치 | 해설 | 주석 사본 |
|---|---|---|---|---|
| 001 | Python 데이터 구조 | `feat/phase3-client` | [explanation.md](https://github.com/rkdduswns/AICapstone/blob/feat/phase3-client/etc/study/001-python-data/explanation.md) | [activity.py](https://github.com/rkdduswns/AICapstone/blob/feat/phase3-client/etc/study/001-python-data/src/shared/activity.py) |
| 002 | Client–Backend HTTP와 FastAPI | `chore/phase1-preparation` | [explanation.md](https://github.com/rkdduswns/AICapstone/blob/chore/phase1-preparation/etc/study/002-health-api/explanation.md) | [app.py](https://github.com/rkdduswns/AICapstone/blob/chore/phase1-preparation/etc/study/002-health-api/src/backend/app.py) |
| 003 | PySide6 이벤트와 화면 상태 | `feat/phase4-client` | [explanation.md](https://github.com/rkdduswns/AICapstone/blob/feat/phase4-client/etc/study/003-qt-events/explanation.md) | [window.py](https://github.com/rkdduswns/AICapstone/blob/feat/phase4-client/etc/study/003-qt-events/src/client/window.py) |
| 004 | 비동기 HTTP·timeout·자원 정리 | `feat/phase2-client` | [explanation.md](https://github.com/rkdduswns/AICapstone/blob/feat/phase2-client/etc/study/004-async-http/explanation.md) | [json_request.py](https://github.com/rkdduswns/AICapstone/blob/feat/phase2-client/etc/study/004-async-http/src/client/json_request.py) |
| 005 | 응답 검증과 오류 분류 | `feat/phase2-client` | [explanation.md](https://github.com/rkdduswns/AICapstone/blob/feat/phase2-client/etc/study/005-response-validation/explanation.md) | [backend_client.py](https://github.com/rkdduswns/AICapstone/blob/feat/phase2-client/etc/study/005-response-validation/src/client/backend_client.py) |
| 006 | pytest와 비동기 UI 테스트 | `feat/phase4-client` | [explanation.md](https://github.com/rkdduswns/AICapstone/blob/feat/phase4-client/etc/study/006-client-tests/explanation.md) | [test_connection.py](https://github.com/rkdduswns/AICapstone/blob/feat/phase4-client/etc/study/006-client-tests/tests/client/test_connection.py) |

## 첫 연결 흐름을 읽는 방법

1. 001에서 `None`, 기본값, dataclass, 타입 힌트의 의미를 익힙니다.
2. 002에서 `/health` 요청과 성공/오류 응답 모양을 확인합니다.
3. 003에서 버튼 클릭, 결과 표시, 후속 조회 시작, 화면 종료의 이벤트를 찾습니다.
4. 004에서 요청 등록 이후 제어가 돌아가고 나중에 신호가 오는 과정을 추적합니다.
5. 005에서 HTTP 성공과 응답 내용 검증 성공의 차이를 확인합니다.
6. 006에서 위 흐름을 가상 서버와 실제 프로세스로 어떻게 시험하는지 읽습니다.

완료 기준: 버튼 클릭부터 응답·내용 검증·화면 갱신·취소까지 누가 무엇을 호출하는지 설명하고, 서버 없음/응답 지연/잘못된 JSON일 때의 결과를 예상할 수 있습니다.

## 브랜치와 병합 범위

- 각 주제는 서로 다른 새 디렉터리를 사용합니다. 여러 브랜치에서 공통 study README나 같은 학습 파일을 동시에 편집하지 않습니다.
- 이 안내 문서는 `chore/phase1-preparation`에만 추가합니다. 모든 자료가 병합되기 전에도 위 브랜치 링크로 각각 열 수 있습니다.
- 자료의 원본 커밋은 작성 당시 스냅샷입니다. 이후 브랜치가 바뀌더라도 출처를 자동 갱신하지 않습니다.
- 새 study 파일 간 경로 중복을 검사합니다. 기존 개발 변경이나 미래의 다른 변경까지 충돌이 없다고 보장하는 것은 아닙니다.
- `main`의 study README/AGENTS 지침에 따라 사본을 실행 코드·테스트·패키지의 구현 근거로 사용하지 않습니다.
- 이전 작업 브랜치에는 최신 main의 study 제외 설정이 아직 없을 수 있습니다. 원본 검증 명령은 `python -m pytest tests`, `python -m ruff check src tests`처럼 구현 경로를 명시하고 이 학습 사본을 실행하지 않습니다.

## 검증

- Python 사본 6개: 문법 파싱, 원본과 AST 동일성, 주석 제외 실행 토큰 동일성을 확인합니다.
- 사본의 출처 blob SHA와 고정 commit SHA를 기록합니다.
- 원본 src/tests/config 파일의 변경 없이 study 경로에만 추가합니다.
- 이번 학습 작업으로 기능 테스트 결과나 개발 Phase 완료 상태를 새로 선언하지 않습니다.
