# 학습 주제: pytest와 비동기 UI 테스트

Phase 004 학습 자료 · `chore/study-workspace`

## 0. 출처와 범위

- 원본 경로: `tests/client/test_connection.py`
- 원본 브랜치: `feat/phase4-client`
- 원본 commit SHA: `a3a1aec2ecce25bad7c1de7547279b766929d8a1`
- 원본 blob SHA: `ed3d77be26f6522155de2991f5858ae674733f10`
- 복사 날짜: 2026-10-15 (Asia/Seoul)
- 사본 파일: [tests/client/test_connection.py](tests/client/test_connection.py)
- 자료 정리일: 2026-10-16 (Asia/Seoul)
- 보관 브랜치: `chore/study-workspace`
- [전체 학습 순서](../00-learning-path.md) · [Study 안내](../README.md)
- [원본 고정 스냅샷](https://github.com/rkdduswns/AICapstone/blob/a3a1aec2ecce25bad7c1de7547279b766929d8a1/tests/client/test_connection.py)
- 원본과 다른 부분: 단계별 한국어 `#` 주석만 추가했습니다. 실행 코드, 문자열, 기존 docstring을 보존했습니다.

이 자료는 해당 브랜치·커밋의 학습용 스냅샷입니다. `src/`와 `tests/`의 구현 기준으로 참조하거나 자동 동기화하지 않습니다.
원래 import 경로도 보존했으므로 사본은 독립 실행용 프로젝트가 아닙니다. 실제 코드/테스트에서는 이 사본을 import하거나 실행하지 않습니다.

## 1. 코드가 해결하는 문제

파서·HTTP 응답·UI 상태·timeout·요청 중 종료·실제 Backend 복구를 재현해 정상 동작뿐 아니라 실패와 정리 경로도 검증합니다.

## 2. 먼저 알아야 할 개념

- fixture는 테스트에 필요한 준비/정리를 제공합니다. 테스트 함수 인자 이름으로 주입됩니다.
- module 범위의 QApplication과 function 범위의 가상 서버는 수명이 다릅니다.
- parametrize는 한 검증 흐름을 여러 입력으로 각각 실행합니다.
- yield fixture의 앞부분은 준비, 뒷부분은 정리 단계입니다.
- wait_for는 조건을 기다리며 테스트에서 Qt 이벤트를 처리합니다. 제품용 대기 루프가 아닙니다.

## 3. 전체 실행 순서

1. 테스트 수집 전에 필요한 Qt 환경을 설정하고 정상 예시 GOOD을 준비합니다.
2. pytest가 필요한 fixture를 준비합니다. 가상 서버는 별도 스레드에서 동작합니다.
3. 테스트마다 응답 본문/상태/지연을 settings로 설정합니다.
4. 파서 테스트는 직접 read_version을 호출하고, UI 테스트는 실제 Qt HTTP 요청을 보냅니다.
5. wait_for가 Qt 이벤트를 처리하며 완료 조건을 기다립니다.
6. 상태와 자원 정리를 assert로 확인합니다.
7. finally와 fixture의 yield 뒤 코드에서 창·서버·스레드·프로세스를 회수합니다.

## 4. 함수별 / 코드 블록별 설명

| 구성 | 검증/역할 | 한계 |
|---|---|---|
| `app` | QApplication 공유 | 실제 Windows 화면 사용성 전체를 증명하지 않습니다. |
| `wait_for` | 조건 기반 비동기 완료 대기 | 제품 UI에 복제할 동기 루프가 아닙니다. |
| `fake_server` | 응답/지연을 제어하는 실제 로컬 HTTP 서버 | OS 감지나 실제 Backend 로직을 검증하지 않습니다. |
| 파서 테스트 두 종류 | 잘못된 버전/JSON/구조 거부 | GUI와 네트워크 없이 검증합니다. |
| `test_window_response` | 표시·버튼·중복 요청 | 가상 서버와 실제 전송 경로를 연결합니다. |
| timeout/종료 테스트 | 타이머 이벤트·취소·자원 상태 | 장시간 성능 시험은 아닙니다. |
| 실제 Backend 복구 테스트 | 미기동/연결/종료/재기동 | 이 원본 버전은 Phase 1 서버 기능을 기준으로 합니다. |

## 5. 하나의 예시를 끝까지 따라가기

timeout 테스트에서는 서버 지연을 0.4초, 클라이언트 제한 시간을 50ms로 둡니다.
10ms QTimer 콜백의 ticks가 남는지 보고, 버튼 복구와 timeout 안내를 확인합니다.
다음 요청을 시작하자마자 창을 닫아 reply=None과 타이머 정지를 확인합니다.

실제 서버 테스트에서는 health가 정상이어도 현재 창/최근 기록은 `기능 준비 중`이 기대값입니다.
이 사본의 원본 시점에는 Backend가 Phase 1이므로, 빈 화면이 올바른 호환 동작입니다.

## 6. 실패 및 경계 상황

- GOOD의 중첩 사전을 그대로 수정하면 테스트 간 상태가 섞일 수 있어 별도 객체를 만듭니다.
- 서버가 늦게 쓰는 동안 클라이언트가 취소하면 BrokenPipe/ConnectionReset이 예상될 수 있습니다.
- 포트 0으로 실제 bind하는 가상 서버와, 빈 포트를 골랐다가 닫고 실제 프로세스에 넘기는 방식은 경합 가능성이 다릅니다.
- subprocess 실행 후 생존 확인과 HTTP 준비 완료 확인을 모두 수행합니다.
- 이 파일에는 subprocess/HTTP/UI 코드가 보존되어 있습니다. 사본은 실행하지 않고 원본 테스트로 검증합니다.

## 7. 이해 확인과 작은 실습

1. module fixture와 function fixture를 바꾸면 어떤 객체가 공유될지 적습니다.
2. 고정 sleep만 쓰는 것과 processEvents/조건 대기의 차이를 설명합니다.
3. HTTP 200이지만 다른 service인 사례를 실패시키는 검사가 어디인지 찾습니다.
4. 이해 기준: 단위 테스트·가상 HTTP UI 검증·실제 프로세스 통합 검증의 범위를 구분할 수 있습니다.

## 검증 범위

- 원본 blob SHA를 확인하고 사본의 Python 문법을 파싱했습니다.
- 원본/사본의 AST와 주석을 제외한 실행 토큰을 비교했습니다. 주석 이외의 코드 변경은 없습니다.
- 학습 자료 작성은 기능 구현/Phase 완료 처리와 별개입니다. 사본을 실행하거나 새 Windows 동작 검증을 수행한 것은 아닙니다.
- 자세한 줄별 설명은 사본 코드의 번호 주석을 따라 읽습니다.
