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

현재 상태 (2026-10-02):

| Phase | Client 상태 | 전체 상태 / 남은 작업 |
|---|---|---|
| 1 | DONE | DONE |
| 2 | DONE · 현재 창 표시/자동 조회 | IN_PROGRESS · Backend Windows 감지, 실제 창 전환 통합 |
| 3 | DONE · 시작 시각/누적 활성 시간 표시 | IN_PROGRESS · Backend 시간/종료/재방문 계산과 통합 |
| 4 | DONE · 최근 기록 조회/새로고침 | IN_PROGRESS · Backend 저장/갱신/조회, 재시작 복원과 통합 |

구현 및 검증 근거: [Phase 2](../../docs/reports/phase2-client.md),
[Phase 3](../../docs/reports/phase3-client.md), [Phase 4](../../docs/reports/phase4-client.md).
사용자는 Client를 우선 담당한다. Phase 3은 별도 채팅에서 구현된 최신 GitHub 브랜치를 확인하여 계승했다.
Phase 4 Client는 `feat/phase3-client` 기반의 `feat/phase4-client`에서 진행한다.
Backend 작업 브랜치와 분리하며 Shared 계약은 Backend 구현 시 함께 반영한다.

이후에는 한 채팅에서 이어가되, **매 작업의 구현·검증·미완료 항목을 GitHub 코드/문서/PR에 기록**한다.
대화나 과거 인수인계만으로 완료 상태를 판단하지 않는다. 재개 시 최신 브랜치·PR과 이 현황을 먼저 확인한다.

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

Client PR은 이전 Client 브랜치를 대상으로 단계별 변경만 검토한다.
선행 PR 병합 시 다음 PR의 기준 브랜치와 차이를 확인한 뒤 변경한다. 전체 Phase 완료와 Client 완료는 구분한다.

## 파일명 및 현황 관리 규칙

- Phase 본문: `phase001.md` ~ `phase014.md`처럼 번호를 세 자리로 기록한다.
- Phase 보조 문서: `phase001-preparation.md`, `phase003-client-handoff.md`처럼 같은 번호 규칙을 따른다.
- 전체 현황은 `00-progress.md`, 폴더 안내는 `README.md`에서 관리한다.
- GitHub 파일 목록에서 이름순으로 Phase 번호가 정렬되도록 한다.
- 번호 변경 시 저장소 내 해당 문서 링크도 함께 갱신한다. 보고서·도구·Git 브랜치 이름은 변경하지 않는다.
- 체크 상태 변경 시 개별 문서와 통합 현황, 작업 확인일·작업 브랜치·근거를 같은 커밋에 기록한다.
