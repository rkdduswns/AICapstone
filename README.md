# ContextTrace

> Windows 작업 로그 기반 개인 지식 출처 역추적 RAG 시스템

ContextTrace는 Windows 환경에서 사용자의 작업 맥락을 자동으로 기록하고, 자연어 검색을 통해 과거에 확인한 정보의 실제 출처와 작업 맥락을 다시 찾는 프로젝트입니다.

## 프로젝트 문서

- [기획 및 추상설계](etc/기획-및-추상설계.md)
- [개발 지침](etc/개발-지침.md)
- [개발 Phase](etc/phases/README.md)
- [Phase 전체 체크리스트·작업 이력](etc/phases/00-progress.md)
- [Phase 1 완료 조건](etc/phases/phase001.md)
- [개발 환경 설치](docs/dev/development-setup.md)
- [Phase 1 상태 통신 규격](docs/dev/health-api.md)
- [Phase 2 현재 창 통신 규격](docs/dev/current-activity-api.md)
- [Phase 2 Client 구현 및 검증](docs/reports/phase2-client.md)
- [Phase 3 시간 표시 규격](docs/dev/activity-timing-api.md)
- [Phase 3 Client 구현 및 검증](docs/reports/phase3-client.md)
- [Phase 4 최근 기록 규격](docs/dev/recent-records-api.md)
- [Phase 4 Client 구현 및 검증](docs/reports/phase4-client.md)
- [Phase 5 개인정보 설정 규격](docs/dev/privacy-api.md)
- [Phase 5 Client 구현 및 검증](docs/reports/phase5-client.md)
- [Phase 6 클립보드 규격](docs/dev/clipboard-api.md)
- [Phase 6 Client 구현 및 검증](docs/reports/phase6-client.md)
- [Phase 7 브라우저 출처·URL 설정 규격](docs/dev/browser-api.md)
- [Phase 7 Client 구현 및 검증](docs/reports/phase7-client.md)
- [Phase 8 저장 웹 본문 규격](docs/dev/web-content-api.md)
- [Phase 8 Client 구현 및 검증](docs/reports/phase8-client.md)
- [Phase 9 문서 출처·저장 본문 규격](docs/dev/document-content-api.md)
- [Phase 9 Client 구현 및 검증](docs/reports/phase9-client.md)
- [Phase 10 검색 데이터 계약](docs/dev/search-data-contract.md)
- [Phase 10 Shared 구현 및 검증](docs/reports/phase10-shared.md)
- [Phase 11 조건 검색 API](docs/dev/search-api.md)
- [Phase 11 Client 구현 및 검증](docs/reports/phase11-client.md)
- [현재 기술 스택](docs/dev/technology-stack.md)
- [웹·문서 이력 연결 실행 안내](docs/dev/history-source-linking.md)

Phase 1 실행 골격 및 Client–Backend 연결을 완료했습니다(2026-09-24).
Linux 및 Windows 자동 테스트와 사용자 실행 확인을 근거로 완료 처리했습니다.
Phase 2–9는 Client 현재 창·시간·최근 기록·개인정보/클립보드/URL 설정·복사 텍스트·브라우저 출처·저장 웹/문서 본문·파일 출처 화면과 Shared 구조를 먼저 구현했습니다.
main에 Backend의 Windows 감지·세션 저장·브라우저 수신·문서 추출 구현이 반영됐습니다.
통합 작업 브랜치에서는 현재 창·기록·개인정보/클립보드 설정·문서 가져오기와 웹·문서의 작업 ID 연결을 실제 API에 연결했습니다.
Chrome/Edge는 확장 버튼으로 수동 연결하며 문서는 최근 기록에서 대상을 선택해 연결합니다.
Windows 수동 검증, 재방문 집계, 자동 탭/파일 감지와 실제 검색은 남아 있습니다.
최신 진행 상태와 검증 근거는 [개발 Phase](etc/phases/README.md)에 기록합니다.

설치 후 `python -m backend`로 Backend를 실행하고 `http://127.0.0.1:8765/health`에서 확인합니다.
검증 명령: `python -m pytest -q`, `python -m ruff check src tests`.
[1A 구현 및 검증 결과](docs/reports/phase1-backend.md)를 참고하세요.

## 실제 Client–Backend 실행

의존성을 설치한 뒤 프로젝트 루트의 PowerShell 두 개에서 각각 실행합니다.

```powershell
# 첫 번째 터미널: 진행 중 세션도 같은 작업 ID로 저장·갱신합니다.
.\.venv\Scripts\python.exe -m backend
```

```powershell
# 두 번째 터미널: 연결 확인 후 현재 작업·최근 기록·설정·문서 가져오기를 사용합니다.
.\.venv\Scripts\python.exe -m client
```

`최근 기록 → 선택한 작업에 문서 연결`에서 PDF·DOCX의 경로와 추출 본문을 연결합니다.
문서 저장 시각과 원래 작업 시각은 별도로 보존합니다. 대상 없이 문서만 가져올 수도 있습니다.
Chrome/Edge 확장 설치와 토큰 설정은 [이력 연결 안내](docs/dev/history-source-linking.md)를 따릅니다.
설정은 서버 재실행 시 초기화되며 클립보드 수집은 기본 꺼짐입니다.
[통합 범위·검증·남은 기능](docs/reports/client-backend-integration.md)을 확인하세요.
아래 Phase별 preview 명령은 가상 데이터 확인용입니다.

## 디렉토리 구조

