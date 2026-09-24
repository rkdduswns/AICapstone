# ContextTrace 개발 Phase

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

현재 상태: **Phase 1 DONE**, **Phase 2 IN_PROGRESS** (2026-09-24).
Phase 2 Client 표시·자동 조회 및 Shared 계약을 구현하고 가상 HTTP 응답으로 검증했다.
다음 작업은 Backend Windows 감지와 실제 창 전환 통합 검증이다.
[Client 구현 결과와 현재 상태](../../docs/reports/phase2-client.md)를 참고한다.

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
