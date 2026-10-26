# ContextTrace 개발 Phase

**[전체 체크리스트·작업일·브랜치 현황](00-progress.md)** — 모든 Phase 진행사항을 한 문서에서 확인합니다.

ContextTrace 개발은 기능을 큰 덩어리로 한 번에 구현하지 않고, **작은 기능 단위로 완성 → 검증 → 통합**하는 방식으로 진행한다.

| Phase | 핵심 기능 | 완료 결과 |
|---|---|---|
| Phase 1 | 실행 골격 및 Client-Backend 연결 | 앱 실행, 상태 요청/응답 확인 |
| Phase 2 | 활성 창 감지 | 현재 프로그램과 창 제목 감지 |
| Phase 3 | 작업 시간 추적 | 시작/종료/활성 시간/재방문 계산 |
| Phase 4 | 작업 기록 저장 | 수집 기록을 로컬에 저장하고 조회 |
| Phase 5 | 기본 개인정보 보호 | 일시정지, 프로그램 차단, 민감정보 필터 |
| Phase 6 | 클립보드 수집 | 복사 텍스트를 현재 작업과 연결 |
| Phase 7 | 브라우저 기본 연동 | Chrome/Edge URL·제목 수집 |
| Phase 8 | 브라우저 본문 수집 | 웹페이지 내용을 검색 가능한 텍스트로 확보 |
| Phase 9 | 로컬 문서 수집 | PDF/DOCX 내용과 실제 파일 출처 연결 |
| Phase 10 | 검색 데이터 구축 | 문서 분할 및 의미 검색용 데이터 생성 |
| Phase 11 | 조건 검색 | 시간·프로그램·출처 유형으로 검색 |
| Phase 12 | 의미·혼합 검색 | 자연어 내용 검색과 조건 검색 결합 |
| Phase 13 | 근거 기반 RAG | 검색 기록 기반 답변과 출처 제공 |
| Phase 14 | 작업 세션·타임라인·안정화 | 세션 구성, 전체 통합, 최종 검증 |

현재 상태 (2026-10-22, `feat/client-backend-integration` 검증 포함):

| Phase | Client·Shared 선행 상태 | 전체 상태 / 남은 작업 |
|---|---|---|
| 1 | DONE | DONE |
| 2 | DONE · 현재 창 표시/자동 조회 | IN_PROGRESS · 실제 API 연결 완료, Windows 창 전환 수동 검증 잔여 |
| 3 | DONE · 시작 시각/누적 활성 시간 표시 | IN_PROGRESS · 세션 시간/종료 저장 연결, 재방문 집계 잔여 |
| 4 | DONE · 최근 기록 조회/새로고침 | IN_PROGRESS · 실제 SQLite 저장/조회·DB 재조회 검증, 진행 중 갱신 완료, 재방문/Windows 수동 검증 잔여 |
| 5 | DONE · 일시정지/차단 목록/기록 상태 | IN_PROGRESS · 실제 설정 API/수집기 연결, 설정 영속화·Windows 수동 검증 잔여 |
| 6 | DONE · 클립보드 기록 설정/복사 텍스트 상세 | IN_PROGRESS · 실제 수집기/DB/조회 연결, Windows 실제 복사 수동 검증 잔여 |
| 7 | DONE · 브라우저 출처/URL 차단 설정 | IN_PROGRESS · 수동 확장/작업 ID 연결 완료, 자동 탭 이벤트·URL 차단·Windows 수동 검증 잔여 |
| 8 | DONE · 저장 웹 본문/수집 시각/출처 상세 | IN_PROGRESS · 수동 캡처/저장 본문 조회/재전송 갱신 완료, 정제·자동 갱신·URL 차단 잔여 |
| 9 | DONE · 파일 출처/저장 본문 및 문서 가져오기 | IN_PROGRESS · 실제 추출·명시적 작업/선택 경로 연결 완료, 자동 파일 감지·Windows 수동 검증 잔여 |
| 10 | Shared DONE · 검색 조각·확보 당시 출처·Client 수신 검증 | IN_PROGRESS · Backend 정규화·분할·임베딩·저장/삭제·역추적 통합 |
| 11 | Client DONE · 명시적 조건 검색·목록·출처 상세 | IN_PROGRESS · Backend 실제 필터·조회·정렬·통합 |

