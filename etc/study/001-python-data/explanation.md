# 학습 주제: Python 데이터 구조

## 0. 출처와 범위

- 원본 경로: `src/shared/activity.py`
- 원본 브랜치: `feat/phase3-client`
- 원본 commit SHA: `e698b9af7cd37f963fd94092b170e85e8d80e1d3`
- 원본 blob SHA: `717d51723b17e5c0d9051e4a9963e71712355fe7`
- 복사 날짜: 2026-10-15 (Asia/Seoul)
- 사본 파일: [src/shared/activity.py](src/shared/activity.py)
- [원본 고정 스냅샷](https://github.com/rkdduswns/AICapstone/blob/e698b9af7cd37f963fd94092b170e85e8d80e1d3/src/shared/activity.py) · [이 자료의 브랜치 위치](https://github.com/rkdduswns/AICapstone/blob/feat/phase3-client/etc/study/001-python-data/explanation.md)
- 원본과 다른 부분: 단계별 한국어 `#` 주석만 추가했습니다. 실행 코드, 문자열, 기존 docstring을 보존했습니다.

이 자료는 해당 브랜치·커밋의 학습용 스냅샷입니다. `src/`와 `tests/`의 구현 기준으로 참조하거나 자동 동기화하지 않습니다.
원래 import 경로도 보존했으므로 사본은 독립 실행용 프로젝트가 아닙니다. 실제 코드/테스트에서는 이 사본을 import하거나 실행하지 않습니다.

## 1. 코드가 해결하는 문제

현재 창·수집 상태·시간을 Client와 Backend가 같은 의미로 주고받도록 데이터 계약을 정의합니다. 수집이나 화면 갱신은 이 파일의 책임이 아닙니다.

## 2. 먼저 알아야 할 개념

- `self`는 인스턴스, `:`는 타입 힌트, `=`는 기본값을 나타냅니다.
- `dataclass`는 필드 선언에 맞춰 생성자·비교·표시 메서드 등을 생성합니다. C# 데이터 전달 객체와 목적을 비교해 봅니다.
- `Literal[...]`과 타입 힌트는 기본적으로 런타임 검증기가 아닙니다.
- `A | None`은 값이 없을 수 있다는 계약이고 `= None`은 인자 생략 시 기본값입니다.
- `frozen=True`는 일반적인 필드 재대입을 막습니다. 내부 객체까지 모두 재귀적으로 불변이 되는 것은 아닙니다.

## 3. 전체 실행 순서

1. import 시 서비스 상수와 데이터 클래스가 정의됩니다. HTTP 요청이나 창 감지는 시작하지 않습니다.
2. 생산자가 감지 결과로 `ActiveWindow`를 만듭니다.
3. 시간 정보가 있으면 별도의 `ActivityTiming`을 만듭니다.
4. 수집 상태와 창·시간을 `CurrentActivity`로 묶습니다.
5. `CurrentActivityResponse`에 담아 성공 응답 모델로 사용합니다.
6. 직렬화와 외부 JSON 검증은 해당 통신 계층이 수행합니다.

## 4. 함수별 / 코드 블록별 설명

| 구성 | 입력/담는 값 | 역할과 선택 이유 |
|---|---|---|
| `CollectionStatus` | 네 종류의 문자열 | 감지 성공·창 없음·미지원·오류를 구분합니다. |
| `ActiveWindow` | 앱명, 프로세스명/ID, 제목 | 프로그램의 정체와 화면 제목을 구분합니다. |
| `ActivityTiming` | 시작 시각, 활성 밀리초 | 시점과 지속 시간을 다른 값으로 표현합니다. |
| `CurrentActivity` | 상태, 선택적 창/시간 | 한 번 받은 현재 작업의 스냅샷입니다. |
| `CurrentActivityResponse` | data, ok, error | API 성공과 실제 수집 결과를 분리합니다. |

## 5. 하나의 예시를 끝까지 따라가기

Chrome에서 예시 문서를 보고 65초간 활성 상태였다고 가정합니다.

```python
# 읽기용 예시입니다. 원본/테스트를 수정하거나 이 사본을 실행하지 않습니다.
window = ActiveWindow('Chrome', 'chrome.exe', 1234, '예시 문서')
timing = ActivityTiming('2026-10-15T09:00:00+09:00', 65_000)
current = CurrentActivity('collecting', window, timing=timing)
response = CurrentActivityResponse(current)
```

`response.ok`는 `True`, `response.data.window.window_title`은 `예시 문서`, 누적 시간은 65,000ms입니다.
반면 `CurrentActivity('no_active_window', None)`도 정상 API 응답에 담을 수 있습니다. API 성공이 곧 창 감지 성공은 아닙니다.

## 6. 실패 및 경계 상황

- `timing=None`은 시간 정보 미제공이며 0ms와 다릅니다.
- `window`는 None을 허용하지만 기본값이 없어 생성자에서 인자를 생략할 수 없습니다.
- 잘못된 상태 문자열이나 상태/창의 모순은 dataclass만으로 거부되지 않습니다. 생산자·파서 검증이 필요합니다.
- 시작 시각 문자열을 선언했다고 시간대 형식까지 자동 검사되지는 않습니다.

## 7. 이해 확인과 작은 실습

1. `window: ActiveWindow | None`과 `timing: ActivityTiming | None = None`의 차이를 말해 봅니다.
2. 정상 API 응답인데도 창이 없는 예시를 직접 적어 봅니다.
3. `active_duration_ms=0`과 `timing=None`을 화면에서 어떻게 달리 표시할지 예상합니다.
4. 이해 기준: 타입 정의, 값 검증, 시간 계산, 화면 표시가 각각 누구의 책임인지 설명할 수 있습니다.

## 검증 범위

- 원본 blob SHA를 확인하고 사본의 Python 문법을 파싱했습니다.
- 원본/사본의 AST와 주석을 제외한 실행 토큰을 비교했습니다. 주석 이외의 코드 변경은 없습니다.
- 학습 자료 작성은 기능 구현/Phase 완료 처리와 별개입니다. 사본을 실행하거나 새 Windows 동작 검증을 수행한 것은 아닙니다.
- 자세한 줄별 설명은 사본 코드의 번호 주석을 따라 읽습니다.

## 참고 문서

- [Python dataclasses](https://docs.python.org/3.11/library/dataclasses.html)
- [Python typing](https://docs.python.org/3.11/library/typing.html)
