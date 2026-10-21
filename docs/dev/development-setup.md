# 개발 환경

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
git switch main
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from PySide6 import QtCore, QtWidgets, QtNetwork; import fastapi, uvicorn, client, backend, shared; print('Environment imports OK')"
.\.venv\Scripts\python.exe -m ruff check src tests
```

Client Phase 2–11과 Backend 구현이 통합된 main을 기준으로 한다.
실제 연결 작업은 `feat/client-backend-integration` 브랜치에서 진행한다.
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
검증용 DB를 분리하려면 `--db-path "$env:TEMP\contexttrace-check\activity.db"`를 지정한다.
생략하면 사용자 홈의 `.contexttrace/activity.db`를 사용하며 저장소 안에 DB를 만들지 않는다.
종료는 Ctrl+C. 사용 중인 포트로 실행하면 오류 로그와 비정상 종료 코드가 반환된다.
Windows 자동 실행 검증과 사용자 확인 결과는 [검증 보고서](../reports/phase1-client-windows.md)를 따른다.

## Client 실행 (Windows PowerShell)

Backend와 별도의 터미널에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m client
```

서버 포트를 변경했다면 Client에도 동일하게 `--port 8766`을 지정한다.
연결 확인 후 현재 창·최근 기록·개인정보 설정을 사용한다. 최근 기록은 종료된 세션만 표시하므로
다른 창으로 전환한 다음 새로고침한다. 클립보드는 개인정보 보호 탭에서 명시적으로 켠다.
`문서 가져오기` 탭에서는 PDF/DOCX 선택, 업로드, 목록 새로고침, 저장 본문을 확인한다.
이 시각은 가져온 시각이며 원본 열람 시각이 아니다. 일시정지 상태에서는 새 업로드도 거부된다.
설정은 현재 프로세스 메모리에서 관리하며 Backend를 재실행하면 기본값으로 초기화된다.
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
실제 OS 감지 검증은 [Phase 2 체크리스트](../../etc/phases/phase002.md)에 별도로 남긴다.

## Phase 3–4 Client 확인

Phase 2–4 Client는 2026-10-02 main에 병합했다. 최신 main에서 아래 미리보기를 실행한다.
추가 의존성은 없다. 구현 상태와 Backend 잔여 작업은 [현재 Phase 현황](../../etc/phases/00-progress.md)을 따른다.

```powershell
.\.venv\Scripts\python.exe tools/preview_phase3_client.py
.\.venv\Scripts\python.exe tools/preview_phase4_client.py
```

각 명령은 독립적인 가상 HTTP 서버와 Client 창을 띄운다. 하나씩 실행하고 창을 닫아 종료한다.
Phase 3은 시작 시각/누적 활성 시간을, Phase 4는 최근 기록 탭을 처음부터 보여준다.
Phase 4 새로고침은 같은 ID의 가상 제목을 갱신하므로 행이 중복 추가되지 않는지 확인할 수 있다.
`--snapshot <PNG 경로>`를 사용하면 첫 유효 응답의 화면을 저장하고 종료한다.

일반 `python -m client`에서는 연결 확인 후 `최근 기록` 탭을 연다.
최근 20건, 마지막 활성 시각순, 선택 상세의 전체 제목·프로세스·시각·누적 활성 시간·재방문 횟수를 확인한다.
새로고침 도중 버튼 잠금, 같은 ID 선택 복원, 긴 한글 제목의 상세 스크롤도 확인한다.
빈 목록과 오류 표시, timeout/연결 재확인/창 종료, 기존 현재 창 표시는 자동 테스트로 검증한다.
기존 Backend에는 기록 endpoint가 없어 `기능 준비 중`이 정상이다.

전체 검증 명령은 위의 pytest/Ruff/pip check와 동일하다.
[최근 기록 API 계약](recent-records-api.md)과 [Phase 4 검증 보고서](../reports/phase4-client.md)를 참고한다.
가상 미리보기 성공은 실제 저장소나 재시작 후 기록 유지 검증을 의미하지 않는다.

## Phase 5 Client 확인

추가 의존성 없이 `feat/phase5-client`의 제어 화면과 가상 HTTP 응답을 확인한다.

```powershell
.\.venv\Scripts\python.exe tools/preview_phase5_client.py
```