구현 및 검증 근거: [Phase 2](../../docs/reports/phase2-client.md),
[Phase 3](../../docs/reports/phase3-client.md), [Phase 4](../../docs/reports/phase4-client.md),
[Phase 5](../../docs/reports/phase5-client.md), [Phase 6](../../docs/reports/phase6-client.md),
[Phase 7](../../docs/reports/phase7-client.md), [Phase 8](../../docs/reports/phase8-client.md), [Phase 9](../../docs/reports/phase9-client.md),
[Phase 10](../../docs/reports/phase10-shared.md), [Phase 11](../../docs/reports/phase11-client.md).
Client Phase 2–4는 2026-10-02, Phase 5–11 Client/Shared는 2026-10-16 main에 병합했다.
Backend 활성 창·세션 저장·브라우저 수신·PDF/DOCX 추출 구현은 2026-10-21 main에 반영됐다.
`feat/client-backend-integration`에서 실제 HTTP/Qt/SQLite 통합과 문서 가져오기를 검증한다.
2026-10-26 Windows Client·Backend의 단일 EXE 빌드·패키지 실행 검증을 추가했다.
[배포 안내](../../docs/dev/windows-exe.md)를 따르며 기능별 Phase 완료 개수와 구분한다.
[통합 보고서](../../docs/reports/client-backend-integration.md)에 연결 범위·검증 결과·제한을 기록한다.
브라우저 수동 캡처·문서 선택 경로의 실제 작업 ID 연결과 저장 본문 조회를 추가했다.
자동 탭/파일 감지, URL 차단, 검색 데이터/조건 검색 API, LLM은 미구현이다.
가상 OS 입력을 실제 Backend로 처리한 검증과 Windows 데스크톱 수동 검증을 구분한다.

매 작업의 구현·검증·미완료 항목을 코드·문서·PR에 기록하고, 최신 브랜치와 검증 근거로 완료 상태를 판단한다.

## 단계별 선행조건

- 실제 Backend 저장 흐름은 가상 OS 입력과 SQLite로 자동 검증한다. 실제 Windows 데이터 수집 전 저장 전 개인정보 정책과 수동 검증을 확인한다.
- PDF/DOCX 수동 가져오기·추출·저장은 구현됐다. 선택한 작업과 실제 선택 경로를 명시적으로 연결한다. 자동 열린 파일 식별은 후속 범위다.

## 진행 원칙

- Phase는 코드 복사 단위가 아니라 개발 목표와 완료 조건을 관리하는 단위이다.
- 실제 코드는 `src/`에서 계속 발전시킨다.
- 각 Phase는 이전 Phase 결과를 유지하면서 한 가지 기능을 추가한다.
- Client와 Backend의 데이터 구조는 해당 기능 구현 전에 먼저 합의한다.
- Phase 마지막에 한꺼번에 연결하지 않고 작은 단위로 계속 통합한다.
- 각 Phase가 끝날 때 최소 1개의 통합 시나리오를 반드시 확인한다.
- 완료된 Phase는 Git tag 또는 milestone으로 시점을 남길 수 있다.

## 권장 Git 흐름

```text
Issue
  ↓
Feature Branch
  ↓
구현 + Test
  ↓
Pull Request
  ↓
상대 개발자 Review
  ↓
main Merge
```

브랜치 예:

```text
feat/window-detection
feat/activity-tracking
feat/browser-context
feat/hybrid-search
fix/privacy-filter
docs/phase-8
```

새 작업은 최신 main에서 분기한다. 미병합 선행 작업에 의존하는 경우에만 해당 브랜치를 PR 기준으로 사용하고,
선행 PR 병합 후 main 기준으로 갱신한다. 전체 Phase 완료와 Client 완료는 구분한다.

## 파일명 및 현황 관리 규칙

- Phase 본문: `phase001.md` ~ `phase014.md`처럼 번호를 세 자리로 기록한다.
- Phase 보조 문서는 별도로 유지할 필요가 있을 때만 `phaseNNN-주제.md` 규칙으로 작성한다.
- 전체 현황은 `00-progress.md`, 폴더 안내는 `README.md`에서 관리한다.
- GitHub 파일 목록에서 이름순으로 Phase 번호가 정렬되도록 한다.
- 번호 변경 시 저장소 내 해당 문서 링크도 함께 갱신한다. 보고서·도구·Git 브랜치 이름은 변경하지 않는다.
- 체크 상태 변경 시 개별 문서와 통합 현황, 작업 확인일·작업 브랜치·근거를 같은 커밋에 기록한다.
