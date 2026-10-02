# Phase 3 Client 구현 및 검증

기준일: 2026-10-01. Phase 3 Client 완료 / 전체 IN_PROGRESS.

## 시작 상태 및 구현

작업 브랜치: `feat/phase3-client`. 기반: Phase 2 Client `1174da0`.
2026-10-02 [PR #3](https://github.com/rkdduswns/AICapstone/pull/3)로 main에 병합했다.

- Shared `ActivityTiming` 및 선택 `CurrentActivity.timing` 추가.
- 시간대 포함 ISO 시작 시각, 누적 활성 밀리초 검증 및 API 문서화.
- PC 현지 시작 시각/오프셋과 `HH:MM:SS` 누적 활성 시간 표시.
- 기존 응답의 시간 누락/null 처리. 오류/창 전환/창 없음/재확인 시 이전 시간 제거.
- Client의 시간 추정·누적 계산 없이 서버 값만 표시.
- 가상 HTTP 시간 미리보기 추가. Phase 2 도구의 서버/화면 흐름을 재사용.
- Backend 실행 코드 및 의존성 변경 없음. 새 코드에 한국어 설명 추가.

## 검증

Windows / Python 3.14.7 / Qt 6.11.2.

- 전체 테스트: **98 passed**, 30.07초. 기존 72개 + 시간 처리 26개.
- Ruff 통과. 가상 HTTP 미리보기의 PNG를 확인하여 한글, 시각/활성 시간 배치 정상 확인.
- 기존 Starlette/httpx deprecation warning 1건.

시간대/0밀리초/초 미만/24시간 이상, 잘못된 타입·날짜·시간대·누락 필드,
비수집 상태의 시간 객체, 정상 갱신, 서버 값 유지, A→B→A 가상 응답,
오류 제거·자동 복구 및 구형 응답으로 전환을 검증했다.
기존 폴링/timeout/종료 정리/제목 선택·스크롤 검증도 통과했다.

가상 응답의 A→B→A 표시는 Backend 재방문 계산 검증을 의미하지 않는다.
실제 활성 창 감지, 누적 활성 시간 계산, 작업 종료·재방문·반복 이벤트 병합,
Backend와 실제 시간 일치 검증은 미완료다. Phase 2 전체와 Phase 3 전체는 완료 처리하지 않는다.
Backend 담당자는 [시간 API 규격](../dev/activity-timing-api.md)과 Shared 정의를 반영해야 한다.

미리보기: `python tools/preview_phase3_client.py`.
