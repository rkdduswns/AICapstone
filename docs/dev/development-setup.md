# Phase 1 개발 환경

현재 설치 가능한 것은 의존성과 `client`, `backend`, `shared` 패키지 경계다.
앱 실행 명령은 Phase 1 구현 후 제공한다.
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
현재 동작 테스트가 없으므로 `python -m pytest`는 테스트 없음(exit 5) 상태이며 통과로 취급하지 않는다.
Phase 1 구현 시 단위 및 실제 HTTP 통합 테스트를 추가하고 `python -m pytest`를 완료 기준에 포함한다.
CI는 그 검증 명령이 실제 기능을 검사하게 된 시점에 추가한다.

## 공식 참고 문서

- [Qt for Python 설치](https://doc.qt.io/qtforpython-6/gettingstarted.html)
- [FastAPI 서버 실행](https://fastapi.tiangolo.com/deployment/manually/)

프로젝트의 실행 옵션/응답 규격은 [상태 API 계약](health-api.md)을 따른다.
