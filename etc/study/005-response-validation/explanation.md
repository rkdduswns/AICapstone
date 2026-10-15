# 학습 주제: 응답 검증과 오류 분류

## 0. 출처와 범위

- 원본 경로: `src/client/backend_client.py`
- 원본 브랜치: `feat/phase2-client`
- 원본 commit SHA: `1174da04027e1757e66965f44f15e045efd0e668`
- 원본 blob SHA: `1bbb78718cb71824f554b81b05402893b8d752a3`
- 복사 날짜: 2026-10-15 (Asia/Seoul)
- 사본 파일: [src/client/backend_client.py](src/client/backend_client.py)
- [원본 고정 스냅샷](https://github.com/rkdduswns/AICapstone/blob/1174da04027e1757e66965f44f15e045efd0e668/src/client/backend_client.py) · [이 자료의 브랜치 위치](https://github.com/rkdduswns/AICapstone/blob/feat/phase2-client/etc/study/005-response-validation/explanation.md)
- 원본과 다른 부분: 단계별 한국어 `#` 주석만 추가했습니다. 실행 코드, 문자열, 기존 docstring을 보존했습니다.

이 자료는 해당 브랜치·커밋의 학습용 스냅샷입니다. `src/`와 `tests/`의 구현 기준으로 참조하거나 자동 동기화하지 않습니다.
원래 import 경로도 보존했으므로 사본은 독립 실행용 프로젝트가 아닙니다. 실제 코드/테스트에서는 이 사본을 import하거나 실행하지 않습니다.

## 1. 코드가 해결하는 문제

HTTP 전송이 성공해도 응답이 다른 서비스의 것이거나 계약에 맞지 않으면 연결 성공으로 표시하지 않습니다. 검증 결과를 화면 문구와 bool 상태로 전달합니다.

## 2. 먼저 알아야 할 개념

- JSON 문법이 올바른 것과 서비스 응답 구조가 올바른 것은 다릅니다.
- `is True`는 True 객체만, `type(value) is int`는 bool을 제외한 정확한 int 타입을 인정합니다.
- `dict.get()`은 키가 없어도 None을 돌려주므로 키 존재 검사가 따로 필요할 수 있습니다.
- `or` 단락 평가로 앞 조건이 실패를 확인하면 뒤의 위험한 접근을 생략합니다.
- 파싱/검증을 순수 함수로 두어 네트워크/GUI 없이도 입력과 출력을 검사할 수 있습니다.

## 3. 전체 실행 순서

1. `check()`가 기반 클래스의 get('/health')를 호출합니다.
2. 전송 객체가 받은 bytes를 received 신호로 보냅니다.
3. `_received()`가 `read_version()`으로 본문을 검사합니다.
4. 바깥 객체·ok/error → data 객체 → 서비스/상태/통신 버전 → 앱 버전 순서로 검사합니다.
5. 검증 실패는 `_failed('content_type', 0)`으로 전달하고 성공 코드를 실행하지 않습니다.
6. 성공이면 result 문구, connection_changed(True)를 알립니다.
7. 전송 실패도 `_failed()`에 모여 고정 문구와 False를 알립니다.

## 4. 함수별 / 코드 블록별 설명

| 함수/신호 | 입력/출력 | 책임 |
|---|---|---|
| `read_version` | bytes → str 또는 예외 | 서비스 응답 검증. UI를 직접 갱신하지 않습니다. |
| `BackendClient.__init__` | 포트, 부모 | 기반 클래스 신호와 처리기를 연결합니다. |
| `check` | 없음 | health 요청을 시작합니다. |
| `_received` | bytes | 검증 후 성공 또는 내용 오류 처리로 분기합니다. |
| `_failed` | reason, status | 원인별 고정 문구와 실패 상태로 변환합니다. |
| `result` / `connection_changed` | str / bool | 사용자 안내와 프로그램의 상태 판단을 분리합니다. |

## 5. 하나의 예시를 끝까지 따라가기

응답의 `data.api_version`이 숫자 `1`이면 통신 버전 검사에 맞습니다.
JSON의 `true`이면 Python bool True가 되어, 값 비교에서 `True == 1`이더라도 정확한 타입 검사에서 거부합니다.
문자열 `"1"`도 거부합니다.

`error:null`인 응답은 허용할 수 있지만 error 키를 아예 지우면 `Missing error field`입니다.
`.get('error') is None`만으로는 이 두 경우를 구분할 수 없어 별도 존재 검사를 둔 이유입니다.

## 6. 실패 및 경계 상황

- b'[]'와 b'null'은 JSON 파싱에 성공하지만 정상 응답은 아닙니다.
- 앱 version이 공백뿐이면 거부합니다. 유효한 version의 앞뒤 공백을 제거해 반환하지는 않습니다.
- content_type이라는 내부 원인에는 매체 유형 오류와 내용 규격 오류가 함께 포함됩니다.
- `_failed`의 사전은 알려진 네 가지 원인을 전제합니다. 임의 reason을 넘기면 KeyError입니다.
- HTTP 상태 코드 인자는 현재 안내 문구에 사용하지 않지만 기반 failed 신호의 형태를 유지합니다.

## 7. 이해 확인과 작은 실습

1. error 키 누락, ok=1, data=[], 다른 service인 응답을 각각 어느 검사에서 거부할지 예상합니다.
2. read_version이 UI를 import하지 않아도 되는 이유를 적습니다.
3. `_received`의 except 뒤 return을 없앤다고 가정하고 어떤 잘못된 흐름이 가능한지 설명합니다.
4. 이해 기준: 전송·본문 검증·사용자 표시가 각각 어떤 함수/클래스의 책임인지 말할 수 있습니다.

## 검증 범위

- 원본 blob SHA를 확인하고 사본의 Python 문법을 파싱했습니다.
- 원본/사본의 AST와 주석을 제외한 실행 토큰을 비교했습니다. 주석 이외의 코드 변경은 없습니다.
- 학습 자료 작성은 기능 구현/Phase 완료 처리와 별개입니다. 사본을 실행하거나 새 Windows 동작 검증을 수행한 것은 아닙니다.
- 자세한 줄별 설명은 사본 코드의 번호 주석을 따라 읽습니다.
