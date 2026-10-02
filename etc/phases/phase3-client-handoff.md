# Phase 3 Client — 다음 채팅 인수인계

작성일: 2026-10-01. 사용자 지시: Client를 우선 개발하고 Phase 2 작동 확인·커밋 후 다음 채팅에서 Phase 3 진행.
이 문서는 다음 작업의 시작점이다. Phase 3 코드는 아직 구현하지 않았다.

## 현재 상태

| 항목 | 상태 |
|---|---|
| 저장소 | `rkdduswns/AICapstone` |
| Phase 1 / main | DONE, 확인 SHA `efafd8e489ef87e42679495ad675c27261feccb5` |
| Phase 2 Client | 구현 및 재검증 완료, `feat/phase2-client`, [Draft PR #2](https://github.com/rkdduswns/AICapstone/pull/2) |
| 검증한 Client 실행 코드 | `33792af4113c59c1446874bc3cd4e78fe87518e9` |
| Phase 2 Backend | `feat/phase2-backend`, 공통 규격 준비 SHA `abdcb47ed30f89fa2da3246faea4b25e367ad2d1`; 실제 감지 미구현 |
| Phase 2 전체 | IN_PROGRESS — 실제 감지/창 전환 통합 검증 미완료 |
| Phase 3 | NOT_STARTED — 다음 채팅에서는 Client 범위만 우선 개발 |

Client 재검증: Windows 10, Python 3.14.7, Qt 6.11.2에서 72개 테스트 통과.
Ruff, pip check, 가상 데이터 화면 표시 확인 완료. 기존 Starlette/httpx 경고 1건.
정확한 검증 범위는 [Phase 2 Client 보고서](../../docs/reports/phase2-client.md)를 따른다.

## 다음 채팅 시작 절차

1. 최신 main, Client/Backend 브랜치, PR #2 상태와 로컬 미커밋 변경을 먼저 확인한다.
2. `etc/개발-지침.md`, `phase3.md`, `docs/dev/current-activity-api.md`, 현재 Client/Shared 코드와 테스트를 읽는다.
3. Phase 2 Client가 main에 병합됐다면 최신 main에서 `feat/phase3-client`를 만든다.
   아직 병합되지 않았다면 최신 `feat/phase2-client`를 기준으로 새 브랜치를 만든다.
   Phase 2 Client 코드가 없는 기존 main에서 새 작업을 시작하지 않는다.
4. 미병합 Client 브랜치를 기반으로 PR을 만들 경우 우선 해당 브랜치를 대상으로 하여 Phase 3 변경만 비교하고,
   Phase 2 병합 뒤 main 기준으로 갱신한다. 기존 Phase 2 PR에 Phase 3 코드를 섞지 않는다.
5. Backend 브랜치의 별도 구현 상황과 공통 규격 변경 여부를 다시 확인한다.

## Phase 3 Client 범위

- 목적: 현재 작업의 시작 시각과 누적 활성 시간을 사용자가 확인할 수 있게 한다.
- 구현 대상: 화면 표시, Backend 응답 처리, 필요한 Shared 시간 필드, 가상 데이터 및 Client 테스트.
- 구현 전 정의: 시각 형식과 시간대, 활성 시간 단위, 값이 없는 경우, 창 전환과 통신 오류 시 표시 방식.
- 현재 수신 시각을 작업 시작 시각으로 취급하지 않는다.
- 활성 시간의 누적과 재방문 판단은 Backend 책임이다. 단순히 현재 시각에서 시작 시각을 빼서 실제 활성 시간으로 표시하지 않는다.
- 공통 규격은 양쪽이 동일하게 사용할 수 있도록 문서화하고 호환성/미지원 응답을 처리한다.
- 우선 가상 응답으로 화면을 검증한다. 실제 시간 추적 및 OS 통합이 확인되기 전 Phase 3 전체를 DONE으로 표시하지 않는다.

## 검증 및 완료조건

- 정상 시작 시각·활성 시간 표시, 시간 값 갱신, 작업 전환, 값 누락/잘못된 값, 오류·복구를 확인한다.
- Phase 2의 프로그램/제목/수집 상태 표시, timeout, 종료 정리, 텍스트 선택·스크롤 보존을 유지한다.
- 기존 테스트와 새 Client 테스트 및 Ruff를 통과하고 API 문서·Phase 상태를 함께 갱신한다.
- Backend와 실제 연동한 시간 일치 검증은 미검증 시 별도 잔여 항목으로 명시한다.

현재 실행 방법(설치된 프로젝트 루트):

```powershell
.\.venv\Scripts\python.exe tools/preview_phase2_client.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m pip check
```
