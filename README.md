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

Phase 1 실행 골격 및 Client–Backend 연결을 완료했습니다(2026-09-24).
Linux 및 Windows 자동 테스트와 사용자 실행 확인을 근거로 완료 처리했습니다.
Phase 2–4는 Client 현재 창·시간·최근 기록 표시와 Shared 구조를 먼저 구현했습니다.
Backend의 Windows 감지, 시간 추적, 로컬 저장 및 실제 통합은 미완료입니다.
최신 진행 상태와 검증 근거는 [개발 Phase](etc/phases/README.md)에 기록합니다.

설치 후 `python -m backend`로 Backend를 실행하고 `http://127.0.0.1:8765/health`에서 확인합니다.
검증 명령: `python -m pytest -q`, `python -m ruff check src tests`.
[1A 구현 및 검증 결과](docs/reports/phase1-backend.md)를 참고하세요.

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
현재 Phase 1 Backend에 연결하면 연결 상태는 정상이고 현재 창 영역은 `기능 준비 중`으로 표시됩니다.

Phase 3 Client는 작업 시작 시각과 Backend 누적 활성 시간을 표시합니다. 시간 정보가 없는 기존 응답도 지원합니다.
가상 미리보기: `python tools/preview_phase3_client.py`.

Phase 4 Client는 `최근 기록` 탭에서 최근 20건과 상세 시간을 조회하고 새로고침합니다.
가상 미리보기: `python tools/preview_phase4_client.py`. 새로고침 시 가상 제목이 갱신되며 실제 작업은 저장하지 않습니다.
현재 Phase 1 Backend에 연결하면 최근 기록도 `기능 준비 중`으로 표시됩니다.
