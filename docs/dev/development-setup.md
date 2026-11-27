# 개발 환경

2026-11-27 통합 브랜치의 실제 검색·RAG·세션/삭제 및 모델 설치는 [Phase 11–14 실행 안내](phase11-14-api-integration.md)를 따른다. 이 버전의 ZIP은 CPU 추론 런타임과 E5 모델을 포함한다. 폴더 전체를 추출하고 models 폴더를 두 EXE 옆에 둔다. 생성 답변을 사용하려면 별도로 Ollama를 설치·실행하고 `ollama pull qwen2.5:3b`로 생성 모델을 준비한다.

Python 설치 없이 실행하려면 [Windows EXE 안내](windows-exe.md)를 따른다.

의존성과 패키지를 설치한 뒤 Backend를 독립 실행할 수 있다. Client도 독립 실행할 수 있다.
Client는 PySide6 Widgets, Backend는 FastAPI/Uvicorn을 사용한다.
각각 별도 프로세스로 수동 실행하며 loopback HTTP/JSON으로 통신한다.
Client는 QtNetwork로 비동기 요청을 보내고, 공통 데이터 정의는 `src/shared`에서 관리한다.

## Windows PowerShell

Python 3.11 이상과 Git을 준비한다. 기존 프로젝트의 Python 최소 버전 조건을 유지한다.
아래 예시는 Python 3.11이 설치된 경우다. 다른 지원 버전은 `py -3.11` 부분을 바꾼다.

```powershell
git clone https://github.com/rkdduswns/AICapstone.git
cd AICapstone
git switch client_dev
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from PySide6 import QtCore, QtWidgets, QtNetwork; import fastapi, uvicorn, client, backend, shared; print('Environment imports OK')"
.\.venv\Scripts\python.exe -m ruff check src tests
```

위 예시는 2026-11-13에 완료된 Client 작업과 기존 실제 연결 기반을 모은 `client_dev` 기준이다.
후속 통합본은 PR #17~20의 정렬·설정 영속화·읽기 전용 청크를 포함한다.
확인 당시 `main`의 `7c30798`에는 소형 창과 PR #16 연결 후속 변경이 모두 들어 있지 않다.
이후 실제 `main` 반영과 별도 Backend 적용 여부는 [브랜치 통합 기준](branch-integration.md)을 확인한다.
가상환경 활성화 없이 해당 Python을 직접 사용하므로 PowerShell 실행 정책 변경이 필요 없다.
이미 clone했다면 작업 중인 변경을 저장하고 `git fetch origin`, `git switch client_dev`, `git pull --ff-only origin client_dev`로 갱신한다.

## 다른 개발 환경에서 공통 코드 확인

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pip check
.venv/bin/python -m ruff check src tests
```

Linux 검증은 Windows 제품 지원을 추가한다는 의미가 아니다.
PySide6 wheel 외의 OS 그래픽 라이브러리가 필요할 수 있다. Windows 화면 검증을 Linux import로 대체하지 않는다.

## 의존성 관리

- `pyproject.toml`: 실행 의존성(PySide6, FastAPI, Uvicorn), 개발 의존성(pytest, httpx, Ruff).
- Client HTTP 요청은 QtNetwork를 사용한다. httpx는 Backend 테스트용이다.
- 이번에는 호환 범위를 설정했다. lock 파일은 없으므로 완전히 동일한 버전 재현은 보장하지 않는다.
- 검증 보고서에 OS·Python·주요 의존성 버전을 기록한다. 팀 공통 버전 고정은 별도 결정한다.
- 실제 사용자 데이터/로그/비밀값을 저장소에 넣지 않는다.

## 검증 명령의 의미

`pip check`는 의존성 일관성, import는 모듈 로딩, Ruff는 정적 검사를 확인한다.
`python -m pytest -q`는 상태 API 및 별도 Backend 프로세스의 HTTP 통합 테스트를 실행한다.
Backend, Client Qt 이벤트 루프, 실제 HTTP 연결 및 실패/복구를 검사한다. Windows CI 결과는 별도 보고서를 따른다.

## 공식 참고 문서

- [Qt for Python 설치](https://doc.qt.io/qtforpython-6/gettingstarted.html)
- [FastAPI 서버 실행](https://fastapi.tiangolo.com/deployment/manually/)

프로젝트의 실행 옵션/응답 규격은 [상태 API 계약](health-api.md)을 따른다.

## Backend 실행 및 확인 (1A)

현재 통합 브랜치의 실제 실행도 아래 두 터미널 명령을 사용한다. 과거 Phase 1 범위와
현재 연결 상태의 차이는 [통합 검증 보고서](../reports/client-backend-integration.md)를 따른다.
Windows에서는 창 감지가 동작하며 Linux에서는 `unsupported`가 정상이다.

저장소 루트에서 설치를 마친 뒤 실행한다.

```powershell
.\.venv\Scripts\python.exe -m backend
```

다른 터미널에서 상태를 확인한다.

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health | ConvertTo-Json -Depth 4
.\.venv\Scripts\python.exe -m pytest -q
```

