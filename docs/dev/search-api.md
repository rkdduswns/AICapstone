# Phase 11 명시적 조건 검색 API

상태: Client/Shared 선행 구현 및 가상 HTTP 검증. Backend의 실제 저장소 검색은 미구현이다.
Client는 명시적으로 입력한 조건을 제출하고 반환한 작업 메타데이터를 표시한다.
검색 요청을 제출하기 전에는 자동으로 기록을 조회하지 않는다.

## 요청

GET http://127.0.0.1:8765/records/search

포트는 기존 실행 설정을 따른다. 각 조건은 URL 쿼리 값으로 인코딩한다.
공통 loopback HTTP 계층의 프록시 비활성화·리다이렉트 거부·3초 timeout을 사용한다.
요청 본문은 없고 Accept: application/json을 보낸다.

| 쿼리 필드 | 의미 |
|---|---|
| keyword | 창 제목 또는 페이지 제목에 포함되는 문자열. 빈 문자열은 제한 없음 |
| process_name | 프로세스명 완전 일치. 빈 문자열은 제한 없음 |
| source_type | all / web / document / pdf / docx |
| active_from | 마지막 활성 시각의 포함 하한. 시간대 있는 ISO 8601, 생략 시 제한 없음 |
| active_before | 마지막 활성 시각의 제외 상한. 시간대 있는 ISO 8601, 생략 시 제한 없음 |
| sort | recent: 마지막 활성 내림차순, oldest: 오름차순 |
| limit | 1~20 정수. 현재 화면은 20건 요청 |

제목 키워드는 최대 200자, 프로세스명은 최대 100자다. 제어 문자는 거부한다.
Client는 양끝 공백을 제거하고 프로세스명만 casefold한다.
Backend는 제목 부분 일치와 프로세스명 완전 일치를 대소문자 구분 없이 처리한다.
프로세스명 정규화 후에도 길이 제한을 적용한다.
출처·시간·제목·프로그램 조건은 모두 AND로 결합한다.

- all: 일반 작업과 출처 없는 구형 기록을 포함한다.
- web: HTTP(S) URL이 있는 브라우저 작업.
- document: 지원 파일 출처가 있는 PDF/DOCX 전체.
- pdf/docx: 해당 파일 유형.
- 제목은 창 제목 또는 페이지 제목 중 하나가 키워드를 포함하면 일치한다.
  파일 경로 자체의 부분 검색은 이번 제목 조건에 포함하지 않는다.
- 시각은 실제 순간으로 비교한다. last_active_at이 하한 이상·상한 미만인 기록을 선택한다.
  양쪽 경계가 있으면 하한은 상한보다 앞서야 한다.
- 같은 시각이면 ID 오름차순으로 순서를 고정한다.

## 날짜 입력

화면은 전체 기간·오늘·날짜 선택을 제공한다. 날짜 선택의 처음과 마지막 날짜를 모두 포함한다.
Client는 시작 날짜 자정과 마지막 날짜 다음 날 자정을 각각 PC 현지 시각으로 변환해
UTC 오프셋과 함께 보낸다. DST 전환일에도 하루를 고정 24시간으로 더하지 않는다.
오늘은 검색 버튼을 누른 시점의 PC 날짜를 사용한다.
역전된 날짜나 표시할 수 없는 범위는 요청 전에 안내한다.
검색 기간은 열람 시작이나 본문 확보 시각 대신 마지막 활성 시각 기준임을 화면에 표시한다.

## 성공 응답

HTTP 200 / Content-Type: application/json.

~~~json
{
  "ok": true,
  "data": {
    "request": {
      "keyword": "기획",
      "process_name": "chrome.exe",
      "source_type": "web",
      "active_from": null,
      "active_before": null,
      "sort": "recent",
      "limit": 20
    },
    "records": [{
      "id": "sample-record",
      "application": "Google Chrome",
      "process_name": "chrome.exe",
      "window_title": "가상 기획 창",
      "started_at": "2026-10-15T08:00:00+09:00",
      "last_active_at": "2026-10-15T08:02:00+09:00",
      "active_duration_ms": 60000,
      "foreground_count": 1,
      "browser": {
        "browser": "chrome",
        "page_title": "가상 기획 자료",
        "url": "https://example.com/planning"
      },
      "document": null
    }],
    "has_more": false,
    "service": "contexttrace-backend",
    "api_version": 1
  },
  "error": null
}
~~~

