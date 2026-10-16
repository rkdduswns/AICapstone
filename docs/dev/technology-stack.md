# 현재 사용 기술 스택

확인일: 2026-10-10. 기준: Phase 8 Client 브랜치의 `pyproject.toml`, 실제 소스 및 CI 설정.
요구 버전은 설치 범위이고, 확인 버전은 이번 로컬 검증 환경의 값이다. 버전 고정 파일은 아직 없다.

## 실행 및 구현

| 영역 | 사용 기술 | 요구 버전 / 확인 버전 | 현재 역할 |
|---|---|---|---|
| 언어 | Python | >=3.11 / 로컬 3.14.7 | Client, Backend, Shared, 개발 도구 |
| Client GUI | PySide6 / Qt Widgets | >=6.8,<7 / PySide6·Qt 6.11.2 | 데스크톱 창·탭·표·설정·상세 표시 |
| Client 비동기 처리 | QtCore Signal, QTimer | PySide6 포함 | UI 이벤트, 폴링, timeout, 상태 전환 |
| Client HTTP | QtNetwork QNetworkAccessManager | PySide6 포함 | UI를 막지 않는 비동기 GET/PUT, 응답 취소 |
| Backend API | FastAPI | >=0.115,<1 / 0.141.1 | 현재 `/health`와 공통 HTTP 오류 처리 골격 |
| Backend 실행 | Uvicorn | >=0.30,<1 / 0.53.0 | 로컬 ASGI 서버 실행 |
| Backend 간접 의존성 | Starlette | FastAPI가 관리 / 1.7.0 | HTTP 예외·미들웨어·테스트 기반 |
| 공통 데이터 | Python dataclasses, typing | 표준 라이브러리 | 상태·작업·개인정보·복사 항목·브라우저 출처·저장 웹 본문 계약 |
| 통신 형식 | HTTP + JSON | API version 1 | 별도 Client/Backend 프로세스, `127.0.0.1` 기본 8765 포트 |
| 데이터 검증·표시 | json, datetime, urllib.parse, re, ipaddress | Python 표준 라이브러리 | 응답 검증, 시각 변환, URL 입력 정규화 |
| 대상 환경 | Windows | 로컬 Windows 10 build 19045 | 현재 데스크톱 실행·검증 대상 |

Client는 Backend 내부 모듈이나 저장소를 직접 참조하지 않는다.
Backend의 작업 수집·시간 계산·영속 저장·보호 판정은 아직 구현 전이며,
Phase 2~8 Client는 Shared 계약과 가상 HTTP 응답으로 검증했다.

## 개발·검증·관리

| 영역 | 사용 기술 | 요구 버전 / 확인 버전 | 역할 |
|---|---|---|---|
| 테스트 | pytest | >=8,<10 / 9.1.1 | 단위·가상 HTTP·Qt 이벤트 루프·Backend 골격 회귀 검증 |
| Backend 테스트 HTTP | HTTPX | >=0.27,<1 / 0.28.1 | FastAPI/Starlette TestClient 기반 검증 |
| 정적 검사 | Ruff | >=0.9,<1 / 0.16.8 | 오류 및 import 정렬 검사, Python 3.11 기준 |
| 가상 서버 | http.server, threading | Python 표준 라이브러리 | 실제 작업 정보를 읽지 않는 테스트 및 미리보기 |
| 패키징 | pyproject.toml, setuptools | 빌드 요구 setuptools>=68 | `src/` 패키지 검색, 격리 빌드, editable 설치 |
| 실행 환경 | venv, pip, PowerShell | Python/Windows 도구 | 가상 환경, 의존성 설치·확인, 실행 |
| 버전 관리 | Git, GitHub, 브랜치, Draft PR | 저장소 설정 | Client/Backend 및 Phase별 변경 이력·검토 |
| CI | GitHub Actions | windows-latest, Python 3.11/3.12 | 의존성·Ruff·pytest 및 결과 파일 보관 |
| 문서 | Markdown | 저장소 문서 | 기획, Phase 체크리스트, API 계약, 검증 근거 |

CI 액션은 `checkout@v4`, `setup-python@v5`, `upload-artifact@v4`다.
`etc/study/`는 실행 코드·테스트·정적 검사·패키징에서 제외된 학습 자료 영역이다.
Phase 7~8에서는 새 외부 의존성을 추가하지 않았다.

## 아직 도입하지 않은 항목

- Chrome/Edge 확장 프로그램: 대상 브라우저만 정해졌고 실제 확장 코드·manifest·JavaScript/TypeScript 스택은 없다.
- Windows 활성 창/클립보드 수집 라이브러리: 실제 OS 수집 구현 전이다.
- DB, ORM, 벡터 DB, 검색 색인: 코드에 도입되지 않았다.
- LLM API/모델, 임베딩 모델, RAG framework: 코드에서 선택·연결되지 않았다.
- 웹 UI framework, WebSocket: 현재 Client는 Qt Widgets와 HTTP/JSON을 사용한다.

기획 문서의 예시 기술은 실제 채택으로 간주하지 않는다. 새 Phase에서 채택할 때 이 문서와 의존성을 갱신한다.

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