Linux에서는 `.venv/bin/python -m backend`를 사용한다.
포트 변경: `python -m backend --port 8766`. 1–65535 범위만 허용한다.
기본 호스트는 127.0.0.1이며 외부 인터페이스로 변경하는 옵션은 제공하지 않는다.
검증용 DB를 분리하려면 `--db-path "$env:TEMP\gangsearch-check\activity.db"`를 지정한다.
생략하면 사용자 홈의 `.contexttrace/activity.db`를 사용하며 저장소 안에 DB를 만들지 않는다.
현재 통합 소스는 일시정지·차단 프로그램·클립보드 사용 설정도 같은 DB에 저장한다.
같은 DB에는 Backend 하나만 실행한다. 포트를 바꿔 별도 Backend를 실행해도 정책의 실시간 동기화는 제공하지 않는다.
종료는 Ctrl+C. 사용 중인 포트로 실행하면 오류 로그와 비정상 종료 코드가 반환된다.
Windows 자동 실행 검증과 사용자 확인 결과는 [검증 보고서](../reports/phase1-client-windows.md)를 따른다.

## Client 실행 (Windows PowerShell)

Backend와 별도의 터미널에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m client
```

서버 포트를 변경했다면 Client에도 동일하게 `--port 8766`을 지정한다.
연결 확인 후 현재 창·최근 기록·개인정보 설정을 사용한다. 최근 기록에는 진행 중인 세션도 포함한다.
클립보드는 개인정보 보호 탭에서 명시적으로 켠다.
`문서 가져오기` 탭에서는 PDF/DOCX 선택, 업로드, 목록 새로고침, 저장 본문을 확인한다.
최근 기록에서 `선택한 작업에 문서 연결`을 누르면 해당 작업에 실제 선택 경로·본문을 연결한다.
가져온 시각과 작업 시각은 별도로 보존한다. 일시정지 상태에서는 새 업로드도 거부된다.
Chrome/Edge 확장 설치·토큰 설정과 문서 연결 방법은 [이력 연결 안내](history-source-linking.md)를 따른다.
현재 통합 소스는 같은 DB로 Backend를 재실행하면 저장된 세 설정을 수집 전에 복원한다.
설정 행이 없는 DB의 기본값은 수집 허용·빈 차단 목록·클립보드 꺼짐이다.
저장·복원 오류의 중단 동작과 재확인 절차는 [개인정보 API 계약](privacy-api.md#설정-저장과-복원)을 따른다.
Linux 자동 검증은 Qt offscreen을 사용하며 Windows에서는 기본 Windows Qt 플랫폼을 사용한다.

## Windows 10/11 수동 검증

1. Backend가 없는 상태에서 Client 창이 열리고 연결 확인 시 오류가 표시되는지 확인한다.
2. Backend를 실행하고 재확인해 연결됨 및 버전이 표시되는지 확인한다.
3. Backend를 종료하고 재확인해 연결 실패가 표시되는지 확인한다.
4. Backend를 재시작하고 재확인해 복구되는지 확인한다.
5. 요청 중 창을 닫아 오류 없이 종료되는지 확인한다.
6. 창의 한글 글꼴, 배율, 버튼 조작을 확인하고 OS 버전·Python 버전·commit SHA를 결과에 기록한다.

GitHub Windows runner의 자동 테스트는 Windows Server 환경일 수 있으며 Windows 10/11 수동 검증을 대체하지 않는다.

## 검색 화면 미리보기

실제 기능은 위의 Backend·Client를 실행해 확인한다. 서버 없이 답변 상세와 의미 검색 화면의 빈 결과·오류·레이아웃을 재현하려면 저장소 루트에서 실행한다.

```powershell
python tools/preview_compact_search.py
python tools/preview_phase12_client.py
```

Phase 2~9와 11의 초기 가상 서버·실행 도구는 실제 API에 연결되어 현행 도구에서 제외했다. 당시 검증을 재현하려면 [정리 전 소스](https://github.com/rkdduswns/AICapstone/tree/a217b4b09778a0764216f54238ea288fde615afe/tools)를 같은 커밋의 Client와 사용한다. 현재 회귀 검증은 `python -m pytest -q tests/client tests/integration`으로 실행한다.
