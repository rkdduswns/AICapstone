# Phase 7 브라우저 출처 및 URL 설정 계약

저장된 페이지 본문과 수집 시각을 확인하는 후속 기능은 [Phase 8 웹 본문 계약](web-content-api.md)을 따른다.

상태: 2026-10-22 통합 브랜치에 수동 Chrome/Edge 확장·Backend 작업 ID 연결·저장·본문 조회를 구현했다.
확장 설치 후 Windows 수동 검증·자동 탭 이벤트·URL 차단은 남아 있다. 전송·설치는 [이력 연결 계약](history-source-linking.md)을 따른다.
아래 URL 차단 설정은 Client의 후속 Backend 계약이며 현재 실제 API는 기능 미지원으로 표시한다.
기획의 `ContextRecord.url` 개념을 브라우저 종류·페이지 제목·URL을 가진 선택적 `browser` 객체로 구체화했다.
Windows 창 제목과 페이지 제목을 구분하고 기존 기록 응답을 유지하기 위한 구조다. 기획 원문과 저장 모델은 변경하지 않는다.

## 최근 작업의 브라우저 출처

기존 `GET /records/recent?limit=20`의 각 기록에 다음 선택 필드를 추가한다.
기존 envelope, 서비스 이름, `api_version: 1`, 시간/정렬/기록 ID 규칙은 [최근 기록 계약](recent-records-api.md)을 따른다.

```json
{
  "browser": {
    "browser": "chrome",
    "page_title": "가상 참고 자료",
    "url": "https://example.com/research?topic=sample#intro"
  }
}
```

| 필드 | 규칙 |
|---|---|
| 기록의 `browser` | 생략/null이면 출처 없음 또는 서버 미제공. 객체이면 아래 세 필드 필수 |
| `browser.browser` | `chrome` 또는 `edge` |
| `browser.page_title` | 문자열. 빈 문자열은 `(제목 없음)` 표시 |
| `browser.url` | HTTP(S) URL 문자열 또는 null. 새 탭/내부 페이지/미지원 스킴은 null |

Client는 URL 원문을 일반 텍스트로 표시하며 창 제목에서 주소를 추정하지 않는다.
URL을 자동 실행하지 않고, 제목의 HTML 모양 문자열도 원문 그대로 표시한다.
선택 변경/새로고침/오류/연결 재확인에서는 이전 출처를 지운다.
잘못된 브라우저 객체/URL을 부분 표시하지 않고 기록 응답 전체를 실패 처리한다.

## URL 차단 설정

`GET /privacy` 및 모든 개인정보 PUT 응답의 `data.settings`에 `blocked_urls`를 추가한다.
생략/null은 기능 미지원, `[]`는 지원되지만 설정된 규칙 없음이다.

```json
{
  "paused": false,
  "blocked_processes": [],
  "clipboard_enabled": false,
  "blocked_urls": [
    {"kind": "domain", "value": "private.example.com"},
    {"kind": "prefix", "value": "https://example.com/private/"}
  ]
}
```

- `PUT /privacy/blocked-urls`는 `{"blocked_urls": [...]}`만 받는다. 다른 설정은 유지한다.
- 목록 전체를 교체하며 빈 배열은 URL 규칙 전체 해제다. 최대 100개, 규칙 객체는 `kind`/`value` 두 필드다.
- 기존 HTTP/JSON, loopback, 3초 timeout, `X-ContextTrace-Client: desktop` 헤더를 유지한다.
- 정상 응답은 적용된 전체 개인정보 상태다. 요청한 규칙과 응답 규칙이 같아야 Client가 적용 완료로 표시한다.
- 입력 오류는 Backend에서 HTTP 422 및 기존 오류 envelope로 반환해야 한다.
- 목록 입력·추가·선택 삭제는 Client 초안만 변경한다. `URL 차단 목록 적용`을 눌러야 PUT을 보낸다.
- 입력란에 주소가 남아 있으면 목록에 추가하거나 지우도록 안내한다. 입력란의 주소를 몰래 제외하고 저장하지 않는다.
- 폴링, 프로그램/클립보드/일시정지 변경, 재연결, 실패는 미적용 목록과 입력란을 보존한다.
- 오류/미지원/쓰기 중에는 적용을 잠근다. 실패한 PUT은 자동 재전송하지 않고 GET으로 상태를 확인한다.

