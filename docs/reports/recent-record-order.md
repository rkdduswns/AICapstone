# 최근 기록 제한 조회 정렬 검증

작업일: 2026-11-05 (KST). 브랜치: `fix/recent-record-order`.
기준: PR #16의 `b12a82a69b842060c43b991fe1524e027f899126`.
확인한 main: `7c307987182c629965da63824b60d36e41db4036`.

## 목적과 범위

[최근 기록 API 계약](../dev/recent-records-api.md)은 마지막 활성 순간 내림차순,
같은 순간의 ID 문자열 오름차순으로 정렬한 뒤 요청 개수를 제한하도록 규정한다.
기존 SQLite 조회는 `julianday(ended_at) DESC, id DESC`를 사용했다.
따라서 동률이 20건을 넘으면 다른 기록을 선택하며, Client가 받은 행을 재정렬해도
이미 빠진 기록은 복구할 수 없었다. `julianday`는 서로 다른 마이크로초도 같은 값으로
변환할 수 있어 최신 1건 조회에서도 오래된 기록이 선택될 수 있었다.

이번 작업은 Phase 4의 해당 조회 경계만 보정한다. 기존 DB를 그대로 사용하고
기록 ID·저장 시각·웹/문서 출처 연결 및 API 응답 형식은 변경하지 않는다.

## 구현

- 조회 연결에만 UTC 고정 소수 6자리 정렬 키를 계산하는 SQLite 함수를 등록한다.
- 정렬 키 내림차순, `CAST(id AS TEXT)` 오름차순 다음에 SQL `LIMIT`을 적용한다.
- 시간대가 없는 과거 값은 기존 SQLite 동작처럼 UTC로 해석한다.
- 해석 불가능하거나 UTC 변환 범위를 벗어나는 시각은 기존 날짜 함수처럼 NULL로 정렬한다.
  저장 원문을 수정하지 않으며, 응답에 포함된 잘못된 시각을 Client가 거부하는 계약도 유지한다.
- 스키마 변경이나 의존성 추가는 없다.

## 검증

환경: Windows 10 빌드 19045, Python 3.14.7, SQLite 3.50.4, Qt 6.12.0.
PR의 Python 3.11·3.12 결과와 별개인 추가 소스 검증이다.

격리한 SQLite와 실제 Backend API·Client 파서를 사용하며, 자동 OS 수집·클립보드 읽기는 끈다.
개인 작업 정보나 원본 파일을 검증 자료로 사용하지 않는다.

- 같은 실제 순간을 `Z`, `+09:00`, `-07:00`으로 표현한 25건에서 정확한 20건 선택.
- 실제 최근 기록 API와 Client 파서의 행 집합·순서 일치.
- 실제 최신/과거 순간의 우선순위와 DB 재열기 후 결과 유지.
- 100/200마이크로초 차이를 양쪽 삽입 순서로 검증하고, 시간대 없는 기존 기록도 확인.
- `limit=1`의 Backend와 Client가 같은 최신 기록을 반환하는지 확인.
- 해석 불가능한 과거 시각이 유효한 최신 기록의 제한 조회를 막지 않는지 확인.

검증 결과:

- 원본 SQL을 사용한 동률·시각 정밀도 테스트에서 오류를 재현했다.
- 추가 회귀 테스트 10개를 포함한 관련 테스트 **134 passed**.
  `test_recent_record_order.py`, `test_history_sources.py`, `test_client_integration.py`,
  `test_activity_store.py`, `test_records.py`, `test_live_backend.py`를 실행했다.
- Client 화면 테스트는 `QT_QPA_PLATFORM=offscreen`으로 실행했다. 데스크톱 창 조작은 하지 않는다.
- `python -m ruff check src tests`, `python -m pip check`, `git diff --check` 통과.
- 기존 Starlette/httpx 사용 중단 경고 1건. 전체 테스트 재실행 결과로 확대하지 않는다.

실행 명령:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/backend/test_recent_record_order.py tests/backend/test_history_sources.py tests/backend/test_client_integration.py tests/backend/test_activity_store.py tests/client/test_records.py tests/client/test_live_backend.py
python -m ruff check src tests
python -m pip check
git diff --check
```

## 완료 조건과 남은 범위

동률 20건 초과·마이크로초·시간대·DB 재열기의 조회 계약을 회귀 테스트로 검증하는 것이
이번 작은 단계의 완료 조건이다. Phase 4 전체 상태와 기존 체크 개수는 유지한다.
재방문 집계와 실제 Windows 수동 검증은 여전히 미완료다.

PR #16은 Draft·main 미병합 상태다. 기존 Windows ZIP은 기준 커밋 `b12a82a`의 산출물이며
이번 정렬 수정을 포함하지 않는다. 수정된 버전을 EXE로 배포할 때 새 패키징 검증이 필요하다.
