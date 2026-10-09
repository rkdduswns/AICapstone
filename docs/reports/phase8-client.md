# Phase 8 Client 구현 및 검증

작업 확인일: 2026-10-10. 브랜치: `feat/phase8-client`.
상태: **Client DONE / 전체 IN_PROGRESS**. Browser/Backend 본문 수집·정제·중복 제거·실제 저장 검증은 남아 있다.

## 기준과 범위

최신 main `d9c47d1be5469085728e18dc9d53e2de0625459b`와 PR #10 미병합 상태를 확인했다.
Phase 7의 브라우저 출처 및 최근 기록 상세에 의존하여 `feat/phase7-client`의
`262efb62c1d718eff02445c821ac3a325264f860`에서 분기했다. PR 기준도 `feat/phase7-client`다.
선행 PR 병합 후 main 기준으로 갱신한다.

기존 Phase 8 계획에는 Browser/Backend 수집 항목만 있었다.
Client 선행 개발 범위로 저장 결과를 확인할 웹 본문 상세와 API 계약을 추가했다.
원래 수집 항목과 전체 완료 조건은 보존하며, Client 완료를 실제 수집 완료로 확대하지 않는다.

## 구현

- 최근 기록 상세의 `웹 본문` 탭. 탭 진입 시만 작업 ID로 저장 본문 조회.
- 수집 당시 페이지 제목·URL·수집 시각·본문 표시. Client 조회 시각과 수집 시각 구분.
- 읽기 전용 일반 텍스트, 최대 50,000자, 일부만 저장된 본문과 정상 빈 본문 구분.
- 작업 ID뿐 아니라 브라우저 종류/URL도 대조하여 페이지 이동 후 출처가 다른 본문 표시 방지.
- 일반 작업·새 탭·구형 기록의 URL 누락 시 요청 생략.
- 선택 변경/목록 갱신/재연결/종료에서 이전 요청과 본문 정리.
- 조회 거부/미지원/오류/timeout 구분 및 수동 복구.
- 기존 비동기 전송과 URL/시각 검증 재사용. 새 외부 의존성, Backend 실행 코드 변경 없음.
- Shared 계약, 가상 미리보기, 한국어 함수 설명·처리 흐름·설계 이유 주석 추가.

실제 브라우저를 읽거나 외부 URL에 접근하지 않는다. Client는 본문/출처를 파일이나 로그에 저장하지 않는다.

## 검증

Windows 10 / Python 3.14.7 / PySide6·Qt 6.11.2.

| 범위 | 결과 |
|---|---|
| 신규 계약/가상 HTTP 테스트 | **34 passed** |
| 기존 회귀 포함 전체 `pytest -q` | **297 passed**, 59.48초 |
| `ruff check src tests tools` | 통과 |
| `pip check` | 의존성 문제 없음 |
| `git diff --check` | 통과 |
| 정상/50,000자 일부 본문/조회 거부 미리보기 PNG | 한글·태그 원문·출처·수집 시각·상태 안내, 620×740 배치 확인 |

응답 타입/필수 필드/작업 ID/URL/시각/길이 검증, 빈 본문, 수집 시점 제목 변경, Unicode 최대 길이를 확인했다.
가상 HTTP로 지연 조회, 새로고침, 특수문자 ID 인코딩, 일반 작업/새 탭 요청 생략,
늦은 응답 취소, 같은 ID의 URL 변경 후 목록 갱신, 403/404/500/잘못된 JSON,
timeout·중복 요청·재연결·종료 및 수동 복구를 검증했다.
기존 Starlette/httpx deprecation warning 1건은 유지된다.
Windows Python 3.11/3.12 CI 결과는 PR에 기록한다.

## 미리보기와 남은 작업

`python tools/preview_phase8_client.py`로 정상 본문을 확인한다.
`--web-state empty|truncated|unsupported|denied`로 각 상태를 선택한다.
`--snapshot <PNG 경로>`는 선택 상태가 표시된 앱 화면을 저장하고 종료한다.
가상 응답 성공은 실제 페이지 추출·저장 전 차단·영속 저장 검증을 의미하지 않는다.

Browser의 기사/문서/SPA 본문 추출과 갱신, Backend 중복 제거·원본 작업 연결,
수집/저장량 제한 및 차단 페이지 미수집·미저장을 후속 구현·통합에서 확인한다.
Phase 체크리스트는 Client/Shared/가상 검증 **5/23**만 완료로 기록한다.
계약: [저장 웹 본문 API](../dev/web-content-api.md).
