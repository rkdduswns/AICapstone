# 학습 주제: 비동기 HTTP·timeout·자원 정리

## 0. 출처와 범위

- 원본 경로: `src/client/json_request.py`
- 원본 브랜치: `feat/phase2-client`
- 원본 commit SHA: `1174da04027e1757e66965f44f15e045efd0e668`
- 원본 blob SHA: `140bee361581b466fc0b0d432574f9c30c8bc758`
- 복사 날짜: 2026-10-15 (Asia/Seoul)
- 사본 파일: [src/client/json_request.py](src/client/json_request.py)
- [원본 고정 스냅샷](https://github.com/rkdduswns/AICapstone/blob/1174da04027e1757e66965f44f15e045efd0e668/src/client/json_request.py) · [이 자료의 브랜치 위치](https://github.com/rkdduswns/AICapstone/blob/feat/phase2-client/etc/study/004-async-http/explanation.md)
- 원본과 다른 부분: 단계별 한국어 `#` 주석만 추가했습니다. 실행 코드, 문자열, 기존 docstring을 보존했습니다.

이 자료는 해당 브랜치·커밋의 학습용 스냅샷입니다. `src/`와 `tests/`의 구현 기준으로 참조하거나 자동 동기화하지 않습니다.
원래 import 경로도 보존했으므로 사본은 독립 실행용 프로젝트가 아닙니다. 실제 코드/테스트에서는 이 사본을 import하거나 실행하지 않습니다.

## 1. 코드가 해결하는 문제

UI를 막지 않고 로컬 API를 조회하고, timeout·HTTP 실패·네트워크 실패·응답 유형·종료 취소를 일관되게 처리합니다.

## 2. 먼저 알아야 할 개념

- 비동기는 요청 시작과 결과 도착이 분리된다는 뜻입니다. 이 코드가 직접 작업 스레드를 생성하지는 않습니다.
- `QNetworkReply.finished`는 처리가 끝났다는 신호이며 성공 전용 신호가 아닙니다.
- `QTimer`는 제한 시간 이벤트를 보내고, `timed_out`은 취소 원인을 보존합니다.
- `finally`는 검사 결과와 관계없이 정리할 코드를 둡니다.
- Qt의 `deleteLater()`는 객체 삭제를 예약합니다. Python 변수 참조를 지우는 `del`과 같은 뜻이 아닙니다.

## 3. 전체 실행 순서

1. 초기 상태는 `reply=None`, `timed_out=False`입니다.
2. `get(path)`가 중복 여부를 검사하고 URL·Accept·리다이렉트 정책을 설정합니다.
3. manager.get이 reply를 반환하면 finished를 연결하고 제한 시간 타이머를 시작합니다. 호출자에게 제어가 돌아갑니다.
4. 응답 완료 시 `_finished()`가 reply를 지역 변수로 옮기고 현재 요청 표식과 타이머를 정리합니다.
5. timeout → HTTP 상태 → 전송 오류 → Content-Type 순으로 검사합니다.
6. 성공이면 본문 bytes를 received로, 실패이면 종류와 상태 코드를 failed로 전달합니다.
7. finally에서 이전 reply의 삭제를 예약합니다.
8. 종료 취소는 `close()`가 finished 연결을 끊은 뒤 abort/deleteLater를 수행합니다.

## 4. 함수별 / 코드 블록별 설명

| 함수 | 입력 | 결과/설계 이유 |
|---|---|---|
| `__init__` | 포트, Qt 부모 | 관리자·단발 타이머·요청 상태 준비. |
| `get` | API 경로 | 요청 하나 등록. 결과는 return 대신 신호로 옵니다. |
| `_timeout` | 타이머 이벤트 | timed_out 설정 후 요청 취소. |
| `_finished` | 완료 이벤트 | 실패 종류 또는 본문 bytes 통지 후 자원 정리. |
| `close` | 종료/재확인 | 결과 통지를 끊은 뒤 요청을 취소합니다. |

## 5. 하나의 예시를 끝까지 따라가기

응답이 늦은 `/health` 요청을 가정합니다.

| 시점 | reply | timed_out | 동작 |
|---|---|---|---|
| 요청 전 | None | False | 대기 |
| get 호출 후 | 응답 객체 | False | finished 연결, 타이머 시작 |
| 제한 시간 만료 | 응답 객체 | True | abort 호출 |
| finished 처리 | self.reply는 None | True | timeout 통지, 삭제 예약 |
| 다음 요청 시작 | 새 응답 객체 | False | 이전 timeout 표식을 초기화 |

앱을 닫아서 취소하는 경우에는 실패 안내를 띄울 필요가 없어 finished 연결을 먼저 해제합니다.

## 6. 실패 및 경계 상황

- HTTP 500은 Qt 전송 오류 상태와 함께 관측될 수 있어 HTTP 상태 검사를 앞에 둡니다.
- 서버 연결 자체가 없으면 HTTP 상태 코드도 없을 수 있습니다.
- application/json 헤더를 통과해도 JSON 문법·필드 검증은 남아 있습니다.
- 3xx 이동과 204를 포함해 200이 아닌 상태는 이 코드에서 실패입니다.
- 타이머는 이벤트 루프가 처리하므로 UI 스레드에서 무거운 동기 작업을 하면 제한 시간 처리도 늦어질 수 있습니다.

## 7. 이해 확인과 작은 실습

1. `_timeout()`에서 timed_out을 abort보다 먼저 설정하는 이유를 설명합니다.
2. close()와 timeout 취소의 finished 연결 처리 차이를 찾습니다.
3. Content-Type이 JSON인데 본문이 깨졌다면 어느 계층에서 실패하는지 예상합니다.
4. 읽기 실습: 사본의 3000을 500으로 바꾼다고 가정하고 정상/느린 응답의 결과를 표로 적습니다. 실제 실행 로직은 원본과 별도 요청 없이 수정하지 않습니다.

## 검증 범위

- 원본 blob SHA를 확인하고 사본의 Python 문법을 파싱했습니다.
- 원본/사본의 AST와 주석을 제외한 실행 토큰을 비교했습니다. 주석 이외의 코드 변경은 없습니다.
- 학습 자료 작성은 기능 구현/Phase 완료 처리와 별개입니다. 사본을 실행하거나 새 Windows 동작 검증을 수행한 것은 아닙니다.
- 자세한 줄별 설명은 사본 코드의 번호 주석을 따라 읽습니다.

## 참고 문서

- [Qt QNetworkReply](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkReply.html)
