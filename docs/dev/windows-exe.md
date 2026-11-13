# ContextTrace Windows 실행 파일

대상: Windows 10/11 x64. Client와 Backend는 서로 독립된 단일 EXE다.
Python·pip 설치 없이 실행하며 현재 통합 브랜치의 기능을 포함한다.

## 실행

1. `ContextTrace-Windows-x64.zip`을 다운로드하고 압축을 푼다.
2. `ContextTrace-Backend.exe`를 실행한다. 열린 콘솔은 유지한다.
3. `ContextTrace-Client.exe`를 실행하고 `연결 확인`을 누른다.
4. 종료할 때 Client 창을 닫고 Backend 콘솔에서 Ctrl+C를 누른다.

첫 실행에는 포함된 런타임을 임시 폴더에 풀기 때문에 시간이 걸릴 수 있다.
Backend는 현재 작업을 수집하고 `127.0.0.1:8765`에서만 응답한다. DB는 사용자 홈의
`.contexttrace/activity.db`에 저장하며 EXE 옆이나 임시 압축 해제 폴더에 저장하지 않는다.
클립보드는 기본 꺼짐이며 설정은 Backend 종료 시 초기화된다. 개발용 빌드에는 코드 서명이 없다.

브라우저의 수동 페이지 연결을 쓰려면 `browser-extension` 폴더를 Chrome/Edge에서 압축해제 확장으로 로드한다.
Backend 토큰은 같은 PowerShell에서 설정하고 실행한다. 설정값은 사용자가 확장 설정에 복사한다.

```powershell
$env:CONTEXTTRACE_BROWSER_TOKEN = [guid]::NewGuid().ToString("N")
$env:CONTEXTTRACE_BROWSER_TOKEN
.\ContextTrace-Backend.exe
```

최근 기록에서 작업을 선택한 뒤 문서를 연결할 수 있다. 상세 순서는 함께 제공한 `HISTORY-LINKING.md`를 따른다.
해당 문서의 소스 실행 명령은 EXE 실행으로 바꾸고, 확장 폴더는 `browser-extension`을 사용한다.
자동 탭/파일 감지·URL 차단·검색·LLM은 아직 미구현이다.

## 포트와 데이터 경로 변경

기본 포트를 다른 프로그램이 사용 중이면 두 프로그램에 같은 포트를 지정한다.
Backend가 이미 켜져 있다면 하나만 실행한다.

```powershell
.\ContextTrace-Backend.exe --port 8766 --db-path "C:\검증 자료\activity.db"
.\ContextTrace-Client.exe --port 8766
```

## 소스에서 다시 빌드

저장소 루트의 Windows x64 Python 3.12 환경에서 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[dev,build]"
.\.venv\Scripts\python.exe tools/build_windows.py
.\.venv\Scripts\python.exe tools/smoke_windows_exe.py
```

산출물은 `dist/ContextTrace-Windows-x64.zip`이며 내부에 실행 파일 두 개, 확장,
실행 안내, `BUILD.json`(소스 커밋·도구 버전), `SHA256SUMS.txt`가 있다.
GitHub PR의 `Windows EXE package` workflow도 같은 명령으로 빌드·검증한 ZIP을 30일간 보관한다.
빌드 의존성은 일반 실행 의존성과 분리했다. 생성 EXE·DB·토큰은 Git에 넣지 않는다.

PyInstaller onefile과 Windows windowed/console 설정을 사용하며 Backend에는 Uvicorn 동적 모듈과
프로젝트 버전 메타데이터를 포함한다. Linux에서 Windows EXE를 만든 것으로 간주하지 않는다.
근거: [패키징 동작](https://pyinstaller.org/en/stable/operating-mode.html),
[CLI 옵션](https://pyinstaller.org/en/stable/usage.html).

자동 검증은 소스 import 경로 없이 한글/공백 경로에서 EXE를 실행하고 실제 HTTP·PDF/DOCX 추출·SQLite·
일시정지 거부·네이티브 Qt 창의 연결 진단을 확인한다. Windows 10/11의 사용자 배율·실제 창 전환 수동 검증은 별도다.
