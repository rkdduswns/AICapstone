# Phase 전체 진행 체크리스트

기준일: **2026-10-26 (KST)**. 기준 main: `7c307987182c629965da63824b60d36e41db4036`.
main에 Client Phase 2~11 및 Backend 구현이 포함돼 있다. 현재 브랜치의 실제 HTTP·SQLite 통합 검증 결과를 추가했다.
브라우저 수동 캡처·명시적 문서 연결과 저장 본문 조회를 추가했다. Windows 실제 수동 검증·자동 탭/파일 감지·검색은 미완료다. [통합 보고서](../../docs/reports/client-backend-integration.md)를 따른다.

## 읽는 방법과 갱신 규칙

- 아래에는 개별 Phase의 모든 체크 항목을 영역별로 모았다. 목표·설계 설명은 개별 문서를 따른다.
- `완료`는 원본의 `[x]`, `미완료`는 `[ ]`에 대응한다. 가상 응답으로 확인한 Client 완료를 Backend/전체 완료로 확대하지 않는다.
- 작업 확인일은 보고서 또는 사용자 승인에서 확인된 날짜다. 과거 항목별 정확한 작업일이 없으면 Phase 단위 확인일/기간을 사용하며 임의로 추정하지 않는다.
- `—`는 미착수 또는 확인된 작업일/작업 브랜치 없음이다. 미완료 행에도 실제 작업을 시작하면 날짜와 브랜치를 기록한다.
- 브랜치는 실제 작업 이력이며 main 병합일과 구분한다. Phase 2 Backend 준비 브랜치의 존재는 구현 완료를 뜻하지 않는다.
- 항목을 변경할 때 개별 Phase 체크리스트와 이 문서를 같은 커밋에서 함께 갱신한다. 작업 확인일·브랜치·검증 근거도 기록한다.
- 후속 기록 형식: `YYYY-MM-DD` 또는 `YYYY-MM-DD ~ YYYY-MM-DD`, 브랜치 `feat/...`, 근거는 보고서/PR/commit 링크.
- 체크 항목에는 구현·테스트·완료 조건이 함께 있으므로 완료 개수는 작업량이나 개발 진척률을 의미하지 않는다.

## 전체 현황

| Phase | 내용 | 전체 상태 | 체크 완료/전체 | 작업 확인일 | 작업 브랜치 | main 병합일 |
|---|---|---|---|---|---|---|
| [001](phase001.md) | 실행 골격 및 Client-Backend 연결 | DONE | 17/17 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | 2026-09-24 |
| [002](phase002.md) | Windows 활성 창 감지 | IN_PROGRESS · Client DONE | 6/20 | 2026-09-24 / 2026-10-01 재검증 | `feat/phase2-client` / `feat/phase2-backend`(준비·미병합) | 2026-10-02 (Client) |
| [003](phase003.md) | 작업 시간 및 재방문 추적 | IN_PROGRESS · Client DONE | 2/17 | 2026-10-01 | `feat/phase3-client` | 2026-10-02 (Client) |
| [004](phase004.md) | 작업 기록 저장 및 조회 | IN_PROGRESS · Client DONE | 17/21 | 2026-10-22 (이력 연결) | `feat/client-backend-integration` | 2026-10-02 (Client) |
| [005](phase005.md) | 기본 개인정보 보호 | IN_PROGRESS · Client DONE | 13/20 | 2026-10-21 (통합 검증) | `feat/client-backend-integration` | 2026-10-16 (Client) |
| [006](phase006.md) | 클립보드 수집 | IN_PROGRESS · Client DONE | 9/20 | 2026-10-21 (통합 검증) | `feat/client-backend-integration` | 2026-10-16 (Client) |
| [007](phase007.md) | 브라우저 기본 연동 | IN_PROGRESS · Client DONE | 10/26 | 2026-10-22 (이력 연결) | `feat/client-backend-integration` | 2026-10-16 (Client) |
| [008](phase008.md) | 웹페이지 본문 수집 | IN_PROGRESS · Client DONE | 8/23 | 2026-10-22 (이력 연결) | `feat/client-backend-integration` | 2026-10-16 (Client) |
| [009](phase009.md) | 로컬 문서 내용 수집 | IN_PROGRESS · Client DONE | 16/21 | 2026-10-22 (이력 연결) | `feat/client-backend-integration` | 2026-10-16 (Client) |
| [010](phase010.md) | 검색 데이터 구축 | IN_PROGRESS · Shared DONE | 4/20 | 2026-10-14 | feat/phase10-shared | 2026-10-16 (Shared) |
| [011](phase011.md) | 조건 검색 | IN_PROGRESS · Client DONE | 9/25 | 2026-10-15 | feat/phase11-client | 2026-10-16 (Client) |
| [012](phase012.md) | 의미 검색 및 혼합 검색 | NOT_STARTED | 0/20 | — | — | — |
| [013](phase013.md) | 근거 기반 RAG | NOT_STARTED | 0/25 | — | — | — |
| [014](phase014.md) | 작업 세션·타임라인·최종 안정화 | NOT_STARTED | 0/28 | — | — | — |

