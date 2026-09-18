# Phase 1 진입 준비

기준: 2026-09-19 KST / main `942cc2c5ce96cd4142837ef4a0c852727af661c6`

## 목적과 현재 상태

원본 [Phase 1](phase1.md)의 목표는 Client와 Backend의 독립 실행 및 상태 요청/응답이다.
이번 변경은 개발 환경, 인터페이스, 작업 순서의 준비이며 Phase 1 기능 완료가 아니다.
원본 기획 및 추상설계와 Phase 체크리스트는 보존한다.

## 인수인계 대조

| 항목 | 확인 결과 및 적용 기준 |
|---|---|
| 저장소 접근 | main 및 전체 트리 열람 가능. 인수인계의 접근 불가 상태는 해소 |
| 구조 | 실제 `src/client`, `src/backend`, `src/shared`, `src/browser`를 유지 |
| Phase | 인수인계의 재구성 0–9 대신 저장소의 1–14를 적용 |
| 제품 | Windows 작업 이력의 실제 출처를 찾는 ContextTrace |
| Python | 기존 `requires-python >=3.11` 유지 |
| Client | 저장소에는 미정. 준비 초안은 PySide6로 구성. 사용자 최종 선택은 확인되지 않음 |
| 기존 구현 | 소스·테스트·CI는 자리표시자뿐. 실행 진입점과 의존성 없음 |
| 현재 작업 | Phase 1 준비 진행. 완료된 기능 Phase는 확인되지 않음 |
| 원문 간 차이 | 기획은 PDF/DOCX를 핵심 안정화 후 추가로 분류하지만 Phase 9는 검색 Phase보다 앞에 배치. 해당 Phase 진입 전 MVP 순서 재검토; 이번 연결 작업에는 영향 없음 |
| 개인정보 순서 | 기획/지침은 저장 전 보호 검사 필수이나 Phase 4 저장, Phase 5 보호 순서. Phase 4까지 가상 데이터로 검증하고 실제 사용자 기록 저장 전 보호 적용 필요 |

## 구성 결정과 범위

| 항목 | 이번 구성 | 결정 근거 |
|---|---|---|
| Client | PySide6 Widgets (임시 구성안) | Python 환경 공유 및 상태 화면 구성. 사용자 최종 선택 확인 필요 |
| Backend | FastAPI + Uvicorn | 상태 API 및 후속 Backend 인터페이스를 명시적으로 분리하기 위한 구현 선택 |
| 통신 | 별도 프로세스, loopback HTTP/JSON | 독립 실행 및 연결 실패를 검증 가능 |
| Client HTTP | PySide6 QtNetwork | UI를 막지 않는 요청; 별도 런타임 HTTP 라이브러리 추가 불필요 |
| 환경 | Python 3.11 이상, venv + pip | 기존 Python 조건을 유지. 실제 검증 버전은 결과 문서에 기록 |
| 개발 도구 | pytest, httpx, Ruff | API 테스트와 정적 검사. httpx는 개발 의존성 |
| 공통 정의 | `src/shared` | 응답 데이터만 공유; Client의 Backend 내부 import 금지 |
| 실행 정책 | 각각 수동 실행 | 자동 서버 기동/종료 관리는 후속 필요 발생 시 검토 |

DB, 모델/API 키, RAG, 브라우저 확장, Windows 수집 라이브러리는 이번에 추가하지 않는다.
FastAPI 선택은 이번 준비의 구현 결정이며 과거에 확정된 기술이라고 간주하지 않는다.

## 선행조건

- [x] 인수인계 및 최신 main 대조
- [x] README, 개발 지침, 기획, Phase 1/2와 전체 Phase 목록 확인
- [ ] Client 기술 최종 선택 (현재 설치 설정은 PySide6 임시 구성안)
- [x] 설치 설정 및 통신 규격 작성
- [ ] Windows 10/11에서 개발 환경 설치 재현
- [ ] 공동 개발자가 통신 규격을 PR에서 검토

## 작은 작업 단위

| 순서 | 목적 / 구현 범위 | 검증 및 완료 조건 |
|---|---|---|
| 1A | shared 상태 응답 구조, Backend 진입점, GET /health, 예외 응답 | Backend 단독 실행; 정상/404/내부 오류 응답의 계약 검증 |
| 1B | Client 진입점, 상태 라벨·확인 버튼, QtNetwork 요청 | Client 단독 실행; 연결 중/성공/실패 표시, UI 응답 유지 |
| 1C | Client–Backend 실제 연결, timeout·실패·복구 | 실제 HTTP 왕복; Backend 종료 후 실패 표시; 재실행 후 수동 재확인 성공 |
| 1D | Windows 실행 검증 및 결과 기록 | 원본 Phase 1 완료 조건을 증거와 함께 체크 |

Client 1B 구현 전 PySide6 채택 여부를 확정한다. 현재 준비 설정은 변경 가능하며 사용자 확정으로 취급하지 않는다.

1A의 계약을 먼저 맞춘 뒤 Client와 Backend 구현을 분담할 수 있다.
실제 담당자는 아직 배정하지 않았다. 예시: 개발자 A=Client, B=Backend, 공동=계약·통합 검증.

## 최소 파일 책임 — 구현할 때 추가

- `src/backend/__main__.py`: 서버 실행과 시작 실패 처리
- `src/backend/app.py`: HTTP 경계와 상태 응답
- `src/client/__main__.py`: Qt 애플리케이션 실행
- `src/client/window.py`: 상태 화면
- `src/client/backend_client.py`: 비동기 HTTP 요청과 실패 변환
- `src/shared/protocol.py`: 응답 데이터 정의
- `tests/backend`, `tests/client`, `tests/integration`: 해당 동작의 테스트

현재 추가한 각 영역의 `__init__.py`는 설치 가능한 패키지 경계만 만든다.
위 구현 파일은 아직 없으며 불필요한 하위 계층은 미리 만들지 않는다.

## 진입 준비의 완료와 Phase 완료 구분

준비 변경은 설치 가능한 의존성/패키지 설정, 환경 안내, 통신 계약, 검증표를 갖추면 검토 가능하다.
Phase 1 완료는 별개이며 Windows에서 독립 실행·연결 성공·연결 실패 시 생존을 확인해야 한다.
설치 또는 import 성공을 앱 실행 성공으로 기록하지 않는다.

참조: [환경 설치](../../docs/dev/development-setup.md), [상태 계약](../../docs/dev/health-api.md),
[준비 검증 결과](../../docs/reports/phase1-preparation.md).

## 현재 진행 상태 (1A 구현 후)

- Phase 1: IN_PROGRESS. main 병합은 사용자 지시에 따라 Phase 1 개발 및 테스트 완료 후 수행.
- 1A: Linux에서 구현 및 검증 완료. 공통 응답 dataclass, Backend 진입점, 상태 API, 예외 응답 추가.
- 1B: NOT_STARTED. Client 기술 선택 확인 및 상태 화면 구현 필요.
- 1C: NOT_STARTED. 실제 Client–Backend 연결 검증 필요.
- 1D: NOT_STARTED. Windows 설치 및 UI/연결 검증 필요.

위 준비 시점의 표와 미구현 파일 목록은 당시 기록이며, 최신 구현 상태는 이 절과
[1A 결과](../../docs/reports/phase1-backend.md)를 따른다. Phase 1 전체 완료 체크는 유지한다.
