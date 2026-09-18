# Phase 1 개발 환경

의존성과 패키지를 설치한 뒤 Backend를 독립 실행할 수 있다. Client 화면은 아직 미구현이다.
Client 설치 설정은 PySide6 임시 구성안이며 최종 기술 선택은 아직 미확인이다.

## Windows PowerShell

Python 3.11 이상과 Git을 준비한다. 기존 프로젝트의 Python 최소 버전 조건을 유지한다.
아래 예시는 Python 3.11이 설치된 경우다. 다른 지원 버전은 `py -3.11` 부분을 바꾼다.

```powershell
git clone https://github.com/rkdduswns/AICapstone.git
cd AICapstone
git switch chore/phase1-preparation
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from PySide6 import QtCore, QtWidgets, QtNetwork; import fastapi, uvicorn, client, backend, shared; print('Environment imports OK')"
.\.venv\Scripts\python.exe -m ruff check src tests
```

PR merge 후에는 준비 브랜치 전환 대신 최신 main을 사용한다.
가상환경 활성화 없이 해당 Python을 직접 사용하므로 PowerShell 실행 정책 변경이 필요 없다.
이미 clone했다면 다시 clone하지 않고 준비 브랜치를 fetch/checkout한다.

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
현재 13개 테스트가 있으며 Client 테스트와 CI는 아직 추가하지 않았다.

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
Windows 명령은 안내이며 실제 Windows 실행 검증은 1D에 남아 있다.
