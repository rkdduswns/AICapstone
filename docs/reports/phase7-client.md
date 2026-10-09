# Phase 7 Client 구현 및 검증

작업 확인일: 2026-10-09. 브랜치: `feat/phase7-client`.
상태: **Client DONE / 전체 IN_PROGRESS**. 실제 Browser/Backend 연동·저장 전 차단 검증은 남아 있다.

## 기준과 범위

최신 main `d9c47d1be5469085728e18dc9d53e2de0625459b` 및 PR #9 미병합 상태를 확인했다.
Phase 5/6 개인정보 UI와 최근 작업 상세에 의존하므로 `feat/phase6-client`의
`9d8ad350c2dec5ca7c2ed7089fa657aeabad2908`에서 분기했다. PR 기준도 `feat/phase6-client`다.
선행 PR 병합 후 main 기준으로 갱신한다.

Phase 7의 두 Client 항목과 공통 계약/가상 검증을 구현했다.
추상 설계의 URL 출처를 선택적 `BrowserPage`로 구체화하고, URL 차단 입력은 세 가지 명시적 방식으로 정했다.
원래 기획은 보존했고, Backend 저장 형식이나 Browser 전송 계층을 구현한 것으로 처리하지 않는다.

## 구현

- 최근 작업 상세에 Chrome/Edge, 페이지 제목, URL 표시. 창 제목과 구분하고 원문을 일반 텍스트로 유지.
- 출처 없는 기존 기록, null URL/빈 제목의 내부 탭, 잘못된 응답 처리.
- 개인정보 보호의 프로그램/URL 차단 탭. 도메인·전체 URL·URL 시작 부분 추가/삭제/되돌리기/적용.
- 최대 100개 규칙, 호스트 정규화, 중복 제거, URL 형태 검증과 명확한 입력 안내.
- 선택 `blocked_urls` 필드와 URL 전용 PUT. 미지원과 빈 설정을 구분.
- 확인 응답 전 성공 표시 금지, PUT 응답 일치 검증, 미적용 초안 보존, 실패 시 GET 복구.
- Backend의 `blocked_url` 상태 표시. Client 자체 차단 판정은 없음.
- 함수 역할·처리 흐름·설계 이유 및 URL 파싱/비동기 확인/초안 보존 주의를 한국어 주석과 docstring으로 설명.
- [기술 스택 목록](../dev/technology-stack.md), API 계약, Phase 체크리스트와 가상 미리보기 추가.

새 외부 의존성이나 Backend 실행 코드는 추가하지 않았다.
실제 탭/클립보드를 읽거나 URL/설정을 Client 파일·로그에 저장하지 않는다.

## 검증

Windows 10 / Python 3.14.7 / PySide6·Qt 6.11.2.

| 범위 | 결과 |
|---|---|
| 신규 테스트 | 41개 추가: URL 입력 계약 23, 기록 출처 12, 개인정보 UI/HTTP 6 |
| 전체 `pytest -q` | **263 passed**, 53.30초 |
| `ruff check src tests tools` | 통과 |
| `pip check` | 의존성 문제 없음 |
| `git diff --check` | 통과 |
| Phase 7 상세/URL 설정 미리보기 PNG | 620×740 화면의 한글·원문 제목·URL·탭·버튼 배치 확인 |

가상 HTTP로 Chrome/Edge 표시, 새 탭/구형 응답, 선택/새로고침/오류 시 출처 제거,
URL 설정 단독 전송, 정규화·중복·최대 개수, 초안 유지, 재연결, 전체 해제 및 되돌리기를 확인했다.
잘못된 스킴/인증 정보/포트/제어 문자와 응답 타입, 차단 규칙 없는 판정 모순을 거부한다.
PUT 결과 불일치·HTTP 오류·서버 적용 후 timeout에서 성공을 추측하거나 쓰기를 반복하지 않음을 검증했다.
기존 Starlette/httpx deprecation warning 1건은 유지된다. CI의 Windows Python 3.11/3.12 결과는 PR에 기록한다.

미리보기: `python tools/preview_phase7_client.py`.
URL 설정으로 시작: `python tools/preview_phase7_client.py --settings`.
설정은 가상 서버 메모리에만 반영한다. URL별 차단 판정은 구현하지 않은 고정 예시다.

## 남은 실제 검증

Chrome/Edge 확장 실행과 활성 탭·페이지 변화 감지, Browser 정보 수신,
Windows 작업 연결, 저장 전 URL 검사, 기록 갱신, 차단 데이터 미저장은 Backend 연결 후 확인한다.
Client/Shared/가상 검증 6개만 완료로 표시하고 실제 테스트와 전체 완료 조건은 미완료로 유지한다.
계약 및 통합 조건: [브라우저 출처와 URL 설정](../dev/browser-api.md).
