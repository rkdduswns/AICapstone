# Phase 11 Client 조건 검색 구현 및 검증

작업일: 2026-10-15 (KST). 브랜치: feat/phase11-client.
상태: **Client/Shared DONE / 전체 IN_PROGRESS**.

## 기준과 범위

최신 main은 d9c47d1be5469085728e18dc9d53e2de0625459b다.
미병합 Phase 10의 b3f637b30b9353ada19c154ee0798ca599a858f0에서 분기했다.
PR base는 feat/phase10-shared이며 선행 PR 병합 후 main 기준으로 갱신한다.
이번 PR이 Shared 기준 브랜치에서도 Windows CI를 실행하도록 기존 workflow의 PR 대상에
feat/phase*-shared를 추가했다.

## 구현

- 조건 검색 탭: 제목 키워드, 프로세스명, 출처 유형, 전체/오늘/선택 날짜, 최근/오래된 순.
- 조건을 고정해 GET으로 수동 검색하고 서버의 전체 조건 확인을 대조한다.
- 최대 20건 목록, 원문 출처·열람/활성 시각·작업 정보 상세, 빈 결과·더 있음 안내.
- 입력 변경·취소·재연결·종료 시 요청/결과 정리, 입력 초안 유지, 수동 재검색.
- 요청·응답 Shared 계약과 기존 ContextRecord 출처 구조 재사용.
- 최근 기록과 검색에서 공통 행 검증을 추출했다. 기존 최근 기록의 검증·정렬 동작은 유지한다.
- 새 외부 의존성과 Backend 검색 실행 코드는 추가하지 않았다.

## 검증

Linux x86_64 / Python 3.12.14 / PySide6·Qt 6.12.0 / pytest 9.1.1 / Ruff 0.17.0.
Windows Python 3.11/3.12 CI 결과는 PR에 기록한다.

| 범위 | 결과 |
|---|---|
| 신규 요청·응답·가상 HTTP·UI·날짜 테스트 | **53 passed**, 2.47초 |
| 기존 406개 회귀 포함 전체 pytest | **459 passed**, 67.27초 |
| Ruff: src tests tools | 통과 |
| pip check | 의존성 문제 없음 |
| git diff --check | 통과 |
| 전체 14개 Phase 체크리스트·완료 수·문서 링크 | 일치 |
| 전체/PDF·빈 결과·조회 거부 미리보기 | 한글·폼·목록·전체 출처·시각·버튼, 620×740 배치 확인 |

오늘·기간 선택·프로그램·출처·키워드·복수 조건을 쿼리에 담고 통제된 가상 결과를 표시했다.
특수문자/태그 형태 제목을 원문으로 유지하고 상세 선택·최대 20건/더 있음 안내를 확인했다.
조건 확인 불일치·중복/잘못된 기록·정렬·오류·timeout·중복 요청·취소·입력 변경 후 늦은 응답·
재연결 초안 보존·종료를 검증했다. 기존 Starlette/httpx 경고 1건은 유지된다.
DST 전환일의 날짜 자정 경계는 별도 POSIX 프로세스에서 확인했다.
이 테스트 1개는 time.tzset이 없는 Windows에서 제외되며 나머지 테스트는 같은 CI에서 실행한다.

기존 회귀 첫 실행에서 Qt 이벤트 처리 중 segmentation fault가 발생했다.
기존 테스트 다수가 close만 호출하고 숨은 창을 남기는 것을 확인해 Client 공통 fixture에서
종료 후 창 deleteLater·DeferredDelete 이벤트·Python 순환 참조를 정리하도록 했다.
개별 문서 테스트만 정리하던 처리를 모든 Client 테스트 경계에 적용했다.
내부 C++ 오류 원인은 확정하지 않았다. 정리 보완 후 전체 406개, 458개, 최종 459개 실행이 통과했다.
Windows CI 결과도 PR에서 확인한다.

## 완료 범위

Client 4개, Shared 3개, 가상 검증 2개로 **9/25** 항목을 완료 처리한다.
기존 Tests 및 전체 완료 조건은 실제 Backend 검색을 대상으로 하므로 미완료로 유지한다.
가상 서버의 조건 필터는 요청/화면 확인을 위한 테스트 도구이며 실제 Backend 검색 구현이 아니다.

실행: python tools/preview_phase11_client.py
옵션: --source all|web|document|pdf|docx, --state ready|empty|unsupported|denied.
--snapshot 옵션은 첫 검색 결과/오류 화면을 PNG로 저장하고 종료한다.

계약: [조건 검색 API](../dev/search-api.md).
