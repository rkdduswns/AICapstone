# Phase 10 Shared 계약 및 Client 수신 검증

작업일: 2026-10-14 (KST). 브랜치: feat/phase10-shared.
상태: **Shared 및 Client 수신 검증 선행 범위 완료 / 전체 IN_PROGRESS**.

## 기준과 범위

최신 main은 d9c47d1be5469085728e18dc9d53e2de0625459b이며 Phase 2–4 Client가 병합됐다.
Phase 5–9는 Draft PR #8–12에 있다. Phase 9의 문서 출처에 의존하여
39e32973574b031f78390e1b97462352a6c76970에서 분기했다.
PR base는 feat/phase9-client이고 선행 PR 병합 후 main 기준으로 갱신한다.

Phase 10의 Shared 두 항목을 구현했다. 검색 입력·목록·상세 UI는 Phase 11에서 진행한다.
Backend의 분할·임베딩·검색/영속 저장 구현은 별도 범위다.

## 구현

- DocumentChunk: 조각 ID·원본 작업 ID·순서·텍스트·의미 데이터 참조.
- SourceMetadata: 확보 당시 웹 또는 파일 출처·프로그램·작업/본문 확보 시각·일부 원문 여부.
- Client JSON 수신 검증: 원본 작업 ID 대조, 단일 출처, 시각·타입·필수 필드·길이 검증.
- 기존 URL/파일/시각 검증을 재사용하고 ID·주소·경로·원문을 임의 수정하지 않는다.
- Shared는 데이터 정의만 담당하고 Qt·Client·Backend를 import하지 않는다.
- HTTP 경로, 검색 요청, 분할 알고리즘, 저장소 스키마, 모델을 이번 단계에서 도입하지 않는다.
- 새 외부 의존성, Backend 실행 코드, 기존 화면 변경 없음.

## 검증

검증 환경: Linux x86_64, Python 3.12.14, PySide6/Qt 6.12.0, pytest 9.1.1, Ruff 0.17.0.
Windows Python 3.11/3.12 CI 결과는 PR에 기록한다.

| 범위 | 결과 |
|---|---|
| 신규 계약 검증 | **58 passed**, 0.08초 |
| 기존 348개 회귀 포함 전체 pytest | **406 passed**, 53.73초 |
| Ruff: src tests tools | 통과 |
| pip check | 의존성 문제 없음 |
| git diff --check | 통과 |
| 전체 14개 Phase 체크리스트·완료 수·문서 링크 | 일치 |
| Shared 독립 import | Client/Backend/PySide6 로드 없이 성공 |

가상 웹/PDF/DOCX 조각의 JSON 직렬화·수신 및 출처 복원을 검증했다.
원본 작업 ID 불일치, 웹/파일 종류 혼합, 필수 필드 누락, 유효하지 않은 URL/파일 경로,
타입·시각·활성 구간 순서·본문 길이 오류를 거부했다.
Unicode 상한, 짧은 텍스트, 추가 필드·의미 데이터 참조 생략/null,
비동기 확보 시각과 페이지 이동 후 과거 출처 스냅샷 보존을 확인했다.
기존 Starlette/httpx deprecation warning 1건이 있으며 이번 전체 실행에서는 Qt 비정상 종료가 없었다.
새 UI가 없어 별도 화면 미리보기는 추가하지 않았다.

## 완료 범위와 남은 작업

개별/통합 체크리스트는 Shared 2개·계약 검증 2개, **4/20**을 완료로 기록한다.
기존 분할/역추적 테스트와 전체 완료 조건은 실제 파이프라인 검증이므로 미완료로 유지한다.
원문 정규화·분할·짧은/중복 조각 정책, 의미 데이터 생성·저장·삭제 연동은 Backend에 남아 있다.
다음 Client 화면 단계는 Phase 11 조건 검색이다.

계약: [검색 문서 조각·출처](../dev/search-data-contract.md).
