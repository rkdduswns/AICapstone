# Phase 10 검색 문서 조각 및 출처 계약

상태: Shared 구조·Client 수신 검증 선행 구현. 실제 검색 데이터 생성은 Backend 미구현이다.
기획의 DocumentChunk 모델을 구체화하고 확보 당시 출처를 함께 반환하는 경계를 정의한다.
이 계약은 조회용 객체이며 DB 스키마·분할 방식·임베딩 모델·벡터 차원을 지정하지 않는다.
Phase 11 검색 응답에서 사용할 개별 조각/출처 구조다. HTTP 요청·응답 envelope는 해당 Phase에서 정의한다.

## 공통 데이터

Shared의 SourceMetadata와 DocumentChunk는 Qt/Client/Backend 내부 구현을 import하지 않는 dataclass다.
생성 자체는 런타임 검증을 수행하지 않는다. Client는 JSON 디코딩 후
read_document_chunk(raw, context_id), read_source_metadata(raw)로 경계 검증을 수행한다.
Backend도 저장·전송 전에 입력과 원본 연결을 검사해야 한다.

다음은 원본 작업에 연결된 가상 웹 조각이다.

~~~json
{
  "id": "chunk-web-001",
  "context_id": "sample-record",
  "chunk_index": 0,
  "text": "가상 문서의 검색 대상 조각입니다.",
  "semantic_data_id": null,
  "source": {
    "kind": "web",
    "application": "Google Chrome",
    "process_name": "chrome.exe",
    "window_title": "작업 당시 창 제목",
    "started_at": "2026-10-14T02:00:00+09:00",
    "last_active_at": "2026-10-14T02:01:00+09:00",
    "captured_at": "2026-10-14T02:00:15+09:00",
    "content_truncated": false,
    "browser": {
      "browser": "chrome",
      "page_title": "본문 확보 당시 페이지 제목",
      "url": "https://example.com/Research?q=sample#Section"
    },
    "document": null
  }
}
~~~

파일 조각에서는 kind를 document로 하고 browser를 생략/null, document를 다음 객체로 제공한다.

~~~json
{"file_path": "C:\\가상 자료\\참고 문서.pdf", "file_type": "pdf"}
~~~

## 조각 필드

| 필드 | 수신 규칙 |
|---|---|
| id | 공백뿐이 아닌 문자열. 안정적인 조각 ID이며 제목/주소에서 추정하지 않음 |
| context_id | 공백뿐이 아닌 문자열. 호출자가 확인한 원본 작업 ID와 정확히 일치 |
| chunk_index | bool을 제외한 0 이상 정수. 해당 본문 스냅샷 내부의 조각 순서 |
| text | 공백뿐이 아닌 문자열, 최대 50,000 Unicode 코드 포인트 |
| source | 필수 SourceMetadata 객체 |
| semantic_data_id | 생략/null은 의미 데이터 미연결. 제공 시 공백뿐이 아닌 문자열 |

50,000자는 기존 저장 본문과 같은 전송 상한이다. 실제 분할 크기나 모델의 토큰 제한이 아니다.
Client는 초과 텍스트를 자르거나 문장을 다시 정규화하지 않는다. 태그·공백·줄바꿈·Unicode를 보존한다.
짧은 텍스트의 색인 여부, 중복 판단, 조각 크기·겹침은 Backend가 결정한다.
추가 필드는 무시하며 필수 필드의 누락·잘못된 타입은 오류다.
semantic_data_id만으로 실제 임베딩 존재나 사용 모델을 확인했다고 취급하지 않는다.

## 출처 필드

| 필드 | 수신 규칙 |
|---|---|
| kind | web 또는 document |
| application, process_name | 공백뿐이 아닌 문자열 |
| window_title | 필수 문자열, 빈 제목 허용 |
| started_at, last_active_at | 시간대 포함 ISO 8601. 마지막 활성은 시작보다 앞설 수 없음 |
| captured_at | 시간대 포함 ISO 8601. 원문 확보 시각 |
| content_truncated | 필수 bool. 원문 스냅샷이 일부만 저장된 경우 true |
| browser | web이면 필수. Chrome/Edge·문자열 페이지 제목·HTTP(S) URL |
| document | document이면 필수. Windows 절대 경로·pdf/docx 유형 |

web은 유효한 browser 하나만, document는 유효한 document 하나만 가진다.
반대 출처는 생략/null이어야 한다. 출처 없음·두 종류 혼합·종류 불일치는 거부한다.
웹 내부/새 탭의 null URL은 검색 조각 출처로 허용하지 않는다.
URL은 [브라우저 계약](browser-api.md), 파일은 [파일 계약](document-content-api.md),
시각은 [시간 계약](activity-timing-api.md)의 수신 검증을 재사용한다.

started_at/last_active_at은 작업 열람 시각이고 captured_at은 본문 확보 시각이다.
비동기 확보가 활성 종료 후 처리될 수 있어 확보 시각을 활성 구간 안으로 강제하지 않는다.
원문에 여러 조각이 생겼다는 이유로 content_truncated를 true로 바꾸지 않는다.
기존 WebContent/DocumentContent의 truncated 값을 모든 관련 조각에서 일관되게 유지한다.

## 원본 연결과 스냅샷

- 모든 조각은 context_id를 통해 실제 원본 작업으로 연결한다.
- 출처는 본문을 확보한 시점의 URL/제목 또는 파일 경로·유형을 보존한다.
  같은 작업에서 탐색이 이어져도 최신 창 제목/URL/경로로 과거 조각을 덮어쓰지 않는다.
- 조각 ID는 서로 다른 원문 스냅샷을 구분해야 한다. chunk_index만으로 전역 ID를 만들지 않는다.
- Client는 원본 작업 ID를 대조하지만 DB에 실제 존재하는지까지 확인하지 않는다.
  Backend는 생성·저장·조회 시 작업과 스냅샷의 연결을 유지한다.
- 원본 삭제·정책 차단 시 조각·의미 데이터가 남아 검색 근거에 쓰이지 않도록 Backend가 처리한다.
- 개인정보 보호 검사는 정규화·분할·임베딩·저장 전에 수행한다.

## 검증 범위

고정 가상 웹/PDF/DOCX 조각을 JSON으로 전달해 ID·출처·시각·원문·일부 저장 여부 복원을 확인한다.
유형 혼합·null URL·상대 경로·잘못된 시간/순서·타입·길이·원본 ID 불일치를 거부한다.
실제 문서 분할, 중복 제거, 임베딩, 색인 저장·삭제 및 저장된 검색 데이터의 역추적은 후속 Backend 검증이다.