```text
AICapstone/
├─ src/
│  ├─ client/
│  ├─ backend/
│  ├─ browser/
│  └─ shared/
├─ tests/
│  ├─ client/
│  ├─ backend/
│  └─ integration/
├─ tools/
├─ docs/
│  ├─ dev/
│  └─ reports/
├─ etc/
│  ├─ 기획-및-추상설계.md
│  ├─ 개발-지침.md
│  └─ phases/
├─ .github/
│  └─ workflows/
├─ .gitignore
├─ README.md
└─ pyproject.toml
```

- `src/`: 실제 프로그램 소스
- `tests/`: 단위 및 통합 테스트
- `tools/`: 개발/검증용 보조 도구
- `docs/`: 구현 관련 기술 문서 및 결과 보고
- `etc/`: 프로젝트 기획, 개발 규칙, Phase 관리 문서
- `.github/`: GitHub 자동화

`client`와 `backend` 내부 구조는 실제 구현이 진행되면서 필요한 기능 단위로 추가합니다.

Client 실행: `python -m client`.
[Client 및 Windows 검증 결과](docs/reports/phase1-client-windows.md).

Phase 2 화면의 가상 데이터 미리보기: `python tools/preview_phase2_client.py`.
실제 Backend 없이 프로그램/제목/수집 상태가 4초마다 바뀝니다. 실제 사용자 작업은 수집하지 않습니다.
최신 Backend는 실제 Windows 현재 창 API를 제공합니다. 아래 preview는 각 Phase의 가상 응답 확인용입니다.

Phase 3 Client는 작업 시작 시각과 Backend 누적 활성 시간을 표시합니다. 시간 정보가 없는 기존 응답도 지원합니다.
가상 미리보기: `python tools/preview_phase3_client.py`.

Phase 4 Client는 `최근 기록` 탭에서 최근 20건과 상세 시간을 조회하고 새로고침합니다.
가상 미리보기: `python tools/preview_phase4_client.py`. 새로고침 시 가상 제목이 갱신되며 실제 작업은 저장하지 않습니다.
최신 Backend에서는 실제 저장 기록과 진행 중인 세션을 조회합니다.

Phase 5 Client는 어느 탭에서나 일시정지·재개를 요청하고, 개인정보 보호 탭에서 차단 프로그램 목록을 적용합니다.
가상 미리보기: `python tools/preview_phase5_client.py`. `chrome.exe`를 입력하면 가상 프로그램 차단 상태를 확인할 수 있습니다.
최신 Backend의 일시정지·프로그램 차단은 실제 수집기에 적용됩니다. URL 차단 설정은 아직 미지원입니다.

Phase 6 Client는 개인정보 보호 탭에서 클립보드 기록 사용 여부를 설정하고, 최근 작업 상세의 복사 텍스트를 조회합니다.
가상 미리보기: `python tools/preview_phase6_client.py`. 설정 화면으로 시작하려면 `--settings`를 추가합니다.
미리보기는 실제 클립보드를 읽지 않습니다. 일반 실행에서는 실제 수집·작업별 조회가 연결돼 있고 Windows 수동 복사 검증은 남아 있습니다.

Phase 7 Client는 최근 작업에 연결된 브라우저 페이지 제목·URL과 URL 차단 규칙 입력을 제공합니다.
가상 미리보기: `python tools/preview_phase7_client.py`. URL 설정 화면은 `--settings`를 추가합니다.
도메인·전체 URL·URL 시작 부분 규칙을 편집하고 명시적으로 적용합니다.
통합 브랜치는 확장 버튼을 통한 URL·본문 저장과 실제 작업 ID 연결을 지원합니다. 자동 탭 전환 수집과 URL 차단은 남아 있습니다.

Phase 8 Client는 최근 기록의 `웹 본문` 탭에서 저장된 텍스트·출처·수집 시각을 확인합니다.
가상 미리보기: `python tools/preview_phase8_client.py`.
`--web-state empty|truncated|unsupported|denied` 중 하나로 빈 본문·일부 저장·미지원·조회 거부를 확인할 수 있습니다.
통합 브랜치의 실제 웹 본문 조회 API가 연결됐습니다. 수동 캡처의 동일 페이지 재전송은 갱신하며 본문 정제·URL 차단은 남아 있습니다.

Phase 9 Client는 파일 경로·유형과 저장 문서 본문·추출 시각을 확인합니다.
가상 미리보기: python tools/preview_phase9_client.py.
--file-type pdf|docx, --document-state empty|truncated|unsupported|denied|gone을 지원합니다.
통합 브랜치는 실제 PDF/DOCX 추출·저장과 명시적 작업/파일 경로 연결을 지원합니다. 자동 파일 감지는 남아 있습니다.

Phase 10은 검색 문서 조각과 확보 당시 출처의 Shared 계약 및 Client 수신 검증을 제공합니다.
원본 작업 ID·URL/파일 경로·열람/본문 확보 시각을 유지합니다.
실제 정규화·문서 분할·임베딩·저장/삭제는 Backend 작업이며, 검색 화면은 Phase 11에서 구현합니다.

Phase 11 Client는 조건 검색 탭에서 제목·프로세스명·출처·날짜 조건을 제출하고 결과 목록/상세를 확인합니다.
가상 미리보기: python tools/preview_phase11_client.py. --source 및 --state 옵션으로 결과와 오류를 확인합니다.
실제 저장소 검색은 Backend 연결 후 구현·검증합니다.
