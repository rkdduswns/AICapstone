# 작업 이력과 웹·문서 출처 연결

적용 브랜치: `feat/client-backend-integration` (2026-10-22). main 반영 전 검토 대상이다.
[실행 환경](development-setup.md), [검증 결과](../reports/client-backend-integration.md)를 함께 따른다.

## 문서 연결

1. Backend와 Client를 실행하고 Client의 연결 확인을 누른다.
2. `최근 기록`에서 연결할 작업을 선택하고 `선택한 작업에 문서 연결`을 누른다.
3. 문서 가져오기 탭의 작업 번호·제목을 확인하고 PDF 또는 DOCX를 선택한다.
4. 업로드가 끝나면 최근 기록으로 돌아가 선택 작업의 `문서 본문`을 연다.

파일 선택으로 받은 Windows 절대 경로와 업로드한 바이트를 해당 작업에 명시적으로 연결한다.
이 경로를 Backend가 열지는 않는다. 원래 작업의 시작/마지막 활성 시각은 바꾸지 않으며,
문서를 가져온 시각은 별도 `captured_at`이다. 자동으로 열린 파일을 감지하는 기능은 남아 있다.
연결 대상을 해제하면 기존처럼 문서만 가져온다. 이전 업로드를 제목/시각으로 추측해 연결하지 않는다.

## Chrome·Edge 페이지 연결

확장은 버튼으로 실행하는 수동 연결 방식이다. 모든 탭을 상시 수집하거나 탭 전환을 자동 기록하지 않는다.
Windows에서 실제 활성 Chrome/Edge 작업을 감지할 수 있어야 한다.

Backend를 실행하는 PowerShell에서 토큰을 만든 뒤 서버를 시작한다. 토큰 값은 저장소에 기록하지 않는다.

```powershell
$env:CONTEXTTRACE_BROWSER_TOKEN = [guid]::NewGuid().ToString("N")
# 이 터미널에서 생성한 값을 확장 설정에 복사한다.
$env:CONTEXTTRACE_BROWSER_TOKEN
.\.venv\Scripts\python.exe -m backend
```

1. Chrome은 `chrome://extensions`, Edge는 `edge://extensions`를 연다.
2. 개발자 모드를 켜고 `압축해제된 확장 프로그램 로드`에서 저장소의 `src/browser/extension` 폴더를 선택한다.
3. 일반 HTTP(S) 페이지로 돌아가 확장 아이콘을 누른다.
4. Backend 포트(기본 8765)와 위 토큰을 입력하고 `연결 설정 저장`을 누른다.
5. `이 페이지를 작업에 연결`을 누르고 완료된 작업 번호를 확인한다.
6. Client의 최근 기록을 새로고침하고 해당 작업의 출처와 `웹 본문`을 확인한다.

토큰은 확장의 로컬 저장소에 보관한다. Backend를 새 토큰으로 실행했다면 확장 설정도 갱신한다.
내부 페이지·새 탭·로컬 파일에서는 연결하지 않는다. Backend 중지·일시정지·프로그램 차단·민감 패턴·토큰 오류는 실패로 표시한다.
본문을 읽는 사이 페이지/작업이 바뀌면 재시도해야 한다. 출처 저장 이후 본문 저장만 실패한 경우에는 부분 성공임을 표시한다.
URL은 기존 Backend 보호 규칙대로 query·fragment를 제거한 값을 저장한다.

권한은 `activeTab`, `scripting`, `storage`, `http://127.0.0.1/*`이다.
페이지 본문은 `main` 또는 `article`의 표시 텍스트를 우선하고 없으면 `body`를 사용하며 최대 100,000자까지 전송한다.
본문 정제와 SPA 자동 갱신, URL 차단 규칙 적용은 후속 범위다.
[activeTab 권한](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)과
[확장의 교차 출처 요청](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests)을 기준으로 구성했다.

## 저장·조회 계약

| 경로 | 연결 계약 |
|---|---|
| `GET /activity/current` | 수집 중 `data.record_id`에 실제 SQLite 작업 ID를 문자열로 반환한다. 같은 세션은 ID를 유지한다. |
| `POST /browser/source` | Bearer 토큰과 선택적 `record_id`를 받는다. ID가 있으면 현재 브라우저 프로세스·작업을 대조한다. 응답 `activity_record_id`가 최종 연결 ID다. |
| `POST /browser/content` | 출처 ID를 받는다. 연결된 출처는 같은 작업이 계속 활성 상태이고 최신 출처일 때만 저장한다. 재전송은 같은 본문 행을 갱신한다. |
| `POST /documents` | multipart `file`, 선택적 `record_id`, `file_path`. 연결 요청은 desktop 헤더·Origin 부재·존재하는 작업·Windows 절대 경로·파일 이름 일치를 검사한다. |
| `GET /records/recent` | 실제 FK로 연결된 최신 `browser`·`document`만 투영한다. |
| `GET /records/web-content?record_id=…` | 작업에 연결된 출처와 저장 웹 본문을 반환한다. |
| `GET /records/document-content?record_id=…` | 작업에 연결된 파일 경로와 저장 문서 본문을 반환한다. |

문서 연결 헤더는 `X-ContextTrace-Client: desktop`이다. 본문 조회는 기존 Shared 응답 계약을 사용한다.
작업이 없으면 404, 작업은 있지만 저장 본문이 없으면 `content: null`이다.
본문은 최대 50,000자를 응답하고 초과하면 `truncated: true`다. 조회 중 외부 URL/원본 파일에 접근하지 않는다.

SQLite의 새 `record_browser_sources`·`record_document_sources` 테이블은 작업과 출처에 외래 키를 둔다.
출처 저장과 연결 삽입은 같은 트랜잭션이며 기존 DB의 작업·출처 행은 보존한다.
한 작업의 여러 연결은 보존하되 현재 상세 화면은 최신 출처 하나를 표시한다.
같은 창 제목에서 정제 후 URL이 바뀐 수동 캡처는 세션을 나눠 이전 출처를 보존한다.
query/fragment만 다른 URL은 기존 정제 정책상 같은 URL이다.
기존 요청에서 작업 ID를 생략하면 자료만 저장하며 기존 데이터에 연결을 임의로 보충하지 않는다.

## 검증 범위

Python 통합 테스트는 실제 Uvicorn·QtNetwork·SQLite·DOCX 추출을 사용하고 OS 감지 입력만 가상화한다.
확장 테스트는 `node --test tests/browser/test_capture.mjs`로 실행한다(Node 22 이상).
여기서는 Chrome API/HTTP 경계의 전송과 중단 처리를 검증하며, 설치된 Chrome/Edge 수동 동작 확인을 대체하지 않는다.
Windows 실제 창/탭 전환과 한글·배율 수동 검증은 별도로 남긴다.
