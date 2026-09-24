# Phase 2 현재 창 API 계약

상태: Client/Shared 구현 및 가상 HTTP 검증 완료. Backend endpoint와 Windows 감지는 아직 미구현이다.
이 문서를 Phase 2B 구현 기준으로 사용한다. Phase 1 `/health` 계약은 유지한다.

## 책임과 요청

- Client: Backend 연결 확인, 현재 창 조회, 응답 검증, 프로그램/제목/수집 상태 표시.
- Backend: Windows 활성 창 감지, PID/프로세스명 추출, 프로그램명 정규화, 지원 여부 판정.
- Shared: `src/shared/activity.py`의 프레임워크 독립 dataclass와 endpoint 상수.
- `GET http://127.0.0.1:<port>/activity/current`, 본문 없음, `Accept: application/json`.
- 응답 `Content-Type: application/json`, 현재 상태는 HTTP 200으로 반환한다.
- `/health`와 동일한 `service`, `api_version: 1`, `ok/data/error` envelope를 사용한다.
  새 경로의 추가이므로 기존 상태 API 버전을 변경하지 않는다.
- Client는 `/health` 호환성 확인 성공 후 최초 조회를 즉시 실행한다.
- 매 응답 완료 후 1초 뒤 다음 요청. 전체 요청 제한은 3초. 진행 중 요청은 중복 생성하지 않는다.
- 프록시와 리다이렉트를 사용하지 않고 loopback 서버에만 요청한다.

## 응답

```json
{
  "ok": true,
  "data": {
    "service": "contexttrace-backend",
    "api_version": 1,
    "collection_status": "collecting",
    "window": {
      "application": "Google Chrome",
      "process_name": "chrome.exe",
      "process_id": 1234,
      "window_title": "가상 자료 — ContextTrace 소개"
    }
  },
  "error": null
}
```

모든 예시는 가상 데이터다. 필드 이름과 필수 여부는 아래와 같다.

| 필드 | 규칙 |
|---|---|
| `ok` | 정확히 boolean true; 정수 1은 거부 |
| `error` | 필수, 정상 envelope에서 null |
| `data.service` | 정확히 `contexttrace-backend` |
| `data.api_version` | 정수 1; boolean/문자열은 거부 |
| `data.collection_status` | 아래 4개 상태 중 하나 |
| `data.window` | 필수; `collecting`일 때 창 객체, 나머지 상태에서는 null |
| `window.application` | Backend에서 정규화한 프로그램명. 공백만 있는 문자열은 거부 |
| `window.process_name` | 실행 프로세스 이름. 공백만 있는 문자열은 거부 |
| `window.process_id` | 양의 정수; boolean/문자열은 거부 |
| `window.window_title` | 필수 문자열. 빈 문자열은 유효하며 화면에 `(제목 없음)` 표시 |

| 수집 상태 | 의미 / Client 표시 |
|---|---|
| `collecting` | 현재 창 감지 성공 / 프로그램·프로세스·제목 표시 |
| `no_active_window` | 활성 창이 없는 정상 상황 / `대기 — 활성 창 없음`, 창 정보 비움 |
| `unsupported` | 지원하지 않는 창/환경 / `수집 불가`, 창 정보 비움 |
| `error` | 감지기가 현재 정보를 얻지 못함 / `감지 오류`, 창 정보 비움 |

`error` 수집 상태는 HTTP 전달 성공과 구분한다. 따라서 envelope는 `ok: true`이고 `error: null`이다.
예를 들어 창이 감지 도중 종료되어 일관된 PID/프로세스/제목을 얻지 못하면 이전 성공 값을 반환하지 않는다.
창 없음/미지원/감지 오류 중 실제 원인에 맞는 상태와 `window: null`을 반환한다.
상태에 맞지 않는 창 객체, 필수 필드 누락, 알 수 없는 상태는 Client에서 응답 오류로 거부한다.
추가 필드는 무시하되 필수 필드의 타입과 의미는 바꾸지 않는다.

## 실패 및 화면 동작

- HTTP 404: Phase 1 서버 등 현재 창 경로 미구현. `기능 준비 중` 표시.
- 기타 HTTP 오류, 연결 실패, 3초 timeout, JSON/필드/Content-Type 오류: 각각 안내하고 이전 창 정보 제거.
- 실패 후에도 1초 뒤 자동 재시도하여 정상 응답이 오면 복구한다. 사용자 연결 재확인은 필요하지 않다.
- `연결 확인` 클릭 시 기존 현재 창 요청과 타이머를 취소하고 `/health`부터 다시 검증한다.
- `/health` 확인이 실패하면 현재 창 자동 조회는 중단되며 사용자가 연결을 재확인한다.
- 창 종료 시 두 요청과 자동 조회 타이머를 정리한다. 늦은 응답은 화면에 반영하지 않는다.
- Backend 연결 영역은 마지막 `/health` 확인 결과다. 현재 창 수신 상태와 혼동하지 않도록 제목과 시각을 별도로 표시한다.
- `마지막 정상 수신`은 유효한 현재 창 응답을 받은 Client 시각이며 작업 시작 시각/활성 시간/저장 시각이 아니다.
- 프로그램명과 제목은 plain text로 표시한다. HTML/링크로 해석하지 않으며 긴 제목은 줄바꿈·스크롤로 확인한다.
- 같은 제목을 반복 수신할 때 사용자가 선택한 텍스트와 스크롤 위치를 유지한다.
- Client는 창 제목/프로세스 정보와 서버 오류 본문을 파일이나 로그에 저장하지 않는다.

## Phase 2B 인수인계

1. `src/backend/`에서 감지기를 구현하고 이 계약으로 endpoint를 제공한다. Client에서 Windows API를 호출하지 않는다.
2. 매 응답은 그 시점의 감지 결과를 반영해야 한다. 실패 시 이전 창 정보를 재사용하지 않는다.
3. 기존 `/health`와 오류 envelope를 유지한다. 전송/API 오류에는 기존 `ErrorResponse`를 사용한다.
4. 이 Client 우선 작업에는 API 접근 제어 구현이 없다. 실제 작업 정보를 제공하는 Backend 구현 시
   `health-api.md`의 작업 데이터 API 접근 제어 설계 항목도 함께 검토한다.
5. Chrome→VS Code, Word→Explorer, 동일 창, 최소화/바탕화면, 프로그램 종료를 실제 감지기와 확인한다.

작업 시간 계산(Phase 3), 저장(Phase 4), 일시정지/차단(Phase 5)은 이번 계약의 범위 밖이다.

## 참고

- [Qt 비동기 HTTP 요청](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkAccessManager.html)
- [Qt 타이머](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QTimer.html)
