# 개발 환경

의존성과 패키지를 설치한 뒤 Backend를 독립 실행할 수 있다. Client도 독립 실행할 수 있다.
사용자 지시로 Client 기술은 PySide6 Widgets로 최종 확정했다.

## Windows PowerShell

Python 3.11 이상과 Git을 준비한다. 기존 프로젝트의 Python 최소 버전 조건을 유지한다.
아래 예시는 Python 3.11이 설치된 경우다. 다른 지원 버전은 `py -3.11` 부분을 바꾼다.

```powershell
git clone https://github.com/rkdduswns/AICapstone.git
cd AICapstone
git switch main
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from PySide6 import QtCore, QtWidgets, QtNetwork; import fastapi, uvicorn, client, backend, shared; print('Environment imports OK')"
.\.venv\Scripts\python.exe -m ruff check src tests
```

Phase 1 병합 후 최신 main을 사용한다.
가상환경 활성화 없이 해당 Python을 직접 사용하므로 PowerShell 실행 정책 변경이 필요 없다.
이미 clone했다면 작업 중인 변경을 저장하고 `git fetch origin`, `git switch main`, `git pull --ff-only origin main`으로 갱신한다.

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
- Windows 최초 실행 검증에서 설치 버전을 기록한 뒤 팀 공통 버전 고정 여부를 결정한다.
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
종료는 Ctrl+C. 사용 중인 포트로 실행하면 오류 로그와 비정상 종료 코드가 반환된다.
Windows 자동 실행 검증과 사용자 확인 결과는 [검증 보고서](../reports/phase1-client-windows.md)를 따른다.

## Client 실행 (Windows PowerShell)

Backend와 별도의 터미널에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m client
```

서버 포트를 변경했다면 Client에도 동일하게 `--port 8766`을 지정한다.
Linux 자동 검증은 Qt offscreen을 사용하며 Windows에서는 기본 Windows Qt 플랫폼을 사용한다.

## Windows 10/11 수동 검증

1. Backend가 없는 상태에서 Client 창이 열리고 연결 확인 시 오류가 표시되는지 확인한다.
2. Backend를 실행하고 재확인해 연결됨 및 버전이 표시되는지 확인한다.
3. Backend를 종료하고 재확인해 연결 실패가 표시되는지 확인한다.
4. Backend를 재시작하고 재확인해 복구되는지 확인한다.
5. 요청 중 창을 닫아 오류 없이 종료되는지 확인한다.
6. 창의 한글 글꼴, 배율, 버튼 조작을 확인하고 OS 버전·Python 버전·commit SHA를 결과에 기록한다.

GitHub Windows runner의 자동 테스트는 Windows Server 환경일 수 있으며 Windows 10/11 수동 검증을 대체하지 않는다.

## Phase 2 Client 우선 개발

실행 의존성은 Phase 1과 같다. 새 패키지 설치는 필요하지 않다.
일반 실행은 `python -m client`이며 연결 확인 성공 후 현재 창 정보를 자동 조회한다.
Phase 1 Backend에는 현재 창 API가 없어 `기능 준비 중`으로 표시된다.

Backend 감지 구현 전에 가상 데이터로 화면을 확인하려면 저장소 루트에서 실행한다.

```powershell
.\.venv\Scripts\python.exe tools/preview_phase2_client.py
```

별도 Backend 실행 없이 Chrome → VS Code → Word → Explorer → 활성 창 없음 → 미지원 → 감지 오류를
4초마다 반복한다. 상단에 가상 데이터임을 표시하며 실제 Windows 작업을 수집하거나 저장하지 않는다.
미리보기 창을 닫으면 임시 HTTP 서버도 종료된다.
이미지 저장만 하려면 `--snapshot <PNG 경로>`를 추가한다.

Client/Shared와 기존 Backend의 회귀 검증:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m pip check
```

화면 점검: 가상 데이터 안내, 프로그램·제목·수집 상태 전환, 한글, 긴 제목 줄바꿈/스크롤,
상태 변화 시 이전 창 정보 제거, 연결 재확인 및 창 종료를 확인한다.
실제 OS 감지 검증은 [Phase 2 체크리스트](../../etc/phases/phase2.md)에 별도로 남긴다.
