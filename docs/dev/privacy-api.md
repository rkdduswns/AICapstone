# Phase 5 개인정보 설정 API 계약

후속 확장: [클립보드 설정](clipboard-api.md), [Phase 7 URL 차단 설정·사유](browser-api.md).
아래는 Phase 5 기본 계약이며 후속 선택 필드/사유는 해당 확장 계약을 함께 따른다.

상태: 실제 Backend 정책·수집기·SQLite 연결에 이어 `feat/privacy-settings-persistence`에서
지원 중인 세 설정의 저장·복원을 추가했다. 자동 검증 범위와 남은 실환경 검증은
[설정 영속화 보고서](../reports/privacy-settings-persistence.md)를 따른다. Phase 전체 완료와 구분한다.
Client는 설정을 요청하고 Backend의 판정을 표시한다. 프로세스 감지·민감 문자열 판정·지속 저장은 하지 않는다.

## 요청

기존 `127.0.0.1:<port>`와 `ok/data/error`, `service: contexttrace-backend`, `api_version: 1`을 유지한다.
모든 정상 응답은 HTTP 200 / `application/json`과 아래 전체 상태다. 새 경로 추가로 기존 API는 변경하지 않는다.

| 메서드/경로 | 요청 본문 | 의미 |
|---|---|---|
| `GET /privacy` | 없음 | 같은 시점의 적용 설정과 현재 기록 가능 여부 |
| `PUT /privacy/paused` | `{"paused": true}` 또는 `false` | 일시정지 목표값만 적용. 토글 명령이 아님 |
| `PUT /privacy/blocked-processes` | `{"blocked_processes": ["chrome.exe"]}` | 차단 목록 전체 교체. 빈 배열은 전체 해제 |

쓰기 요청은 `Content-Type: application/json`, `X-ContextTrace-Client: desktop` 헤더를 보낸다.
Backend는 정확한 필드/타입을 검사하고 다른 설정을 유지한다. 입력 오류에는 HTTP 422와 기존 오류 envelope를 사용한다.
일시정지를 누를 때 차단 목록 입력 초안을 함께 전송하지 않으며, 목록 적용이 일시정지를 해제하지 않는다.
여러 Client의 같은 필드 변경은 마지막으로 적용한 요청을 따른다. 별도 필드를 덮어쓰는 전체 설정 PUT은 제공하지 않는다.

## 설정 저장과 복원

`paused`, `blocked_processes`, `clipboard_enabled`만 작업 기록과 같은 SQLite DB의
`privacy_settings` 한 행에 저장한다. URL 차단 설정은 여전히 미지원이며 `blocked_urls: null`을 반환한다.
`--db-path`를 지정하면 해당 DB의 설정을 사용한다. 별도 정책을 주입하지 않는 일반 실행에서 설정 행이 없는 신규·기존 DB는
수집 허용·빈 차단 목록·클립보드 꺼짐으로 시작한다.

저장된 설정이 있으면 이 세 필드에는 저장값이 우선한다. 명시적으로 주입한 `PrivacyPolicy`는
설정 행이 없는 DB의 초기값과 저장 대상이 아닌 정책에 사용하며, 저장된 일시정지를 덮어쓰지 않는다.
모듈 import나 `create_app()` 호출만으로 기본 저장소를 열지 않는다. 서버 시작 시에는 수집 루프를
예약하기 전에 복원하고, lifespan 없이 처리되는 요청도 endpoint의 감지·수신 처리·저장 로직 전에 복원한다.

PUT은 `BEGIN IMMEDIATE` 트랜잭션에서 최신 저장값을 읽고 요청한 필드만 바꾼다.
커밋이 성공한 뒤 정책 메모리와 클립보드 수집기에 적용하며, 적용 완료 후에만 HTTP 200을 반환한다.
저장 실패는 HTTP 503과 기존 오류 envelope로 응답하고 이전 메모리 설정을 유지한다.
커밋 후 적용이 실패한 경우에는 DB에 목표값이 저장됐을 수 있다. 진행 중 세션을 닫고
수집 일시정지·클립보드 꺼짐 상태로 전환한 뒤 HTTP 503을 반환하며, 다음 요청·수집 주기에 복원을 다시 시도한다.
Client는 이 경우에도 PUT을 자동 재전송하지 않고 GET으로 상태를 확인한다.

