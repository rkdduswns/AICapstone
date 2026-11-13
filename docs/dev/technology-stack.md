# 현재 사용 기술 스택

확인일: 2026-11-13. 기준: `69473fe`에 PR #17~20을 합친 강써치 통합본, `pyproject.toml`, 실제 소스 및 CI 설정.
별도 Backend 브랜치 `feat/phase10-backend`의 `c95b440`과 현재 통합본의 차이는 [통합 계약 비교](compact-backend-integration.md)를 따른다.
아래 요구 버전은 설치 범위다. lock 파일이 없으며 실제 설치 버전은 각 검증 보고서의 환경을 따른다.

## 실행 및 구현

| 영역 | 사용 기술 | 요구 버전 | 현재 역할 |
|---|---|---|---|
| 언어 | Python | >=3.11 | Client, Backend, Shared, 개발 도구 |
| Client GUI | PySide6 / Qt Widgets | >=6.8,<7 | 소형 검색창·관리 화면·답변/근거 미리보기 |
| Client 비동기 처리 | QtCore Signal, QTimer | PySide6 포함 | UI 이벤트, 폴링, timeout, 상태 전환 |
| Client HTTP | QtNetwork QNetworkAccessManager | PySide6 포함 | 비동기 조회·설정 변경·문서 업로드, 응답 취소 |
| Backend API | FastAPI | >=0.115,<1 | 상태·현재 작업·최근 기록·보호 설정·복사 텍스트·웹/문서 저장·본문 조회 |
| Backend 실행 | Uvicorn | >=0.30,<1 | 로컬 ASGI 서버 실행 |
| Backend 간접 의존성 | Starlette | FastAPI가 관리 | HTTP 예외·미들웨어·테스트 기반 |
| Windows 수집 | ctypes / Win32 API | Python 표준 라이브러리 | 활성 창·프로세스·클립보드 읽기, 자동 입력 기반 회귀 검증 |
| 기록 저장 | sqlite3 / SQLite | Python 표준 라이브러리 | 세션·웹/문서·클립보드 저장과 명시적 출처 관계 |
| 문서 추출 | pypdf, python-docx | >=5,<7 / >=1.1,<2 | 선택 PDF·DOCX의 텍스트 추출 |
| 파일 업로드 | python-multipart | >=0.0.20 | FastAPI 문서 multipart 요청 처리 |
| 브라우저 확장 | Chrome/Edge Manifest V3, JavaScript | 저장소의 확장 소스 | 버튼으로 페이지 수동 캡처·작업 ID 연결·토큰 전송 |
| 공통 데이터 | Python dataclasses, typing | 표준 라이브러리 | 상태·작업·개인정보·복사 항목·브라우저 출처·저장 웹 본문 계약 |
| 통신 형식 | HTTP + JSON | API version 1 | 별도 Client/Backend 프로세스, `127.0.0.1` 기본 8765 포트 |
| 데이터 검증·표시 | json, datetime, urllib.parse, re, ipaddress | Python 표준 라이브러리 | 응답 검증, 시각 변환, URL 입력 정규화 |
| 대상 환경 | Windows | 지원 Python 3.11 이상 | 데스크톱 제품 대상, 3.11·3.12 자동 검증과 실제 수동 검증 구분 |

Client는 Backend 내부 모듈이나 저장소를 직접 참조하지 않는다.
현재 통합본은 실제 HTTP·SQLite·문서 추출 라이브러리와 연결돼 있다.
자동 테스트의 OS 입력은 가상 자료를 사용하므로 실제 Windows·Chrome/Edge 수동 검증 완료를 뜻하지 않는다.
검색·답변 화면의 가상 미리보기와 실제 데이터의 수집/조회 연결도 구분한다.

## 개발·검증·관리