Phase 2~9는 가상 OS 입력과 실제 Backend HTTP·SQLite·문서 추출 라이브러리를 사용해 부분 통합했다.
작업 ID 기반 출처 연결은 가상 OS 입력과 실제 HTTP·SQLite·Qt로 검증했다. 실제 Windows 작업/복사 및 확장 설치 후 수동 검증은 남아 있다.
Phase 10의 실제 정규화·분할·임베딩·검색 데이터 저장/삭제 및 역추적 통합 검증은 남아 있다.
Phase 11의 실제 저장소 조건 검색·정렬·보호 정책 적용 및 통합 검증은 남아 있다.

## 2026-10-22 통합 범위

현재 창·시간·최근 기록, 일시정지/차단/클립보드 설정 및 저장 조회, 수동 문서 가져오기를 실제 Backend와 연결했다.
Backend 구현 자체는 2026-10-21 main에 병합됐다. 이번 통합 브랜치는 main 미병합 상태다.
브라우저 수동 캡처와 문서의 명시적 작업 ID/Windows 경로 연결, 저장 본문 조회를 추가했다.
설정 영속화, 실제 Windows 수동 검증, 자동 탭/파일 감지·URL 차단·실제 검색은 잔여 범위다.
문서의 선택 경로를 보존하지만 수동 연결을 자동 열람 감지 완료로 확대하지 않는다.

## 작업 이력