## 입력 정규형과 차단 범위

다음 범위는 Backend 구현 시 사용할 계약이다. Client에는 현재 URL과 규칙을 비교하는 차단 판정기가 없다.

| `kind` | 입력 예 | Backend 적용 범위 |
|---|---|---|
| `domain` | `example.com` | 호스트가 정확히 같거나 `.` 경계의 하위 도메인. `a.example.com` 포함, `evil-example.com` 제외. 스킴·포트와 무관 |
| `exact` | `https://example.com/path?q=a#top` | 정규화한 전체 URL 일치. 경로·쿼리·fragment 대소문자 및 값 구분 |
| `prefix` | `https://example.com/private/` | 정규화한 URL이 입력값으로 시작. `/private`는 `/private-other`도 포함하므로 폴더 범위는 `/private/` 입력 |

입력 앞뒤 공백을 제거하고 도메인은 소문자 IDNA 표기로 통일한다.
도메인은 총 253자 이하, 각 label 1~63자, 영숫자/중간 하이픈만 허용한다.
스킴·포트·경로·와일드카드·끝의 점을 포함한 도메인 입력은 거부한다.

HTTP(S) URL은 최대 8,192자이며 호스트가 필수다. 인증 정보, 공백/제어 문자, `\`, `<`, `>`, `"`,
잘못된 `%` 인코딩, 잘못된 포트/괄호를 거부한다. 명시적 포트는 1~65535이며 IPv6 주소도 지원한다.
스킴/호스트를 소문자로, 국제화 호스트를 IDNA로, IPv6를 압축 표기로 통일한다.
기본 포트(http 80/https 443)를 생략하고 빈 경로는 `/`로 만든다.
경로/쿼리/fragment의 대소문자, percent encoding, query 순서는 바꾸지 않는다.
`prefix`에는 값이 있는 쿼리/fragment를 허용하지 않는다. 빈 `?`/`#` 구분자는 정규화 시 제거된다.
일반 regex, `*` 패턴, 경로 dot-segment/percent encoding 동치 변환은 이번 계약에 포함하지 않는다.
따라서 같은 페이지로 해석될 수 있는 서로 다른 경로 표기가 자동으로 같은 규칙이 되지는 않는다.

규칙은 `(kind, value)` 기준 중복 제거 및 문자열 오름차순으로 전송한다.
서버 응답은 이 정규형이어야 한다. 반대로 최근 기록의 URL은 유효성만 검사하고 표시 원문을 유지한다.
Python의 URL 분리 함수는 자체 검증기가 아니므로, 원문의 제어 문자 등을 파싱 전에 검사한다.
근거: [Python URL parsing security](https://docs.python.org/3/library/urllib.parse.html#url-parsing-security).

## 보호 상태와 호환성

`recording.reason: blocked_url`, `allowed: false`를 추가하며 Client는 `기록 차단 · 차단 URL`로 표시한다.
이 사유에는 비어 있지 않은 `blocked_urls`가 필요하다. 목록이 있다고 현재 페이지 차단을 추측하지 않는다.
전체 일시정지는 계속 최우선이며 `paused: true`와 `reason: paused`가 함께 와야 한다.
실제 일치 URL/민감 내용은 보호 상태 응답에 넣지 않는다.

새 Client는 Phase 5/6 응답의 선택 필드 누락을 지원한다. 반대 방향은 완전 호환이 아니다.
구형 Client는 새 `blocked_url` 사유를 알지 못하므로 보호 상태를 미확인으로 처리한다.
Backend가 이 사유를 제공할 때 Phase 7 Client를 함께 사용해야 한다.

## 실제 통합 조건

Browser에서 활성 탭/탭 변경/같은 탭의 URL 변경을 감지하고 Backend에서 Windows 작업과 연결해야 한다.
Backend는 입력을 독립적으로 검증하고, 정규화된 URL을 저장 전에 차단 검사해야 한다.
차단 페이지의 제목·주소·본문·연결된 민감 데이터가 기록/색인/RAG에 남지 않게 하는 처리는 Backend 책임이다.
Client의 문법 검증이나 정규화는 브라우저의 모든 URL 동치/우회 사례에 대한 보호 검증을 대신하지 않는다.
실제 Chrome/Edge, 새 탭, 차단 URL, 일시정지, 저장소 재조회는 Backend 연결 후 검증한다.
