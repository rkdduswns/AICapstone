# Phase 순서로 보는 Study

정리일: 2026-10-16 (Asia/Seoul) · 보관 브랜치: `chore/study-workspace`

학습용 코드 사본 6개와 단계별 해설을 이 브랜치의 `etc/study/`에 모았습니다.
폴더명은 `phaseNNN-SS-주제` 형식으로, Phase 번호와 같은 Phase 안의 순서가 이름순 정렬에 반영됩니다.
각 행의 해설과 주석 코드를 같은 브랜치 안에서 바로 열 수 있습니다.

## Phase별 자료

| Phase | 폴더 | 학습 내용 | 해설 | 주석 코드 |
|---|---|---|---|---|
| 001 | `phase001-01-health-api` | HTTP와 FastAPI 상태 API | [해설](phase001-01-health-api/explanation.md) | [app.py](phase001-01-health-api/src/backend/app.py) |
| 002 | `phase002-01-async-http` | 비동기 HTTP·시간 초과·취소 | [해설](phase002-01-async-http/explanation.md) | [json_request.py](phase002-01-async-http/src/client/json_request.py) |
| 002 | `phase002-02-response-validation` | 응답 검증과 오류 처리 | [해설](phase002-02-response-validation/explanation.md) | [backend_client.py](phase002-02-response-validation/src/client/backend_client.py) |
| 003 | `phase003-01-python-data` | Python 데이터 모델과 시간 정보 | [해설](phase003-01-python-data/explanation.md) | [activity.py](phase003-01-python-data/src/shared/activity.py) |
| 004 | `phase004-01-qt-events` | Qt 이벤트와 화면 상태 | [해설](phase004-01-qt-events/explanation.md) | [window.py](phase004-01-qt-events/src/client/window.py) |
| 004 | `phase004-02-client-tests` | pytest와 비동기 UI 테스트 | [해설](phase004-02-client-tests/explanation.md) | [test_connection.py](phase004-02-client-tests/tests/client/test_connection.py) |

## 순서대로 읽기

1. **Phase 001**: `/health` 요청과 FastAPI의 성공/오류 응답을 읽습니다.
2. **Phase 002**: 비동기 요청이 시작되고, 응답/시간 초과/취소 후 정리되는 순서를 확인합니다. 다음으로 서버 식별·필드·타입을 검증하는 과정을 읽습니다.
3. **Phase 003**: 현재 창과 시간 정보를 묶는 dataclass, 타입 힌트, None과 기본값의 차이를 확인합니다. Python 문법이 낯설면 이 주제를 먼저 훑어도 됩니다.
4. **Phase 004**: 버튼·통신 결과·화면 갱신·종료 이벤트를 연결해 읽은 뒤, 이를 가상 서버와 실제 프로세스로 시험하는 테스트를 읽습니다.

각 주제는 `explanation.md`의 실행 순서와 코드의 번호 주석을 함께 읽습니다. 해설 마지막에는 예시와 이해 확인 질문이 있습니다.
완료 기준은 버튼 클릭부터 요청·검증·표시·취소까지 설명하고, 서버 없음/응답 지연/잘못된 JSON의 결과를 예상할 수 있는 것입니다.

## 원본과 학습 사본

- 이번 정리는 보관 위치와 안내 링크를 바꾸는 작업입니다. 기존 Python 사본의 코드·주석과 원본 커밋 정보는 그대로 유지합니다.
- Phase 003 모델은 Phase 2의 현재 창 정의에 Phase 3 시간 정보가 추가된 시점이고, Phase 004 화면/테스트는 Phase 4 시점입니다.
- 최신 main과 자동 동기화된 구현 코드가 아닙니다. 원본 경로·브랜치·commit SHA·최초 복사 날짜는 각 사본과 해설에서 확인합니다.
- 원본 소스는 해당 브랜치에 유지합니다. 분산되어 있던 학습용 파일은 이곳으로 이동하고 기존 네 브랜치의 중복 사본을 정리합니다.
- 사본은 읽기용 자료입니다. 실제 `src/`, `tests/`에서 import·실행·테스트 데이터로 사용하지 않습니다.
- [Study 작성 규칙](README.md) · [해설 양식](TEMPLATE.md)

## 검증 범위

- 코드 사본 6개는 이동 전후 바이트와 blob SHA를 비교하고 Python 문법/AST를 검사합니다.
- 원본 경로와 commit SHA, 상세 주석 및 해설 본문을 보존하고 탐색 링크를 검사합니다.
- 변경은 `etc/study/`에만 적용합니다. 개발 코드, 테스트, 설정, Phase 진행 상태는 이 학습 정리로 변경하지 않습니다.