- 어느 탭에서나 상단 `기록 일시정지`/`기록 재개` 버튼을 사용할 수 있다.
- 개인정보 보호 탭에서 `chrome.exe`를 한 줄에 입력하고 `차단 목록 적용`을 누르면 가상 차단 상태가 표시된다.
- 빈 목록을 적용하면 차단 목록을 비운다. `입력 되돌리기`는 서버에 쓰지 않고 초안만 복원한다.
- `--reason sensitive_content`로 가상 민감 문자열 차단 표시를, `--snapshot <PNG 경로>`로 화면 저장을 확인한다.
- 미리보기 입력은 프로세스 메모리에만 존재하고 창을 닫으면 사라진다. 실제 작업은 수집/필터/저장하지 않는다.

자동 검증은 기존 pytest/Ruff/pip check 명령을 사용한다. 신규 검증 범위는 Client 계약·UI·가상 HTTP 요청이다.
실제 일시정지 중 저장 방지, 차단 프로그램/민감 문자열 차단, 재개 후 저장 및 기존 기록 불변은 Backend 연결 후 수행한다.
정상 실행에서 기존 Backend에 연결하면 보호 상태 `미확인`과 `기능 준비 중`이 표시되며 변경 버튼은 비활성화된다.
[개인정보 API 계약](privacy-api.md)과 [검증 보고서](../reports/phase5-client.md)를 따른다.

## Phase 6 Client 확인

`feat/phase6-client`는 미병합 Phase 5 Client에 의존한다. 추가 의존성은 없다.

```powershell
.\.venv\Scripts\python.exe tools/preview_phase6_client.py
.\.venv\Scripts\python.exe tools/preview_phase6_client.py --settings
```

각 명령을 하나씩 실행한다. 기본 화면은 최근 작업의 `복사 텍스트` 상세이며 `--settings`는 개인정보 설정 탭을 연다.
`--snapshot <PNG 경로>`로 첫 유효 응답을 화면 이미지로 저장하고 종료할 수 있다.

- 개인정보 보호 탭에서 초기 `꺼짐`을 확인하고 켜기/끄기를 요청한다. 전체 일시정지 상태와 입력 중 차단 목록이 유지되는지 확인한다.
- 최근 기록에서 작업을 선택하고 복사 텍스트 탭을 열어 복사 시각별 원문과 줄바꿈을 확인한다.
- 가상 저장 항목은 기록 설정을 꺼도 그대로 조회된다. 꺼짐은 이후 수집 설정이며 기존 기록 삭제 기능이 아니다.
- 미리보기는 고정된 가상 데이터만 제공한다. OS 클립보드 읽기·쓰기·감시나 파일 저장은 수행하지 않는다.
- 기존 Phase 5 응답에 클립보드 설정이 없으면 `기능 미지원`으로 표시하고 클립보드 변경 버튼만 잠근다.

가상 HTTP 검증 및 기존 기능 회귀에는 기존 pytest/Ruff/pip check 명령을 사용한다.
실제 클립보드 수집·중복 방지·작업 전환 연결·민감정보/일시정지 차단·저장은 Backend 연결 후 검증한다.
[클립보드 API 계약](clipboard-api.md)과 [Phase 6 보고서](../reports/phase6-client.md)를 따른다.

## Phase 8 Client 확인

`feat/phase8-client`는 미병합 Phase 7 Client에 의존한다. 추가 의존성은 없다.

```powershell
.\.venv\Scripts\python.exe tools/preview_phase8_client.py
.\.venv\Scripts\python.exe tools/preview_phase8_client.py --web-state truncated
```

각 명령은 하나씩 실행한다. 기본 화면은 최근 기록의 `웹 본문` 상세다.

- 페이지 제목·URL·수집 시각과 저장 본문을 확인한다. `<b>` 같은 태그도 글자로 표시되어야 한다.
- `--web-state empty`는 본문 없음, `truncated`는 길이 제한 안내와 50,000자 스크롤을 확인한다.
- `--web-state unsupported`는 API 미지원, `denied`는 조회 거부를 확인한다.
- `--snapshot <PNG 경로>`는 해당 결과를 화면 이미지로 저장하고 종료한다.
- 현재 실제 Backend에는 새 endpoint가 없으며 가상 미리보기만 본문을 제공한다.
- 실제 브라우저·외부 URL·저장소를 읽지 않는다. 화면 성공은 실제 수집/저장/차단 검증과 별개다.

검증 명령은 기존 pytest/Ruff/pip check와 동일하다.
[웹 본문 API 계약](web-content-api.md)과 [Phase 8 보고서](../reports/phase8-client.md)를 따른다.
