# Phase 1 상태 통신 계약

상태: 1A Backend 및 공통 응답 구조 구현·Linux 검증 완료. PySide6 Client 구현 및 Linux 자동 검증 완료. Windows 검증 결과는 별도 보고서 참조.

## 접속 및 요청

- 기본 주소: `http://127.0.0.1:8765`
- 서버는 `127.0.0.1`에만 bind한다. 현재 API는 상태 정보만 제공한다.
- `GET /health`, 요청 본문 없음, `Accept: application/json`
- 응답 `Content-Type: application/json`
- 연결 성공은 HTTP 200과 아래 필드 검증에 모두 성공한 경우에만 표시한다.
- `service`와 `api_version`을 확인해 다른 프로그램의 응답을 정상으로 오인하지 않는다.

```json
{"ok":true,"data":{"service":"contexttrace-backend","status":"running","version":"0.1.0","api_version":1},"error":null}
```

| 필드 | 계약 |
|---|---|
| ok | boolean. 정상 응답은 true |
| data | 정상일 때 상태 객체, 실패일 때 null |
| data.service | 정확히 `contexttrace-backend` |
| data.status | Phase 1에서는 정확히 `running` |
| data.version | 애플리케이션 버전 문자열, 연결 호환 여부와 분리 |
| data.api_version | 정수 1. bool 또는 문자열로 대체하지 않음 |
| error | 정상일 때 null, 실패일 때 code/message 객체 |

실패 응답 예시(HTTP 500):

```json
{"ok":false,"data":null,"error":{"code":"INTERNAL_ERROR","message":"상태 확인 중 오류가 발생했습니다."}}
```

미지원 경로는 HTTP 404 / `NOT_FOUND`, 미지원 메서드는 HTTP 405 / `METHOD_NOT_ALLOWED`를 사용한다.
입력 검증 오류는 HTTP 422 / `INVALID_REQUEST`로 변환한다.
FastAPI 기본 오류 응답도 이 계약으로 변환한다. 내부 stack trace나 로컬 경로는 응답에 넣지 않는다.

## Client 상태 및 실패 처리

| 상황 | 화면 상태 / 처리 |
|---|---|
| 실행 직후 | 미확인. Backend가 없어도 창은 열림 |
| 확인 버튼 클릭 | 연결 중. 중복 요청 버튼 비활성화 |
| 정상 응답 | 연결됨 및 Backend 버전 표시 |
| 접속 거절 | 연결 안 됨. Backend 실행 후 다시 확인 안내 |
| 요청 시작 후 3초 초과 | 시간 초과. 전체 요청 타이머로 요청 취소 |
| HTTP 오류 | 상태 확인 실패. 일반 오류 메시지 표시 |
| 잘못된 JSON/필드/서비스/API 버전 | 호환되지 않는 응답. 연결됨으로 표시하지 않음 |
| 재확인 성공 | 이전 오류를 지우고 연결됨으로 복구 |
| 요청 중 창 닫기 | 요청·타이머 정리 후 정상 종료 |

자동 재시도 및 자동 polling은 Phase 1에서 하지 않는다. 상태 표시는 마지막 확인 결과이며
마지막 확인 시각을 함께 표시한다. Backend가 종료되면 다음 확인 요청에서 실패로 바뀐다.
Qt 이벤트 루프를 막는 동기 네트워크 호출은 사용하지 않는다.

## 설정 및 로그

Backend는 기본값으로 동작하며, Client 구현 시 양쪽에 동일한 `--port` 옵션(1–65535, 기본 8765)을 제공한다.
Client는 loopback host를 고정한다. 포트 충돌·잘못된 옵션은 명확한 오류와 비정상 종료 코드로 알린다.
서버는 Python logging으로 시작/종료/오류를 콘솔에 기록한다. 실행 로그 파일은 아직 만들지 않는다.
`.env` 로더와 API 키는 이번 단계에서 필요 없다.

## 검증 시나리오

1. Backend 단독 기동 → GET /health의 상태 코드·JSON 확인.
2. Backend 미기동 → Client 창 실행 → 확인 클릭 → 오류 표시 및 UI 생존.
3. 두 프로세스 기동 → Client 확인 → 연결됨 표시.
4. Backend 종료 → 재확인 실패 → Backend 재기동 → 재확인 성공.
5. 응답 지연·잘못된 JSON·잘못된 서비스·API 버전·HTTP 500을 가상 서버로 재현.
6. 요청 중 창 종료 및 연속 클릭 시 중복 요청/종료 오류 없음.
7. Windows 10/11에서 위 독립 실행 및 왕복을 확인하고 실제 확인한 OS 버전을 기록.

이 계약은 상태 API에만 적용한다. 작업 데이터 API와 브라우저 연동의 접근 제어는 해당 Phase에서 설계한다.

## 구현 참고

- [FastAPI 예외 처리](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- 공통 구조는 Python dataclass로 정의하여 UI 및 서버 프레임워크 의존성을 피한다.
- 앱 버전은 설치된 `contexttrace` 패키지 메타데이터에서 읽는다.
- 상태 API만 노출하며 자동 문서 경로와 후행 슬래시 리다이렉트는 비활성화했다.

Client는 [Qt QNetworkAccessManager](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkAccessManager.html)를 사용한다. 전체 요청 3초 타이머, 수동 재확인, 요청 취소와 종료 정리를 구현했다.