설정 행 없음과 복원 실패는 다르다. 손상된 값이나 DB 읽기 오류를 기본 허용값으로 초기화하지 않는다.
시작 시 복원 실패는 서버 시작을 중단하고, 요청 시 실패는 HTTP 503을 반환한다.
복원이 성공하기 전까지 수집하지 않으며 저장된 원문도 덮어쓰지 않는다.
클립보드 사용을 복원할 때는 현재 변경 번호로 기준을 다시 잡아 복원 이전의 복사를 새 이벤트로 저장하지 않는다.

같은 DB에는 Backend 하나만 실행하는 범위다. 필드별 저장은 다른 필드의 최신 저장값을 보존하지만,
별도 Backend 프로세스 사이에서 적용 정책을 실시간으로 동기화하는 기능은 제공하지 않는다.
검증 절차와 결과는 [설정 영속화 보고서](../reports/privacy-settings-persistence.md)에 기록한다.

## 응답 구조

```json
{
  "ok": true,
  "data": {
    "service": "contexttrace-backend",
    "api_version": 1,
    "settings": {"paused": false, "blocked_processes": ["chrome.exe"]},
    "recording": {"allowed": false, "reason": "blocked_program"}
  },
  "error": null
}
```

- Shared 정의는 `src/shared/privacy.py`의 `PrivacySettings`, `RecordingStatus`, `PrivacyState`, `PrivacyResponse`다.
- `ok`는 boolean true, `error`는 필수 null, `api_version`은 정수 1이다. boolean을 정수로 취급하지 않는다.
- `settings.paused`와 `recording.allowed`는 필수 boolean이다.
- `blocked_processes`는 필수 배열, 최대 100개다. 각 값은 경로 없는 `.exe` 실행 파일 이름이며 최대 255자다.
  공백뿐인 이름, 빈 stem, 제어 문자, `< > : " / \ | ? *`는 허용하지 않는다.
- Client 입력에서 앞뒤 공백과 빈 줄은 제거하고 소문자로 바꾼 뒤 중복 제거·문자열 오름차순 정렬한다.
  Backend도 같은 정규형으로 저장/응답한다. 응답의 중복·대문자·잘못된 순서/형식은 계약 오류로 거부한다.
- 이름 비교는 실행 파일 basename을 소문자로 정규화한 정확한 일치다. 경로·정규식·와일드카드·URL 차단은 이번 입력 범위에 없다.
- 정상 envelope, 모든 설정/판정 필드는 필수다. 알 수 없는 추가 필드는 무시한다.
- 응답에는 실제 민감 문자열, 창 제목, 필터 일치 원문을 넣지 않는다.

| `recording.reason` | `allowed` | Client 표시 |
|---|---|---|
| `allowed` | true | 기록 가능 |
| `paused` | false | 기록 일시정지됨 |
| `blocked_program` | false | 기록 차단 · 차단 프로그램 |
| `sensitive_content` | false | 기록 차단 · 민감 문자열 |
| `no_active_window` | false | 기록 대기 · 활성 창 없음 |
| `unsupported` | false | 기록 불가 · 미지원 환경 |
| `error` | false | 기록 불가 · 보호 검사 오류 |

일시정지가 최우선이므로 `settings.paused`가 true인 경우에만 `reason: paused`다.
`allowed`는 `reason: allowed`일 때만 true다. `blocked_program`이면 비어 있지 않은 차단 목록이 필요하다.
그 밖의 사유 선택과 민감 패턴은 Backend에서 판정한다. Client가 현재 창을 차단 목록과 비교하여 저장 여부를 단정하지 않는다.
`/activity/current`의 `collecting`은 감지 성공이지 저장 허용이 아니다. 기존 활동 응답을 보호 성공으로 해석하지 않는다.

## Client 동작과 실패 처리

