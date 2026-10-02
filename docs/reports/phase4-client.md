# Phase 4 Client 구현 및 검증

2026-10-02. 상태: **Client DONE / Phase 4 전체 IN_PROGRESS**.

## 시작 기준과 범위

작업 브랜치: `feat/phase4-client`. 기반: Phase 3 Client
`e698b9af7cd37f963fd94092b170e85e8d80e1d3`. 기존 98개 테스트에 기록 조회 검증을 추가했다.
2026-10-02 [PR #4](https://github.com/rkdduswns/AICapstone/pull/4)로 main에 병합했다.

## 구현

- `최근 기록` 탭: 최근 20건, 마지막 활성 시각순 목록과 선택 상세.
- 새로고침: 진행 중 중복 요청 방지, 목록 교체, 안정적인 ID에 따른 선택 복원.
- 호환되는 health 확인 후 탭 최초 진입 시 조회. 현재 작업 폴링과 독립적인 비동기 요청.
- 빈 목록, 미구현 API, 서버/연결/timeout/응답 오류 구분. 이전 기록 제거 및 수동 복구.
- 연결 재확인/종료 시 요청 취소와 늦은 응답 무시.
- Shared 저장 기록 조회 구조 및 [API 계약](../dev/recent-records-api.md).
- 시간대가 다른 응답의 실제 순간 정렬, 같은 순간의 ID순 고정, 중복 ID/잘못된 필드 거부.
- Phase 3과 공통 시각 검증/표시 함수 사용. Backend 누적값과 활성화 횟수를 표시하며 Client가 자체 계산·저장하지 않는다.
- 가상 기록 미리보기. 기존 Phase 2–3 도구의 HTTP 서버/화면 흐름 재사용.
- 이전 Client 브랜치를 대상으로 하는 PR에서도 Windows 검증이 실행되도록 CI 대상 확장.

Backend 실행 코드, DB, 실행/개발 의존성은 변경하지 않았다.

## 검증 결과

Windows 10 build 19045 / Python 3.14.7 / PySide6·Qt 6.11.2에서 기존 가상환경을 재사용했다.

| 검증 | 결과 |
|---|---|
| `python -m pytest -q` | **150 passed**, 36.05초. 기존 98개 + 기록 관련 52개 |
| `python -m ruff check src tests tools` | 통과 |
| `python -m pip check` | 의존성 문제 없음 |
| `git diff --check` | 통과 |
| Phase 4 가상 HTTP 미리보기 PNG | 한글, 3건의 최신순 목록, 상세 시각/활성 시간/재방문, 620×660 화면 배치 확인 |

실제 Qt 이벤트 루프와 가상 HTTP 서버로 다음을 검증했다.

- 호환성 확인 전 조회 차단, 탭 최초 조회, 정상 응답 후 불필요한 재조회 방지.
- 목록 교체/같은 ID 갱신/선택 유지/빈 목록, 서로 다른 시간대와 동일 시각 정렬.
- 초 미만/0/24시간 이상 활성 시간, 첫 활성화와 재방문 표시, 빈 제목·긴 한글·HTML 형태의 일반 텍스트.
- 필수 필드 누락, 잘못된 타입·날짜·오프셋·시간 순서·중복 ID·개수 초과.
- HTTP 404/500/리다이렉트, 연결 끊김, timeout, 잘못된 JSON/Content-Type, 수동 복구.
- 기록 요청 중 Qt 이벤트/현재 작업 조회 유지, 연결 재확인 및 창 종료 후 늦은 기록 제거.
- 별도 프로세스로 실행하는 **실제 기존 Backend**의 연결 실패→시작→종료→재시작 복구 및 기록 API 404 표시.

기존 Starlette/httpx deprecation warning 1건은 남아 있다. 이 작업에서 의존성을 변경하지 않았다.
GitHub Windows Python 3.11/3.12 검증은 커밋 `a3a1aec2ecce25bad7c1de7547279b766929d8a1`에서 성공했다.
[Actions 실행 결과](https://github.com/rkdduswns/AICapstone/actions/runs/36882317714)를 참고한다.

## 미완료와 다음 통합

실제 Windows 감지, 시간/재방문 계산, 저장소 생성·갱신·조회 endpoint,
Backend 재시작 후 동일 기록 유지와 실제 Client 통합은 미완료다.
가상 HTTP 표시 및 기존 Backend 프로세스 재시작 테스트는 **기록 지속 저장 검증이 아니다**.
따라서 Phase 2–4 전체를 DONE으로 바꾸지 않았다.

Backend 담당자는 [최근 기록 API](../dev/recent-records-api.md)의 Shared 구조와 저장/조회 완료 조건을 반영한다.
Client 다음 기능은 Phase 5 개인정보 보호 화면이지만, 이번 변경에는 포함하지 않는다.

화면 실행: `python tools/preview_phase4_client.py`.