| 영역 | 사용 기술 | 요구 버전 | 역할 |
|---|---|---|---|
| 테스트 | pytest | >=8,<10 | 단위·가상 HTTP·실제 HTTP/SQLite 통합·Qt 이벤트 루프 회귀 검증 |
| Backend 테스트 HTTP | HTTPX | >=0.27,<1 | FastAPI/Starlette TestClient 기반 검증 |
| 정적 검사 | Ruff | >=0.9,<1 | 오류 및 import 정렬 검사, Python 3.11 기준 |
| 가상 서버 | http.server, threading | Python 표준 라이브러리 | 실제 작업 정보를 읽지 않는 테스트 및 미리보기 |
| 패키징 | pyproject.toml, setuptools | 빌드 요구 setuptools>=68 | `src/` 패키지 검색, 격리 빌드, editable 설치 |
| Windows 배포 | PyInstaller | build extra >=6.16,<7 | Client·Backend 단일 EXE와 ZIP 생성 |
| 확장 검증 | Node.js 내장 테스트 도구 | 실행 환경에서 확인 | 브라우저 확장 JavaScript 자동 테스트 |
| 실행 환경 | venv, pip, PowerShell | Python/Windows 도구 | 가상 환경, 의존성 설치·확인, 실행 |
| 버전 관리 | Git, GitHub, 브랜치, Draft PR | 저장소 설정 | Client/Backend 및 Phase별 변경 이력·검토 |
| CI | GitHub Actions | windows-latest, Python 3.11/3.12 | 의존성·Ruff·pytest 및 결과 파일 보관 |
| 문서 | Markdown | 저장소 문서 | 기획, Phase 체크리스트, API 계약, 검증 근거 |

CI 액션은 `checkout@v4`, `setup-python@v5`, `upload-artifact@v4`다.
`etc/study/`는 실행 코드·테스트·정적 검사·패키징에서 제외된 학습 자료 영역이다.
Phase 7~8 Client 선행 작업 당시에는 새 외부 의존성을 추가하지 않았고, 이후 Backend 문서 추출·업로드와 EXE 패키징 의존성이 추가됐다.

## 현재 통합본에 연결하지 않은 항목

- 자동 탭/URL 변경·열린 파일 감지, URL 차단: 수동 캡처·문서 선택과 구분하는 후속 범위다.
- 검색 색인 저장·삭제: 별도 `d274643` 작업이며 아직 미통합이다. 설정 영속화와 읽기 전용 전처리·조각 생성은 PR #17~20 합류 범위에 포함한다. [브랜치 기준](branch-integration.md)을 따른다.
- 실제 조건/의미/혼합 검색 HTTP API와 LLM 답변 API: 일반 Client 실행에 연결되지 않았다.
- 임베딩·검색 내부 구현: `c95b440`에 있으나 현재 수집·출처·보호 계약을 보존하는 통합은 미완료다.
- 웹 UI framework, WebSocket: 현재 Client는 Qt Widgets와 HTTP/JSON을 사용한다.

기획 문서의 예시 기술은 실제 채택으로 간주하지 않는다. 새 Phase에서 채택할 때 이 문서와 의존성을 갱신한다.

## 과거 검증 환경

2026-10-10 Phase 8 Client의 로컬 확인 버전은 Windows 10 build 19045 / Python 3.14.7 /
PySide6·Qt 6.11.2 / FastAPI 0.141.1 / Uvicorn 0.53.0 / Starlette 1.7.0 /
pytest 9.1.1 / HTTPX 0.28.1 / Ruff 0.16.8이었다. 당시 버전을 현재 설치 버전이나 고정 버전으로 해석하지 않는다.
아래 Phase 9~11 내용도 해당 날짜의 구현·검증 기록이다.

## Phase 9 확인 (2026-10-12)

파일 출처·저장 문서 본문 Shared 계약과 Client 상세를 추가했다. 새 외부 의존성이나 추출 라이브러리는 추가하지 않았다.
이번 검증은 Linux x86_64 / Python 3.12.14 / PySide6·Qt 6.12.0 / pytest 9.1.1 / Ruff 0.17.0이다.
위 Phase 8 Windows 확인 버전은 당시 검증 기록이며 이번 Linux 검증 버전과 구분한다.
Windows 검증은 GitHub CI 결과를 PR에 기록한다. Backend PDF/DOCX 추출·영속 저장·검색은 미구현이다.

## Phase 10 확인 (2026-10-14)

Shared 검색 조각·출처 데이터와 Client JSON 수신 검증을 추가했다. 기존 URL/파일/시각 검증을 재사용한다.
새 의존성·UI·Backend 실행 코드 변경은 없고 임베딩 모델·검색 저장소는 미도입이다.
Phase 11 검색 응답에서 이 계약을 사용하며 실제 데이터 구축은 Backend에서 진행한다.

## Phase 11 확인 (2026-10-15)

Qt Widgets 검색 폼·표·상세와 기존 QtNetwork GET을 사용한다. 기록 행 검증은 최근 조회와 공통으로 사용한다.
새 외부 의존성·Backend 검색 실행 코드 변경은 없고 실제 저장소 조건 검색·의미 검색은 미구현이다.
Windows CI는 미병합 Shared 브랜치 기준 PR에도 실행하도록 대상 브랜치를 확장했다.
