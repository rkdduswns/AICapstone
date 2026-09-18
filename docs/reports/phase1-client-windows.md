# Phase 1B/1C 및 Windows 검증

## 결정 및 구현

사용자가 PySide6를 최종 선택했다. 1B 상태 화면 및 독립 진입점, 1C QtNetwork 연결을 구현했다.
Backend 구현을 Client에서 직접 import하지 않는다. 서비스/API 버전, 응답 형태를 검사한다.
3초 timeout, 중복 요청 방지, 요청 중 종료 정리, 마지막 확인 시각 표시를 포함한다.

## 검증 상태

- 로컬 환경: Linux / Python 3.12.14 / Qt offscreen.
- 로컬 결과: pytest 27개 통과, Ruff 및 git diff --check 통과. 기존 의존성 deprecation warning 2건 유지.
- Windows 실행 환경은 로컬에 없어 GitHub Actions Windows runner에서 자동 검증했다.
- Windows CI: Python 3.11.9 및 3.12.10 모두 27개 통과. 설치, pip check, Ruff도 통과.
- Windows 10/11 실제 데스크톱 수동 검증: 미실행.
- main 병합: Phase 1 개발·테스트 완료까지 보류.

자동 검증은 UI 생성, 응답별 표시, timeout 및 이벤트 루프 생존, 요청 중 종료,
실제 Backend 미실행→연결→종료→재기동 복구를 검사한다.
수동 확인 절차는 [개발 환경](../dev/development-setup.md)에 기록했다.

## Windows 최초 실행 및 수정

[최초 실행](https://github.com/rkdduswns/AICapstone/actions/runs/35389845994)에서
Windows Server 2025 Datacenter(build 26100), Python 3.11.9 환경을 확인했다.
서버 미실행 시 연결 거절 대신 3초 timeout이 먼저 발생하여 기대 메시지 검사가 실패했다.
실패 시 UI 생존이라는 계약에 맞게 연결 거절과 시간 초과를 모두 허용하도록 수정했다.
연결 성공 및 재기동 복구 검사는 유지하며 Windows 재검증 결과를 별도 기록한다.

## Windows 최종 자동 검증 결과

- 검증 커밋: `e2fc98e03ef8594b3dd9dcdc9ed8fe771402ca29`.
- [성공한 Windows 실행](https://github.com/rkdduswns/AICapstone/actions/runs/35390028720).
- OS: Windows Server 2025 Datacenter, build 26100. Qt 기본 Windows 플랫폼 사용(offscreen 아님).
- Python 3.11.9: 27 passed, 2 warnings / 20.00s.
- Python 3.12.10: 27 passed, 2 warnings / 20.97s.
- 경고는 기존 Starlette/httpx 및 AnyIO deprecation warning이며 실패 없음.
- JUnit 결과는 해당 실행의 버전별 artifact에 보관된다.

두 환경에서 Qt 창 생성·표시, 비동기 응답, 실패/timeout/정상 복구, 요청 중 창 종료,
실제 Backend 프로세스 실행 및 HTTP 왕복을 확인했다. CI에서 사람의 화면 조작은 수행하지 않았다.
Windows 10/11 실제 기기의 한글 글꼴·배율·수동 종료 확인은 남아 있어 Phase 1 전체 완료와 main 병합은 보류한다.
