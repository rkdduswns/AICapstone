# Phase 11–14 실제 API 통합

2026-11-27(KST), `feat/phase11-14-api-integration` 기준이다. `main 7e0991e`와
`feat/phase11-backend 4ba10cf`를 함께 반영한다. main 병합 여부와 전체 Phase 완료는 별개다.
[검증 결과와 남은 작업](../reports/phase11-14-api-integration.md)을 따른다.

## 실행과 모델 준비

기본 수집·기록·조건 검색·세션 화면은 기존 개발 설치로 실행한다. 의미 검색과 답변에는
추가 모델 환경이 필요하다. Windows PowerShell에서 저장소 루트 기준으로 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ml]"
# 첫 실행 전 E5 모델을 내려받아 준비한다. 다운로드에는 인터넷이 필요하다.
.\.venv\Scripts\python.exe -c "from backend.embedding import EmbeddingService; print(len(EmbeddingService().embed_query('검색 준비')))"
```

임베딩은 `intfloat/multilingual-e5-small`, CPU, 384차원이다. 실제 모델 tokenizer로 분할하고
질의/본문 접두어를 사용한다. [모델 설명](https://huggingface.co/intfloat/multilingual-e5-small)을 참고한다.
Ollama를 설치한 뒤 다음 명령으로 Backend 기본 생성 모델을 준비한다.

```powershell
ollama pull qwen2.5:3b
ollama serve
```

Ollama가 이미 실행 중이면 추가 서버를 띄울 필요가 없다.
[Ollama 실행 안내](https://docs.ollama.com/quickstart)를 따른다.
기본 주소는 `http://127.0.0.1:11434`, 모델은 `qwen2.5:3b`다.
기존 Backend 변수 `CONTEXTTRACE_OLLAMA_URL`, `CONTEXTTRACE_OLLAMA_MODEL`로 변경할 수 있다.
생성 요청은 loopback HTTP만 사용하며 프록시·리다이렉트를 따르지 않는다.

```powershell
# 별도 터미널 두 개에서 실행한다.
.\.venv\Scripts\python.exe -m backend
.\.venv\Scripts\python.exe -m client
```

Client 메뉴의 현재 작업/연결에서 연결을 확인한다. 최근 기록에서 실제 작업을 선택하고
PDF/DOCX를 연결하거나 [수동 브라우저 확장](history-source-linking.md)으로 페이지를 연결한다.
수집은 모델 다운로드를 기다리지 않는다. 실제 원문·출처·텍스트 청크를 먼저 저장하고,
첫 의미 검색/질문 시 누락된 벡터를 실제 원문으로 생성한다. 가짜 벡터로 대체하지 않는다.
오래된 연결 자료도 검색 전에 색인한다. 큰 미색인 자료가 많으면 첫 요청이 오래 걸릴 수 있다.
Client 의미 검색/답변 제한은 180초, Ollama 생성 제한은 120초다. UI 취소는 응답 수신을 중단하며
이미 시작한 서버 모델 추론까지 강제 중단하는 기능은 아니다.

## 화면과 실제 경로

| 화면/동작 | API | 연결 내용 |
|---|---|---|
| 조건 검색 | `GET /records/search` | 제목·프로그램·출처·기간 AND 조건과 정렬 |
| 의미 검색 | `POST /records/semantic-search` | 실제 저장 조각·벡터 유사도, 조건 결합, 실제 출처 |
| 작은 검색창 질문 | `POST /records/answer` | 검색 근거→Ollama→인용 근거·원본 출처 |
| 세션/타임라인 | `GET /sessions`, `GET /sessions/{id}` | 실제 세션 ID, 작업 페이지, 연결된 자료 |
| 선택 작업 삭제 | `DELETE /records/{id}` | 확인 후 원문 연결·검색 자료 함께 삭제 |
| 전체 기록 삭제 | `DELETE /records?confirm=true` | 확인 후 전체 자료 삭제, 설정 유지 |

일반 실행의 `_answer_unavailable` 대체 응답과 기본 의미 검색 미리보기 공급자를 제거했다.
조건·의미 검색·세션을 실제 메뉴로 노출한다. `tools/preview_*`는 명시적 가상 화면 검증 도구로 유지한다.
모델 미설치/중지, 거부, 근거 부족, 취소는 각각 표시하며 성공한 가상 답변으로 바꾸지 않는다.

## ID·출처·보호 정책

- 문서/브라우저 수집은 `context_id`와 기존 `record_id`를 수용한다. 충돌·강제 숫자 변환은 거부한다.
  현재 창이 바뀐 브라우저 연결도 기존 검사에 따라 거부한다.