1. 호환되는 `/health` 확인 후 탭과 무관하게 즉시 조회하고, 응답 완료 1초 뒤 다음 GET을 요청한다.
2. 일시정지 버튼과 마지막 확인 결과는 모든 탭 위에 표시한다. 상세 확인 시각, 차단 목록 편집, 상태 재확인은 개인정보 보호 탭에 둔다.
3. 서버 확인 전에는 변경 버튼을 잠그고 `미확인`으로 표시한다. 정상 응답에 포함된 판정만 표시한다.
4. 일시정지/재개 또는 목록 적용 시 진행 중 GET을 취소하고 PUT 하나만 보낸다. 입력과 변경 버튼을 잠그고 요청 중임을 표시한다.
5. PUT 응답의 요청 대상 필드가 목표값과 일치해야 적용 완료다. 응답 전 버튼 상태를 반전하거나 성공을 표시하지 않는다.
6. timeout/연결 오류/서버 오류/잘못된 응답 시 기존 판정을 지우고 미확인으로 전환한다.
   쓰기 실패는 서버에서 이미 적용했을 가능성이 있어 `설정 적용 여부 미확인`으로 표시한다.
   **PUT은 자동 재전송하지 않고 GET으로 적용 상태를 다시 확인**한다.
7. 404/405는 기능 준비 중으로 표시하고 자동 조회를 중지한다. 보호 상태 재확인 또는 재연결로 다시 시도한다.
8. 목록 입력 초안은 폴링·일시정지 변경·연결 재확인·오류로 덮어쓰지 않는다. 적용 성공 후 정규형으로 표시한다.
   `입력 되돌리기`는 마지막으로 확인된 서버 목록으로만 복원하며 쓰기 요청을 보내지 않는다.
9. 연결 재확인/종료는 요청과 타이머를 취소한다. 이는 서버 설정 변경을 취소하거나 기록을 중지한다는 뜻이 아니다.

공통 전송 계층은 요청 3초 제한, loopback 고정, 프록시 비활성화, 리다이렉트 거부를 유지한다.
화면은 plain text로 표시하고 설정/응답/민감값을 Client 파일이나 로그에 저장하지 않는다.

## Backend 보호 계약과 잔여 검증

아래는 구현과 실제 환경 검증을 함께 요구하는 계약이다. 현재 연결된 일시정지·프로그램 차단·민감 본문 저장 거부와
통합한 설정 재시작 복원과 미구현 URL 차단을 구분하며, 자동 테스트 통과만으로 전체 Phase를 완료 처리하지 않는다.

- 일시정지와 프로그램 차단, 기본 민감 패턴을 **저장 전**에 검사한다. 판정 실패도 저장 불가로 처리한다.
- 설정 변경을 수집/저장 작업과 동기화한다. PUT 200은 적용 완료 이후 반환하며, 이미 대기 중인 데이터에도 새 보호 정책을 적용한다.
- 응답의 설정과 판정은 일관된 스냅샷이어야 한다. 현재 저장·재시작 정책은 위의 설정 저장과 복원 규칙을 따른다.
- 일시정지 중 저장 안 됨, 차단 프로그램/민감 문자열 저장 안 됨, 재개 후 허용된 데이터만 저장됨, 기존 기록 불변을 실제 저장소로 검증한다.
- 설정 API와 작업 데이터 API의 접근 제어를 구현한다. loopback과 고정 헤더만으로 로컬 프로세스를 인증할 수는 없다.
  웹 Origin 요청·CORS를 무제한 허용하지 않고, JSON/전용 헤더 검증을 유지한다. 인증 방식과 연동 검증은 Backend 통합 범위다.
- 기본 민감 패턴의 대상·오탐 정책과 차단 사유 우선순위는 Backend에서 확정한다. URL/사용자 패턴 편집 UI는 이후 해당 Phase에서 다룬다.

가상 서버의 상태 전환은 실제 보호 계층을 대체하지 않는다. 현재 Backend·SQLite 자동 검증과
실제 Windows 수집·화면의 수동 검증을 구분하며, Phase 5 전체 완료 여부는 Phase 문서의 잔여 조건을 따른다.

구현 참고: [Qt 비동기 PUT](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkAccessManager.html).

Phase 6은 선택 `settings.clipboard_enabled`와 `PUT /privacy/clipboard`를 추가한다.
누락/null은 기능 미지원이며 기존 Phase 5 필드의 의미는 유지한다. [클립보드 계약](clipboard-api.md)을 따른다.
