# ContextTrace

> Windows 작업 로그 기반 개인 지식 출처 역추적 RAG 시스템

ContextTrace는 Windows 환경에서 사용자의 작업 맥락을 자동으로 기록하고, 자연어 검색을 통해 과거에 확인한 정보의 실제 출처와 작업 맥락을 다시 찾는 프로젝트입니다.

## 프로젝트 문서

- [기획 및 추상설계](etc/기획-및-추상설계.md)
- [개발 지침](etc/개발-지침.md)
- [개발 Phase](etc/phases/README.md)
- [Phase 1 준비 및 작업 순서](etc/phases/phase1-preparation.md)
- [개발 환경 설치](docs/dev/development-setup.md)
- [Phase 1 상태 통신 규격](docs/dev/health-api.md)

Phase 1 실행 골격 및 Client–Backend 연결을 완료했습니다(2026-09-24).
Linux 및 Windows 자동 테스트와 사용자 실행 확인을 근거로 완료 처리했습니다.
다음 단계는 Phase 2 Windows 활성 창 감지입니다.

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