- request는 서버가 확인한 정규화된 전체 조건이다. 빈 문자열·null·limit도 생략하지 않는다.
  Client가 제출한 값과 정확히 일치해야 한다.
- ok는 boolean true, error는 필수 null, 서비스명과 정수 API 버전은 기존 계약을 따른다.
- records는 최대 요청 limit건의 ContextRecord다. 필드 검증은
  [최근 기록](recent-records-api.md), [브라우저](browser-api.md),
  [파일 출처](document-content-api.md) 계약을 재사용한다.
- 검색 결과 한 행의 웹/파일 출처는 동시에 제공하지 않는다. 일반 작업은 둘 다 생략/null이다.
- 중복 ID, 잘못된 기록·시각·출처, 요구 정렬과 다른 순서는 응답 전체 오류다.
  Client는 잘못된 행을 빼거나 결과를 재정렬해 성공 처리하지 않는다.
- has_more는 필수 bool. true이면 limit건이 반환돼야 하며 더 많은 일치 기록이 있다는 뜻이다.
  전체 건수를 추정하지 않고 조건을 좁히도록 안내한다. 이번 화면에는 페이지 이동이 없다.
- 빈 결과는 records: [], has_more: false다. 오류와 구분한다.

## 화면과 비동기 상태

목록은 제목·출처·프로그램·마지막 활성 시각을 표시한다.
선택 상세는 전체 제목, URL/파일 경로, 프로그램·프로세스, 열람 시작·마지막 활성,
누적 활성 시간·재방문, 원본 창 제목·기록 ID를 표시한다.
표·툴팁·상세·조건 확인 문구는 일반 텍스트다. 링크나 HTML을 실행하지 않는다.
창 제목에서 경로/URL을 추정하지 않으며 원문 출처를 임의 정규화하지 않는다.
검색 결과에는 본문/문서 조각을 포함하지 않는다.

조건 편집은 진행 중 요청을 취소하고 이전 목록·상세·적용 조건을 비운다.
검색 중 중복 제출을 막고 취소 버튼으로 중단할 수 있다.
취소된 늦은 응답이 새 조건이나 새 결과를 덮지 못하게 한다.
재연결·종료에서는 요청과 결과를 정리한다. 입력 초안은 재연결에도 유지하고
자동 재검색은 하지 않는다. 오류 후 같은 입력으로 수동 재검색할 수 있다.

| 상황 | Client 표시 |
|---|---|
| HTTP 404 | 조건 검색 기능 준비 중 |
| HTTP 403 | 조회 거부·개인정보 설정 확인 |
| HTTP 422 | 조건 처리 불가·입력 확인 |
| 다른 HTTP 오류·연결 실패·timeout | 각 실패 안내·수동 재검색 |
| 조건 확인 불일치·계약 오류 | 호환되지 않는 검색 응답 |
| 정상 빈 목록 | 조건에 맞는 기록 없음 |

## 통합 시 남은 작업

Backend는 저장된 작업을 대상으로 조건 결합·필터·정렬·limit/더 있음 판정을 구현한다.
입력과 limit을 서버에서도 검증하고 개인정보 정책상 조회가 허용되는 기록만 반환한다.
Phase 10의 DocumentChunk/SourceMetadata는 본문 확보 시점의 검색 근거용 구조다.
이번 조건 검색은 ContextRecord 메타데이터 계약을 사용하여 조각 생성·임베딩 완료와 분리해 진행한다.
실제 저장소의 오늘/날짜·Chrome/PDF·복수 조건·빈 결과와 삭제/보호 정책을 연결해 검증한다.
