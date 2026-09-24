# Phase 2A — Client 우선 구현 및 현재 상태

기준일: 2026-09-24. Phase 2A 구현 및 가상 HTTP 검증 완료. Phase 2 전체는 IN_PROGRESS.

## 저장소 재확인

- 저장소: `rkdduswns/AICapstone`, default branch: `main`.
- 시작 SHA: `efafd8e489ef87e42679495ad675c27261feccb5`.
- 최신 변경: `feat: complete Phase 1 client-backend connection (#1)`, 2026-09-24.
- 시작 시 열린 PR 없음. Phase 1 DONE, Phase 2 미시작 상태에서 Client 우선 진행 지시를 적용했다.
- `README`, `etc/개발-지침.md`, 기획/추상설계, Phase 1/2/3, `docs/dev`, Phase 1 검증 보고서,
  실제 코드 및 테스트를 확인했다. `docs/wiki`는 없고 기획은 `etc/`에 있다.

| 인수인계 항목 | 최신 저장소에서 확인한 내용 | 판정 |
|---|---|---|
| client/backend 최상위 경로 | `src/client`, `src/backend`, `src/browser`, `src/shared` | REPO_NEWER |
| Client 기술 미확정 | PySide6 Widgets 확정, QtNetwork 비동기 HTTP 사용 | REPO_NEWER |
| Python Backend | FastAPI/Uvicorn, loopback HTTP | MATCH 및 구체화 |
| 재구성 Phase 2 = Backend 기반 | 실제 Phase 2 = Windows 활성 창 감지 | REPO_NEWER |
| 현재 구현/테스트 미확인 | Phase 1 완료, 기존 테스트 27개 | REPO_NEWER |
| 저장·검색·AI 모델 구성 | 기획은 있으나 구현 없음. DB/LLM 제품은 이번 작업에서 확정하지 않음 | 미구현 |

기획 및 개발 지침의 Client UI / Backend 수집 책임 분리와 코드는 일치한다.
새 규격은 `docs/dev/current-activity-api.md`에 분리했고 원본 기획/추상설계는 수정하지 않았다.

## 구현 범위

- 프로그램명, 프로세스명/PID, 창 제목, 수집 상태, 마지막 정상 수신 시각 표시.
- `/health` 검증 후 `/activity/current` 조회. 응답 완료 1초 뒤 자동 갱신, 전체 요청 3초 timeout.
- 활성 창 없음/미지원/감지 오류/HTTP 오류/연결 단절/잘못된 응답 처리와 자동 복구.
- 실패 시 이전 창 정보 제거. 재확인/종료 시 진행 중 요청과 타이머 취소.
- 공통 `ActiveWindow`, `CurrentActivity`, `CurrentActivityResponse` dataclass.
- 두 API의 중복 전송 코드를 `JsonRequest`로 분리하고 Phase 1의 기존 표시/검증 동작 유지.
- 가상 데이터만 제공하는 미리보기 도구. 실제 Backend 코드나 의존성 목록 변경 없음.
- 작성/수정한 함수와 주요 비동기 흐름에 한국어 설명 추가.
- Windows CI를 main PR과 main push에서도 실행하도록 확장하고 tools 정적 검사 포함.

## 로컬 검증 결과

- 환경: Windows 10 build 19045, Python 3.14.7, PySide6/Qt 6.11.2, 기본 Windows Qt 플랫폼.
- `python -m pytest -q`: **72 passed**, 26.52s (동일 제목의 선택·스크롤 보존 검증 포함).
- `python -m ruff check src tests tools`: 통과.
- `python -m pip check`: 통과.
- 가상 데이터를 통한 실제 Qt 화면 이미지 확인: 한글, 프로그램/제목/상태 영역, 줄바꿈 배치 정상.
- 기존 Starlette/httpx deprecation warning 1건. 이번 작업에서 의존성 변경은 하지 않았다.
- 최초 제한 환경 실행은 69개 통과, 임시 디렉터리 접근 제한으로 2개 setup 오류가 있었다.
  접근 가능한 환경에서 전체 71개를 다시 실행해 통과했다.
  이후 동일 제목의 사용자 선택·스크롤 보존과 종료 테스트의 서버 수신 시점 동기화를 보완하고
  전체 72개를 재검증했다.

검증 내용:

- Chrome→VS Code, Word→Explorer, 동일 창 유지의 가상 응답을 실제 loopback HTTP로 전달.
- 활성 창 없음, 미지원, 감지 오류 시 이전 프로그램/제목 제거.
- API/서비스/필수 필드/상태 조합 검증, 빈 제목, 긴 한글 제목, HTML 형태 문자열의 plain text 표시.
- 동일 제목 반복 수신 시 텍스트 선택 및 스크롤 위치 유지.
- HTTP 404/500/302, 전송 실패, 잘못된 JSON/Content-Type, timeout 및 자동 복구.
- 느린 요청 중복 방지, Qt 이벤트 루프 생존, 재확인 시 이전 요청 취소, 종료 후 재조회 방지.
- 실제 Phase 1 Backend 별도 프로세스의 연결/종료/재시작과 `기능 준비 중` 표시.

Windows 10의 자동 UI/HTTP 테스트이며 사람이 실제 Chrome/Word 창을 전환한 검증은 아니다.
Phase 2의 Windows 11 수동 검증 및 실제 감지기 연동 결과도 아직 없다.

## 실행 및 후속 작업

설치 방식: `pyproject.toml` + pip editable install. Python 최소 버전은 3.11을 유지한다.
진입점: `python -m backend`, `python -m client`. 패키징/설치 프로그램은 아직 없다.
미리보기: `python tools/preview_phase2_client.py` (별도 Backend 불필요).

다음 최소 작업은 **Phase 2B Backend 활성 창 감지 + 현재 창 API**다.
`src/shared/activity.py`와 [현재 창 계약](../dev/current-activity-api.md)을 기준으로 구현한다.
그 뒤 Phase 2C에서 실제 창 전환/바탕화면/종료 프로그램을 검사하고 Phase 2 완료 여부를 판단한다.