- 이전 DB의 실제 출처 연결표에서만 작업 ID를 복원한다. 제목·시각 근접성으로 연결하지 않는다.
  독립 수집 웹은 `context_id=null`이며 UI에 작업 연결 없음·수집 시각을 표시한다.
  연결 없는 구형 문서 업로드는 계속 지원하지만 작업/색인을 임의 생성하지 않는다.
- Client가 보낸 원본 파일 경로는 그대로 보존한다. Backend 관리 복사본은 `stored_file_path`로 구분한다.
  삭제는 명시적으로 기록한 관리 복사본에만 적용하며 사용자 원본 경로의 파일을 지우지 않는다.
- 검색/답변은 실제 청크 ID·작업 ID·원본 URL/경로·열람/마지막 활성/수집 시각을 구분한다.
  Client는 제출 질의·프로토콜·중복 ID·출처 불일치를 검사한다.
- 기존 영속 일시정지·차단 프로그램·클립보드 정책과 본문 저장 전 403을 보존한다.
  검색과 모델 입력 전에 현재 정책을 재검사하고, 생성 중 삭제/차단된 근거는 반환하지 않는다.
  URL 차단 및 보호 저장/메모 기능은 이번 구현에 포함되지 않는다.
- 원문 갱신·정책 변경·삭제는 파생 색인을 무효화한다. 삭제한 진행 중 작업은 수집기 캐시에서도 비워
  종료 시 같은 ID가 다시 저장되지 않게 한다. 수집을 재개하면 새 작업은 생길 수 있다.
- 기존 SQLite 기록·설정과 읽기 전용 전처리 CLI를 유지한다. 알려진 실험용 `record_id`형
  `search_chunks`는 `legacy_search_chunks_v1`로 보존하고 실제 원문에서 새 색인을 만든다.
  확인되지 않은 스키마는 추정 변환하지 않는다. 실제 사용자 DB 사용 전 파일을 복사해 검증한다.

## 검증 순서

1. 연결 확인→최근 작업에 문서 연결→조건 검색에서 같은 작업과 경로를 확인한다.
2. 의미 검색에서 문서 내용의 다른 표현을 입력하고 관련 결과/원본 경로를 확인한다.
3. 작은 검색창에서 질문하고 전체 답변→근거→출처 정보에서 실제 작업/수집 시각을 대조한다.
4. 무관한 질문의 근거 부족, Ollama 중지 시 오류, 요청 취소 후 UI 조작을 확인한다.
5. 세션에서 같은 작업/자료를 조회하고 삭제 확인의 취소/승인을 각각 확인한다.
6. Backend 재시작 후 남은 자료를 재검색하고 일시정지/차단 설정을 확인한다.

자동 검증은 `python -m pytest -q`, `python -m ruff check src tests tools`,
`node --test tests/browser/test_capture.mjs`, `python -m pip check`로 수행한다.
`tests/integration/test_phase11_14_live.py`는 실제 Qt·Uvicorn·SQLite·DOCX·Ollama 전송 어댑터를
실행한다. OS 감지와 모델 추론 출력은 제어된 대역이며 실제 모델 품질 검증을 대신하지 않는다.

## Backend 기본 형식 및 Windows 통합판

표준 문서 첨부는 multipart `file`, `context_id`를 보낸다. 통합 서버는 선택 확장인
`original_file_path`를 검증해 보존하고, 표준 업로드의 `file_path`에는 관리 복사본 경로를 저장한다.
기본 서버가 201 응답에 작업 ID를 생략해도 업로드는 성공으로 처리하고 실제 목록을 다시 읽는다.
요청한 ID를 연결 확인으로 간주하지 않는다. 이전 `record_id` 입력은 하위 호환용이다.
삭제는 검증한 관리 복사본만 처리한다.

의미 검색의 웹 결과 ID는 `web-{브라우저 출처 ID}`다. 작업 연결은 선택 필드 `context_id`로 구분한다.
기본 검색의 `record` 및 평면 RAG 근거만으로도 표시한다. 확장 스냅샷이 없으면
Backend가 알려 준 파일 위치·응답 시각을 원본 경로·본문 확보 시각으로 해석하지 않는다.
확장 필드가 있되 서로 모순되는 경우는 오류로 처리한다.

이전 최소 EXE와 달리 최신 ZIP에는 공식 E5 모델의 고정 리비전 ONNX 파일과
CPU 추론 런타임이 함께 들어 있다. Python 설치 없이 압축 폴더에서 Backend → Client 순으로 실행한다.
`강써치-Backend.exe --check-embedding`으로 실제 한국어 질의와 두 본문의 관련도 비교를 점검할 수 있다.
모델 파일은 EXE와 함께 이동한다. Ollama와 생성 모델은 별도 설치가 필요하다.