| 확인일 | 범위 | 작업 브랜치 | 결과 / 근거 |
|---|---|---|---|
| 2026-10-26 | Windows EXE 배포 도구 | `feat/client-backend-integration` | Client/Backend 각각 onefile 빌드·실제 EXE 자동 검증·ZIP 배포, [실행·검증 범위](../../docs/dev/windows-exe.md). main 미병합, Phase 완료 개수는 유지 |
| 2026-10-22 | 웹·문서 작업 이력 연결 | `feat/client-backend-integration` | 실제 FK/본문 조회·명시적 경로·수동 확장, Python 529·Node 8 통과. [실행/제한](../../docs/dev/history-source-linking.md), [검증](../../docs/reports/client-backend-integration.md). main 미병합 |
| 2026-10-21 | Client–Backend 부분 통합 | `feat/client-backend-integration` | 실제 HTTP/Qt/SQLite·문서 추출 연결, [통합 검증](../../docs/reports/client-backend-integration.md). Windows 수동 검증 및 출처 연결/검색 잔여 |
| 2026-09-24 | Phase 1 전체 | `chore/phase1-preparation` | 자동 검증 + 사용자 확인, [PR #1](https://github.com/rkdduswns/AICapstone/pull/1) 병합 |
| 2026-09-24 / 2026-10-01 | Phase 2 Client | `feat/phase2-client` | 구현 및 재검증 완료, 2026-10-02 [PR #2](https://github.com/rkdduswns/AICapstone/pull/2) 병합 |
| 2026-10-01 | Phase 3 Client | `feat/phase3-client` | 구현·검증 완료, 2026-10-02 [PR #3](https://github.com/rkdduswns/AICapstone/pull/3) 병합 |
| 2026-10-02 | Phase 4 Client | `feat/phase4-client` | 구현·검증 완료, [PR #4](https://github.com/rkdduswns/AICapstone/pull/4) 병합 |
| 2026-10-02 | study 공간 | `chore/study-workspace` | [PR #5](https://github.com/rkdduswns/AICapstone/pull/5) 병합; Phase 기능 진척과 별개 |
| 2026-10-07 | Phase 5 Client | `feat/phase5-client` | 제어 화면·Shared 계약·가상 HTTP 검증 완료, [보고서](../../docs/reports/phase5-client.md). 실제 보호 검증은 Backend 연결 후 진행 |
| 2026-10-08 | Phase 6 Client | `feat/phase6-client` | 미병합 Phase 5 기반. 클립보드 설정·작업별 복사 상세·가상 HTTP 검증 완료, [보고서](../../docs/reports/phase6-client.md) |
| 2026-10-09 | Phase 7 Client | `feat/phase7-client` | 미병합 Phase 6 기반. 브라우저 출처·URL 차단 설정·가상 HTTP 검증 완료, [보고서](../../docs/reports/phase7-client.md) |
| 2026-10-10 | Phase 8 Client | `feat/phase8-client` | 미병합 Phase 7 기반. 저장 웹 본문 상세·출처 대조·가상 HTTP 검증 완료, [보고서](../../docs/reports/phase8-client.md) |
| 2026-10-12 | Phase 9 Client | feat/phase9-client | 미병합 Phase 8 기반. 파일 출처·저장 문서 본문·Shared 계약·가상 HTTP 검증 완료, [보고서](../../docs/reports/phase9-client.md) |
| 2026-10-14 | Phase 10 Shared | feat/phase10-shared | 미병합 Phase 9 기반. 검색 조각·출처 계약·Client 수신 검증 완료, [보고서](../../docs/reports/phase10-shared.md) |
| 2026-10-15 | Phase 11 Client | feat/phase11-client | 미병합 Phase 10 기반. 명시적 조건 검색 화면·Shared 계약·가상 HTTP 검증 완료, [보고서](../../docs/reports/phase11-client.md) |

문서 관리 이력: 2026-10-02 `docs/phase-progress`에서 통합 체크리스트와 세 자리 Phase 파일명을 적용했다
([PR #6](https://github.com/rkdduswns/AICapstone/pull/6) 병합). 같은 날 `docs/project-doc-cleanup`에서
준비·인계 문서를 기술 문서와 검증 보고서로 통합하고 현재 main 기준 안내를 정리했다.

## Phase 001 — 실행 골격 및 Client-Backend 연결

원본: [phase001.md](phase001.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | Client 실행 진입점 구성 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Client | 기본 메인 화면 구성 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Client | Backend 연결 상태 표시 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Client | 상태 확인 요청 전송 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Backend | Backend 실행 진입점 구성 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Backend | 상태 확인 요청 처리 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Backend | 실행 상태 반환 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Backend | 기본 예외 처리 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Shared | 공통 응답 형태 정의 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Shared | 상태 정보 구조 정의 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Tests | Client 단독 실행 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Tests | Backend 단독 실행 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Tests | Client → Backend 상태 요청 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| Tests | Backend 미실행 상태 처리 | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| 완료 조건 | Client와 Backend가 각각 실행된다. | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| 완료 조건 | Client에서 Backend 연결 여부를 확인할 수 있다. | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |
| 완료 조건 | 연결 실패 시 프로그램이 비정상 종료되지 않는다. | 완료 | 2026-09-19 ~ 2026-09-24 | `chore/phase1-preparation` | [검증 보고서](../../docs/reports/phase1-client-windows.md) |

## Phase 002 — Windows 활성 창 감지

원본: [phase002.md](phase002.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 현재 감지 프로그램 표시 | 완료 | 2026-09-24 / 2026-10-01 재검증 | `feat/phase2-client` | [검증 보고서](../../docs/reports/phase2-client.md) · Client/가상 응답 범위 |
| Client | 현재 창 제목 표시 | 완료 | 2026-09-24 / 2026-10-01 재검증 | `feat/phase2-client` | [검증 보고서](../../docs/reports/phase2-client.md) · Client/가상 응답 범위 |
| Client | 수집 상태 표시 | 완료 | 2026-09-24 / 2026-10-01 재검증 | `feat/phase2-client` | [검증 보고서](../../docs/reports/phase2-client.md) · Client/가상 응답 범위 |
| Backend | 활성 창 감지 | 미완료 | — | `feat/phase2-backend` (준비) | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 프로세스 ID 확인 | 미완료 | — | `feat/phase2-backend` (준비) | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 프로세스명 확인 | 미완료 | — | `feat/phase2-backend` (준비) | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 프로그램명 정규화 | 미완료 | — | `feat/phase2-backend` (준비) | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 창 제목 추출 | 미완료 | — | `feat/phase2-backend` (준비) | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 지원하지 않는 창 처리 | 미완료 | — | `feat/phase2-backend` (준비) | Backend 구현 및 실제 통합 검증 필요 |
| Shared | 현재 작업 정보 구조 정의 | 완료 | 2026-09-24 / 2026-10-01 재검증 | `feat/phase2-client` | [검증 보고서](../../docs/reports/phase2-client.md) · Client/가상 응답 범위 |
| Tests | 가상 HTTP 응답으로 전환/동일 창/활성 창 없음/미지원/감지 오류 검증 | 완료 | 2026-09-24 / 2026-10-01 재검증 | `feat/phase2-client` | [검증 보고서](../../docs/reports/phase2-client.md) · Client/가상 응답 범위 |
| Tests | 통신 실패·시간 초과·응답 검증·자동 복구·요청 취소 검증 | 완료 | 2026-09-24 / 2026-10-01 재검증 | `feat/phase2-client` | [검증 보고서](../../docs/reports/phase2-client.md) · Client/가상 응답 범위 |
| Tests | Chrome → VS Code 전환 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | Word → Explorer 전환 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | 동일 창 유지 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | 최소화 / 바탕화면 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | 종료되는 프로그램 처리 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | 현재 활성 프로그램을 확인할 수 있다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | 현재 창 제목을 확인할 수 있다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | 창 전환이 Client에 반영된다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |

## Phase 003 — 작업 시간 및 재방문 추적

원본: [phase003.md](phase003.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 현재 작업 시작 시각 표시 | 완료 | 2026-10-01 | `feat/phase3-client` | [검증 보고서](../../docs/reports/phase3-client.md) · Client/가상 응답 범위 |
| Client | 현재 활성 시간 표시 | 완료 | 2026-10-01 | `feat/phase3-client` | [검증 보고서](../../docs/reports/phase3-client.md) · Client/가상 응답 범위 |
| Backend | 작업 시작 시각 기록 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 마지막 활성 시각 갱신 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 활성 시간 누적 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 창 전환 시 이전 작업 종료 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 동일 작업 재활성화 판단 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 재방문 횟수 계산 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 짧은 반복 감지 병합 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | 동일 창 1분 유지 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | A → B → A 재방문 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | 빠른 Alt+Tab | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | 짧은 반복 이벤트 병합 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Tests | Client 표시 시간과 Backend 값 일치 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | 작업별 시작/종료 시각을 구분할 수 있다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | 실제 활성 시간을 계산할 수 있다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | 동일 작업 재방문을 식별할 수 있다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |

## Phase 004 — 작업 기록 저장 및 조회

원본: [phase004.md](phase004.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 최근 작업 기록 간단 조회 화면 | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Client | 최근 기록 새로고침 | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Backend | 작업 기록 생성 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 작업 기록 갱신 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Backend | 활성 시간 저장 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 재방문 횟수 저장 | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| Backend | 최근 기록 조회 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 프로그램 재시작 후 기존 기록 유지 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Shared | 작업 기록 조회 구조 확정 (DB 스키마는 Backend에서 결정) | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Shared | 최근 기록 응답 구조 정의 | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Tests | 새 기록 생성 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | 기존 기록 갱신 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Tests | 재시작 후 기록 조회 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | Client 시간 순 정렬 (시간대 포함 실제 순간 및 동일 시각 ID순) | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Tests | Client 잘못된/누락된 값 처리 | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Tests | Client 빈 목록·조회 실패·수동 복구·취소·긴 제목 표시 | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Tests | 기존 Backend의 미구현 API(404) 호환성 | 완료 | 2026-10-02 | `feat/phase4-client` | [검증 보고서](../../docs/reports/phase4-client.md) · Client/가상 응답 범위 |
| Tests | Backend 최신 기록 제한 조회 및 잘못된 요청 검증 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| 완료 조건 | 실제 작업 기록이 로컬에 저장된다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | 프로그램을 재실행해도 기존 기록이 유지된다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |
| 완료 조건 | Client에서 최근 작업 기록을 확인할 수 있다. | 미완료 | — | — | Backend 구현 및 실제 통합 검증 필요 |

## Phase 005 — 기본 개인정보 보호

원본: [phase005.md](phase005.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 기록 일시정지 / 재개 | 완료 | 2026-10-07 | `feat/phase5-client` | [보고서](../../docs/reports/phase5-client.md) · Client/가상 응답 범위 |
| Client | 차단 프로그램 목록 입력 | 완료 | 2026-10-07 | `feat/phase5-client` | [보고서](../../docs/reports/phase5-client.md) · 적용 확인 및 초안 보존 |
| Client | 현재 기록 가능 여부 표시 | 완료 | 2026-10-07 | `feat/phase5-client` | [보고서](../../docs/reports/phase5-client.md) · Backend 판정 표시 |
| Backend | 전체 기록 일시정지 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 프로그램 차단 검사 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 민감 문자열 패턴 검사 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 저장 전 개인정보 보호 검사 | 미완료 | — | — | 미착수 |
| Backend | 차단 사유 구분 | 미완료 | — | — | 미착수 |
| Shared | 개인정보 설정 구조 | 완료 | 2026-10-07 | `feat/phase5-client` | [개인정보 API](../../docs/dev/privacy-api.md) |
| Shared | 기록 상태 구조 | 완료 | 2026-10-07 | `feat/phase5-client` | [개인정보 API](../../docs/dev/privacy-api.md) |
| Tests | 가상 HTTP 설정 요청·응답 및 기록 상태 표시 | 완료 | 2026-10-07 | `feat/phase5-client` | [보고서](../../docs/reports/phase5-client.md) |
| Tests | 입력 검증·초안 보존·실패 복구·요청 취소 | 완료 | 2026-10-07 | `feat/phase5-client` | [보고서](../../docs/reports/phase5-client.md) |
| Tests | 기록 일시정지 중 저장되지 않음 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | 차단 프로그램 활성 시 저장되지 않음 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | 민감 문자열 차단 | 미완료 | — | — | Backend 연결 후 실제 저장소로 검증 |
| Tests | 기록 재개 후 정상 저장 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | 기존 기록에는 영향 없음 | 미완료 | — | — | Backend 연결 후 실제 저장소로 검증 |
| 완료 조건 | 사용자가 전체 기록을 즉시 중지할 수 있다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 지정 프로그램의 기록이 저장되지 않는다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 기본 민감 문자열이 저장되지 않는다. | 미완료 | — | — | 미착수 |

## Phase 006 — 클립보드 수집

원본: [phase006.md](phase006.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 클립보드 기록 사용 여부 설정 | 완료 | 2026-10-08 | `feat/phase6-client` | [보고서](../../docs/reports/phase6-client.md) · Client/가상 응답 범위 |
| Client | 최근 작업 상세에서 관련 복사 텍스트 확인 | 완료 | 2026-10-08 | `feat/phase6-client` | [보고서](../../docs/reports/phase6-client.md) · 읽기 전용 조회 |
| Backend | 텍스트 클립보드 변화 감지 | 미완료 | — | — | 미착수 |
| Backend | 동일 내용 반복 복사 방지 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 복사 시각 기록 | 미완료 | — | — | 미착수 |
| Backend | 현재 활성 작업과 연결 | 미완료 | — | — | 미착수 |
| Backend | 개인정보 필터 적용 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 과도한 길이 제한 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Shared | 클립보드 사용 설정의 선택 필드 및 변경 계약 | 완료 | 2026-10-08 | `feat/phase6-client` | [클립보드 API](../../docs/dev/clipboard-api.md) |
| Shared | 작업별 복사 이벤트 및 상세 응답 구조 | 완료 | 2026-10-08 | `feat/phase6-client` | [클립보드 API](../../docs/dev/clipboard-api.md) |
| Tests | 가상 HTTP 클립보드 설정 변경 및 구형 응답 호환 | 완료 | 2026-10-08 | `feat/phase6-client` | [보고서](../../docs/reports/phase6-client.md) |
| Tests | 작업별 조회·선택 전환·원문 표시·응답 검증·오류 및 취소 | 완료 | 2026-10-08 | `feat/phase6-client` | [보고서](../../docs/reports/phase6-client.md) |
| Tests | 일반 텍스트 복사 | 미완료 | — | — | Backend 연결 후 OS/저장소 검증 |
| Tests | 동일 텍스트 반복 복사 | 미완료 | — | — | Backend 연결 후 OS/저장소 검증 |
| Tests | 프로그램 전환 직후 복사 | 미완료 | — | — | Backend 연결 후 OS/저장소 검증 |
| Tests | 민감 문자열 복사 | 미완료 | — | — | Backend 연결 후 OS/저장소 검증 |
| Tests | 기록 일시정지 중 복사 | 미완료 | — | — | Backend 연결 후 OS/저장소 검증 |
| 완료 조건 | 복사 텍스트가 현재 작업과 연결된다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 민감 텍스트는 저장되지 않는다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 중복 복사로 기록이 불필요하게 증가하지 않는다. | 미완료 | — | — | 미착수 |

## Phase 007 — 브라우저 기본 연동

원본: [phase007.md](phase007.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Browser | 확장 프로그램 기본 실행 | 미완료 | — | — | 미착수 |
| Browser | 현재 활성 탭 감지 | 미완료 | — | — | 미착수 |
| Browser | 탭 제목 수집 | 미완료 | — | — | 미착수 |
| Browser | URL 수집 | 미완료 | — | — | 미착수 |
| Browser | 탭 변경 이벤트 감지 | 미완료 | — | — | 미착수 |
| Browser | Backend로 정보 전달 | 미완료 | — | — | 미착수 |
| Backend | 브라우저 정보 수신 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Backend | Windows 활성 브라우저 작업과 연결 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Backend | URL 변경 처리 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Backend | 브라우저 작업 기록 갱신 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Backend | URL 차단 검사 | 미완료 | — | — | 미착수 |
| Client | 최근 작업 기록에 URL 표시 | 완료 | 2026-10-09 | `feat/phase7-client` | [보고서](../../docs/reports/phase7-client.md) · 가상 응답 범위 |
| Client | 차단 URL 설정 입력 | 완료 | 2026-10-09 | `feat/phase7-client` | [보고서](../../docs/reports/phase7-client.md) · 실제 차단은 Backend 책임 |
| Shared | 브라우저 출처의 선택 필드와 조회 계약 | 완료 | 2026-10-09 | `feat/phase7-client` | [브라우저 API](../../docs/dev/browser-api.md) |
| Shared | URL 차단 규칙 및 개별 변경 계약 | 완료 | 2026-10-09 | `feat/phase7-client` | [브라우저 API](../../docs/dev/browser-api.md) |
| Tests | 가상 HTTP 브라우저 출처 표시·구형 응답·오류 처리 | 완료 | 2026-10-09 | `feat/phase7-client` | [보고서](../../docs/reports/phase7-client.md) |
| Tests | 가상 HTTP URL 설정·초안 보존·적용 확인·실패 복구 | 완료 | 2026-10-09 | `feat/phase7-client` | [보고서](../../docs/reports/phase7-client.md) |
| Tests | Chrome 탭 전환 | 미완료 | — | — | 미착수 |
| Tests | Edge 탭 전환 | 미완료 | — | — | 미착수 |
| Tests | 동일 탭 URL 변경 | 미완료 | — | — | 미착수 |
| Tests | 새 탭 / 빈 탭 | 미완료 | — | — | 미착수 |
| Tests | 차단 URL | 미완료 | — | — | 미착수 |
| Tests | Browser와 Windows 기록 연결 | 미완료 | — | — | 미착수 |
| 완료 조건 | Chrome/Edge의 페이지 제목과 URL을 기록할 수 있다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 브라우저 탭 변경이 작업 기록에 반영된다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 차단 URL은 저장되지 않는다. | 미완료 | — | — | 미착수 |

## Phase 008 — 웹페이지 본문 수집

원본: [phase008.md](phase008.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Browser | 페이지 텍스트 추출 | 미완료 | — | — | 미착수 |
| Browser | 불필요한 UI 텍스트 최소화 | 미완료 | — | — | 미착수 |
| Browser | 페이지 변경 시 본문 갱신 | 미완료 | — | — | 미착수 |
| Browser | 텍스트 크기 제한 | 미완료 | — | — | 미착수 |
| Browser | 차단 URL에서 본문 수집 금지 | 미완료 | — | — | 미착수 |
| Backend | 수신한 웹 텍스트 정리 | 미완료 | — | — | 미착수 |
| Backend | 동일 페이지 중복 텍스트 제거 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 · 같은 출처 재전송은 갱신 |
| Backend | URL / 제목 / 본문 연결 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Backend | 원본 작업 기록과 연결 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 |
| Client | 최근 작업에서 저장된 웹 본문·수집 시각·출처 확인 | 완료 | 2026-10-10 | `feat/phase8-client` | [보고서](../../docs/reports/phase8-client.md) · 저장 결과 확인 범위 추가 |
| Client | 미수집·길이 제한·조회 오류 상태 표시 | 완료 | 2026-10-10 | `feat/phase8-client` | [보고서](../../docs/reports/phase8-client.md) · Client/가상 응답 범위 |
| Shared | 작업별 웹 본문과 출처를 연결하는 조회 계약 | 완료 | 2026-10-10 | `feat/phase8-client` | [웹 본문 API](../../docs/dev/web-content-api.md) |
| Tests | 가상 HTTP 본문 조회·선택 전환·오류·취소·복구 | 완료 | 2026-10-10 | `feat/phase8-client` | [보고서](../../docs/reports/phase8-client.md) |
| Tests | 본문 응답 검증·출처 대조·길이 및 빈 결과 검사 | 완료 | 2026-10-10 | `feat/phase8-client` | [보고서](../../docs/reports/phase8-client.md) |
| Tests | 일반 기사 페이지 | 미완료 | — | — | 미착수 |
| Tests | 문서형 페이지 | 미완료 | — | — | 미착수 |
| Tests | SPA 페이지 전환 | 미완료 | — | — | 미착수 |
| Tests | 동일 페이지 재방문 | 미완료 | — | — | 미착수 |
| Tests | 매우 긴 페이지 | 미완료 | — | — | 미착수 |
| Tests | 차단 사이트 본문 미수집 | 미완료 | — | — | 미착수 |
| 완료 조건 | 웹페이지 내용이 실제 URL과 연결되어 저장된다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 같은 페이지의 불필요한 중복 내용이 최소화된다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 차단 URL의 본문은 저장되지 않는다. | 미완료 | — | — | 미착수 |

## Phase 009 — 로컬 문서 내용 수집

원본: [phase009.md](phase009.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Backend | 열려 있는 파일 경로 식별 | 미완료 | — | — | Backend 실제 감지·추출·저장 및 통합 검증 필요 |
| Backend | 지원 파일 유형 판별 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | PDF 텍스트 추출 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | DOCX 텍스트 추출 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Backend | 문서 내용과 파일 경로 연결 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 · 명시적 선택 연결, 자동 감지 아님 |
| Backend | 열람 시각과 작업 기록 연결 | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 · 명시적 선택 연결, 자동 감지 아님 |
| Backend | 동일 파일 재처리 최소화 | 미완료 | — | — | Backend 실제 감지·추출·저장 및 통합 검증 필요 |
| Client | 최근 기록에서 파일 경로 표시 | 완료 | 2026-10-12 | feat/phase9-client | [검증 보고서](../../docs/reports/phase9-client.md) · Client/가상 응답 범위 |
| Client | 파일 출처 상세보기 | 완료 | 2026-10-12 | feat/phase9-client | [검증 보고서](../../docs/reports/phase9-client.md) · Client/가상 응답 범위 |
| Shared | 문서 출처와 작업별 저장 본문 조회 계약 | 완료 | 2026-10-12 | feat/phase9-client | [검증 보고서](../../docs/reports/phase9-client.md) · Client/가상 응답 범위 |
| Tests | 가상 HTTP 문서 조회·선택 전환·오류·취소·복구 | 완료 | 2026-10-12 | feat/phase9-client | [검증 보고서](../../docs/reports/phase9-client.md) · Client/가상 응답 범위 |
| Tests | Windows 파일 출처·본문 계약·길이·구형 응답 검증 | 완료 | 2026-10-12 | feat/phase9-client | [검증 보고서](../../docs/reports/phase9-client.md) · Client/가상 응답 범위 |
| Tests | 일반 PDF | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | 여러 페이지 PDF | 미완료 | — | — | Backend 실제 감지·추출·저장 및 통합 검증 필요 |
| Tests | 일반 DOCX | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | 내용 없는 문서 | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| Tests | 이동/삭제된 파일 | 미완료 | — | — | Backend 실제 감지·추출·저장 및 통합 검증 필요 |
| Tests | 동일 파일 재열람 | 미완료 | — | — | Backend 실제 감지·추출·저장 및 통합 검증 필요 |
| 완료 조건 | PDF 내용을 추출할 수 있다. | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| 완료 조건 | DOCX 내용을 추출할 수 있다. | 완료 | 2026-10-21 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 입력/실제 Backend·DB |
| 완료 조건 | 추출된 내용에서 실제 파일 경로로 역추적할 수 있다. | 완료 | 2026-10-22 | `feat/client-backend-integration` | [통합 검증](../../docs/reports/client-backend-integration.md) · 가상 OS 입력과 실제 HTTP·SQLite·Qt 검증 · 명시적 선택 연결, 자동 감지 아님 |

## Phase 010 — 검색 데이터 구축

원본: [phase010.md](phase010.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Backend | 텍스트 정규화 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Backend | 긴 문서 분할 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Backend | 짧은/불필요한 조각 제거 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Backend | 각 조각에 원본 작업 ID 연결 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Backend | 의미 검색용 데이터 생성 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Backend | 검색용 데이터 저장 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Backend | 원본 삭제 시 검색 데이터 처리 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Shared | 검색 문서 조각 구조 정의 | 완료 | 2026-10-14 | feat/phase10-shared | [검증 보고서](../../docs/reports/phase10-shared.md) · Shared/가상 계약 범위 |
| Shared | 출처 메타데이터 구조 정의 | 완료 | 2026-10-14 | feat/phase10-shared | [검증 보고서](../../docs/reports/phase10-shared.md) · Shared/가상 계약 범위 |
| Tests | 가상 웹/PDF/DOCX 조각의 JSON 직렬화·검증·출처 복원 | 완료 | 2026-10-14 | feat/phase10-shared | [검증 보고서](../../docs/reports/phase10-shared.md) · Shared/가상 계약 범위 |
| Tests | 작업 ID·출처·시각·본문 계약 오류 거부 | 완료 | 2026-10-14 | feat/phase10-shared | [검증 보고서](../../docs/reports/phase10-shared.md) · Shared/가상 계약 범위 |
| Tests | 긴 웹페이지 분할 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Tests | 긴 PDF 분할 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Tests | 아주 짧은 텍스트 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Tests | 중복 조각 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Tests | 검색 조각 → 원본 URL 복원 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| Tests | 검색 조각 → 원본 파일 경로 복원 | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| 완료 조건 | 웹/문서 내용을 동일한 검색 단위로 다룰 수 있다. | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| 완료 조건 | 모든 검색 단위가 실제 원본 작업과 연결된다. | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |
| 완료 조건 | 의미 검색에 사용할 데이터가 준비된다. | 미완료 | — | — | Backend 정규화·분할·의미 데이터 생성/저장·실제 통합 필요 |

## Phase 011 — 조건 검색

원본: [phase011.md](phase011.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 검색 입력 화면 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Client | 검색 결과 목록 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Client | 결과 제목 / 출처 / 열람 시각 표시 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Client | 결과 상세보기 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Backend | 시간 범위 조건 처리 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Backend | 프로그램 조건 처리 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Backend | 웹 / 파일 출처 유형 조건 처리 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Backend | 제목 키워드 검색 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Backend | 복수 조건 결합 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Backend | 결과 시간순 / 최근순 정렬 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Shared | 검색 요청 구조 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Shared | 검색 결과 구조 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Shared | 출처 정보 구조 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Tests | 가상 HTTP 조건 전달·결과/상세·빈 결과·오류·취소·복구 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Tests | 입력·응답 조건 확인·정렬·기록 계약 검증 | 완료 | 2026-10-15 | feat/phase11-client | [검증 보고서](../../docs/reports/phase11-client.md) · Client/Shared/가상 응답 범위 |
| Tests | 오늘 기록 검색 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Tests | 특정 날짜 범위 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Tests | Chrome 기록만 검색 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Tests | PDF 기록만 검색 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Tests | 시간 + 프로그램 조건 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| Tests | 결과 없음 | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| 완료 조건 | 시간 조건으로 기록을 찾을 수 있다. | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| 완료 조건 | 프로그램 조건으로 기록을 찾을 수 있다. | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| 완료 조건 | 웹/파일 출처를 구분해 검색할 수 있다. | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |
| 완료 조건 | 결과에서 실제 출처와 열람 시각을 확인할 수 있다. | 미완료 | — | — | Backend 실제 저장소 검색·정렬·보호 정책 및 통합 검증 필요 |

## Phase 012 — 의미 검색 및 혼합 검색

원본: [phase012.md](phase012.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 자연어 검색 입력 | 미완료 | — | — | 미착수 |
| Client | 관련 내용 미리보기 | 미완료 | — | — | 미착수 |
| Client | 검색 결과 관련도 표시 방식 정리 | 미완료 | — | — | 미착수 |
| Backend | 질의 의미 검색 | 미완료 | — | — | 미착수 |
| Backend | 의미 유사도 기반 후보 추출 | 미완료 | — | — | 미착수 |
| Backend | 시간 조건 + 의미 검색 | 미완료 | — | — | 미착수 |
| Backend | 프로그램 조건 + 의미 검색 | 미완료 | — | — | 미착수 |
| Backend | 출처 유형 + 의미 검색 | 미완료 | — | — | 미착수 |
| Backend | 결과 재정렬 | 미완료 | — | — | 미착수 |
| Backend | 활성 시간 / 재방문 신호 반영 가능 구조 | 미완료 | — | — | 미착수 |
| Tests | 내용만 기억하는 질의 | 미완료 | — | — | 미착수 |
| Tests | 다른 표현의 의미 검색 | 미완료 | — | — | 미착수 |
| Tests | 시간 + 의미 질의 | 미완료 | — | — | 미착수 |
| Tests | 프로그램 + 의미 질의 | 미완료 | — | — | 미착수 |
| Tests | 웹과 PDF 혼합 결과 | 미완료 | — | — | 미착수 |
| Tests | 관련 없는 질의 | 미완료 | — | — | 미착수 |
| Tests | 실제 출처 연결 검증 | 미완료 | — | — | 미착수 |
| 완료 조건 | 내용의 의미만으로 과거 자료를 찾을 수 있다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 시간·프로그램 조건과 의미 검색을 함께 사용할 수 있다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 검색 결과에서 실제 URL/파일 경로를 확인할 수 있다. | 미완료 | — | — | 미착수 |

## Phase 013 — 근거 기반 RAG

원본: [phase013.md](phase013.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Client | 생성 답변 표시 | 미완료 | — | — | 미착수 |
| Client | 답변 근거 목록 | 미완료 | — | — | 미착수 |
| Client | 근거별 URL / 파일 경로 | 미완료 | — | — | 미착수 |
| Client | 근거별 열람 시각 | 미완료 | — | — | 미착수 |
| Client | 근거 상세보기 | 미완료 | — | — | 미착수 |
| Client | 근거 부족 상태 표시 | 미완료 | — | — | 미착수 |
| Backend | 상위 검색 근거 선택 | 미완료 | — | — | 미착수 |
| Backend | 중복 근거 제거 | 미완료 | — | — | 미착수 |
| Backend | 답변용 근거 구성 | 미완료 | — | — | 미착수 |
| Backend | 검색 근거 기반 응답 생성 | 미완료 | — | — | 미착수 |
| Backend | 근거 밖 출처 생성 방지 | 미완료 | — | — | 미착수 |
| Backend | 근거 부족 기준 적용 | 미완료 | — | — | 미착수 |
| Backend | 외부 전달 전 민감정보 재검사 | 미완료 | — | — | 미착수 |
| Shared | RAG 요청 구조 | 미완료 | — | — | 미착수 |
| Shared | 답변 구조 | 미완료 | — | — | 미착수 |
| Shared | 근거 출처 구조 | 미완료 | — | — | 미착수 |
| Tests | 단일 출처 질문 | 미완료 | — | — | 미착수 |
| Tests | 여러 출처 질문 | 미완료 | — | — | 미착수 |
| Tests | 비슷한 문서 구분 | 미완료 | — | — | 미착수 |
| Tests | 근거가 없는 질문 | 미완료 | — | — | 미착수 |
| Tests | 존재하지 않는 URL 생성 여부 | 미완료 | — | — | 미착수 |
| Tests | 차단/민감 데이터 포함 여부 | 미완료 | — | — | 미착수 |
| 완료 조건 | 검색된 기록을 기반으로 답변할 수 있다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 답변의 실제 출처를 함께 표시한다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 충분한 근거가 없으면 임의 답변을 생성하지 않는다. | 미완료 | — | — | 미착수 |

## Phase 014 — 작업 세션·타임라인·최종 안정화

원본: [phase014.md](phase014.md)

| 영역 | 체크 항목 | 상태 | 작업 확인일 | 작업 브랜치 | 근거 / 남은 사항 |
|---|---|---|---|---|---|
| Backend | 시간 간격 기반 작업 세션 구성 | 미완료 | — | — | 미착수 |
| Backend | 세션 시작 / 종료 계산 | 미완료 | — | — | 미착수 |
| Backend | 세션과 작업 기록 연결 | 미완료 | — | — | 미착수 |
| Backend | 세션 관련 자료 조회 | 미완료 | — | — | 미착수 |
| Backend | 선택 기록 삭제 | 미완료 | — | — | 미착수 |
| Backend | 전체 기록 삭제 | 미완료 | — | — | 미착수 |
| Backend | 장시간 수집 안정성 확인 | 미완료 | — | — | 미착수 |
| Backend | 종료/재시작 데이터 일관성 확인 | 미완료 | — | — | 미착수 |
| Backend | 검색 응답 시간 점검 | 미완료 | — | — | 미착수 |
| Client | 작업 타임라인 | 미완료 | — | — | 미착수 |
| Client | 작업 세션 상세보기 | 미완료 | — | — | 미착수 |
| Client | 개인정보 설정 화면 정리 | 미완료 | — | — | 미착수 |
| Client | 기록 삭제 기능 | 미완료 | — | — | 미착수 |
| Client | 검색 → 답변 → 출처 이동 흐름 정리 | 미완료 | — | — | 미착수 |
| Client | 오류 / 빈 결과 상태 정리 | 미완료 | — | — | 미착수 |
| Integration | 웹 열람 → 기록 → 의미 검색 → URL 확인 | 미완료 | — | — | 미착수 |
| Integration | PDF 열람 → 내용 검색 → 파일 경로 확인 | 미완료 | — | — | 미착수 |
| Integration | 기록 → 검색 → RAG → 근거 확인 | 미완료 | — | — | 미착수 |
| Integration | 차단 앱 → 저장되지 않음 | 미완료 | — | — | 미착수 |
| Integration | 차단 URL → 저장되지 않음 | 미완료 | — | — | 미착수 |
| Integration | 일시정지 → 재개 | 미완료 | — | — | 미착수 |
| Integration | 재시작 후 기존 기록 검색 | 미완료 | — | — | 미착수 |
| Integration | 장시간 실행 | 미완료 | — | — | 미착수 |
| 완료 조건 | 웹과 로컬 문서의 전체 출처 역추적 흐름이 동작한다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 관련 작업을 세션과 타임라인으로 확인할 수 있다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 개인정보 보호 규칙이 전체 파이프라인에 적용된다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 프로그램 재시작 후에도 기존 기록을 검색할 수 있다. | 미완료 | — | — | 미착수 |
| 완료 조건 | 대표 시연 시나리오를 반복해도 안정적으로 동작한다. | 미완료 | — | — | 미착수 |
