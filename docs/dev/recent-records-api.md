# Phase 4 최근 기록 API 계약

상태: Client/Shared 구현 및 가상 HTTP 검증 완료. Backend 저장소와 endpoint는 미구현이다.
이 문서를 Backend 구현 기준으로 사용하며, Phase 4 전체는 실제 저장·재시작 복원 검증 전까지 IN_PROGRESS다.

## 요청과 책임

- `GET http://127.0.0.1:<port>/records/recent?limit=20`, 본문 없음, `Accept: application/json`.
- Client는 최근 20건만 요청한다. Backend는 `limit` 생략 시 20, 정수 1–20만 허용하고 그 외에는 HTTP 422와 기존 오류 envelope를 반환한다.
- Backend는 저장소 전체에서 마지막 활성 시각 내림차순, 같은 순간은 ID 오름차순으로 정렬한 뒤 개수를 제한한다.
- Client도 응답을 같은 순서로 정렬한다. Client 정렬은 Backend의 최신 20건 선택을 대신하지 않는다.
- 응답은 HTTP 200, `Content-Type: application/json`. 저장 기록이 없으면 빈 배열이다.
- `/health`와 같은 서비스 및 `api_version: 1`을 유지한다. 새 경로 추가이므로 기존 API를 변경하지 않는다.
- Shared 정의: `src/shared/records.py`의 `ContextRecord`, `RecentRecords`, `RecentRecordsResponse`.
- Client는 응답을 검증하고 표시한다. 저장·갱신·시간/재방문 계산은 Backend 책임이다.

## 정상 응답

아래 값은 모두 가상 데이터다.

```json
{
  "ok": true,
  "data": {
    "service": "contexttrace-backend",
    "api_version": 1,
    "records": [
      {
        "id": "sample-record-001",
        "application": "Visual Studio Code",
        "process_name": "Code.exe",
        "window_title": "가상 작업.py",
        "started_at": "2026-10-01T10:00:00+09:00",
        "last_active_at": "2026-10-01T10:20:00+09:00",
        "active_duration_ms": 65000,
        "foreground_count": 3
      }
    ]
  },
  "error": null
}
```

| 필드 | 규칙 |
|---|---|
| `ok` | boolean true. 정수 1 거부 |
| `error` | 필수, 정상 응답에서 null |
| `data.service` | 정확히 `contexttrace-backend` |
| `data.api_version` | 정수 1. boolean/문자열 거부 |
| `data.records` | 필수 배열, 요청한 개수 이하. null 거부 |
| `id` | 공백만 있지 않은 문자열. 저장 후 갱신·재조회·재시작에도 같은 기록의 ID 유지. 한 응답 안에서 중복 불가 |
| `application`, `process_name` | 공백만 있지 않은 문자열 |
| `window_title` | 필수 문자열. 빈 문자열은 `(제목 없음)`으로 표시 |
| `started_at` | 기록 최초 시작 시각. 시간대 포함 ISO 8601 문자열 |
| `last_active_at` | 마지막으로 활성 상태임을 확인한 시각. 실제 순간 기준으로 시작 시각 이상 |
| `active_duration_ms` | 정수 0 이상, 비활성 구간을 제외한 누적 활성 밀리초. boolean/실수/문자열 거부 |
| `foreground_count` | 정수 1 이상, 최초 활성화 1회를 포함한 활성화 횟수. 재방문 표시는 이 값에서 1을 뺀 값 |

시각은 `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` 또는 `±HH:MM` 오프셋을 갖는다.
유효한 달력 시각, 소수 1–6자리, 오프셋 시 0–23/분 0–59를 허용하며 PC 현지 시각으로 표시 가능해야 한다.
[Phase 3 시간 계약](activity-timing-api.md)과 같은 검증/표시 함수를 사용한다.
서로 다른 오프셋은 문자열이 아닌 실제 순간으로 비교한다. ID 비교는 문자열 오름차순이다.
활성 중인 기록은 아직 종료 시각이 없으므로 별도 종료 필드를 요구하지 않는다.
추가 필드는 무시하며 필수 필드 누락이나 한 행의 오류도 응답 전체 실패로 처리한다.

## 화면 및 실패 처리

- 호환되는 `/health` 확인 후 `최근 기록` 탭 최초 진입 시 조회한다. 탭을 먼저 열었다면 연결 성공 시 조회한다.
- 정상 조회 이후에는 버튼으로 새로고침한다. 주기적인 현재 창 조회와 기록 조회는 독립적이다.
- 조회 중 버튼을 비활성화하고 이전 목록/상세를 비운다. 응답은 누적하지 않고 교체하며, 같은 ID가 있으면 선택을 복원한다.
- 목록에는 프로그램, 제목, PC 현지 마지막 활성 시각, 누적 활성 시간을 표시한다.
  선택 상세에는 전체 제목, 프로세스, 시작/마지막 활성 시각과 UTC 오프셋, 재방문 횟수를 표시한다.
- 활성 시간은 서버 값을 `HH:MM:SS`로 표시한다. 초 미만은 버리고 24시간 이후에도 시간을 누적한다.
- 마지막 정상 조회 시각은 Client가 유효한 응답을 받은 시각이다. 저장 시각이나 작업 시작 시각이 아니다.
- 빈 배열은 `저장된 작업 기록이 없습니다.`로 표시한다.
- HTTP 404는 `기능 준비 중`, 다른 HTTP 오류·연결 실패·3초 timeout·잘못된 응답은 각각 오류로 표시한다.
- 오류 시 이전 기록을 남기지 않으며 새로고침으로 복구한다. 최초 조회가 실패한 경우 탭 재진입도 재시도한다.
- 연결 재확인/창 종료 시 진행 중 요청을 취소하여 늦은 응답이 이전 데이터를 다시 표시하지 못하게 한다.
- 공통 HTTP 계층의 loopback 제한, 프록시 비활성화, 리다이렉트 거부를 유지한다.
- 제목은 일반 텍스트이며 긴 제목은 상세란에서 줄바꿈/스크롤로 확인한다. Client는 기록이나 오류 본문을 파일/로그로 저장하지 않는다.

## Backend 구현과 실제 통합의 완료 조건

1. Phase 2 감지 및 Phase 3 추적 결과로 기록을 생성·갱신한다. 동일 기록 판단과 재방문 병합 정책은 Backend 구현에서 문서화한다.
2. 저장 ID, 누적 활성 시간, 활성화 횟수, 마지막 활성 시각을 지속 저장한다. DB 종류와 저장 방식은 이 조회 계약이 강제하지 않는다.
3. 동일 기록 갱신 시 ID가 유지되고, 재방문이 없는 최초 기록의 `foreground_count`는 1이어야 한다.
4. 최신순으로 제한된 조회 endpoint를 구현하고 잘못된 `limit` 및 저장 필드를 검증한다.
5. 새 기록 생성, 기존 기록 갱신, 20건 초과 중 최신 기록 선택, 재시작 후 동일 ID/값 조회를 실제 저장소와 검증한다.
6. 기존 API의 [접근 제어 검토 사항](health-api.md)과 저장 전 개인정보 보호 원칙을 따른다.

현재 가상 HTTP 테스트와 미리보기는 실제 DB 저장·재방문 계산·Backend 재시작 복원의 증거가 아니다.
