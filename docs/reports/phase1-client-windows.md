# Phase 1B/1C 및 Windows 검증

## 결정 및 구현

사용자가 PySide6를 최종 선택했다. 1B 상태 화면 및 독립 진입점, 1C QtNetwork 연결을 구현했다.
Backend 구현을 Client에서 직접 import하지 않는다. 서비스/API 버전, 응답 형태를 검사한다.
3초 timeout, 중복 요청 방지, 요청 중 종료 정리, 마지막 확인 시각 표시를 포함한다.

## 검증 상태

- 로컬 환경: Linux / Python 3.12.14 / Qt offscreen.
- 로컬 결과: pytest 27개 통과, Ruff 및 git diff --check 통과. 기존 의존성 deprecation warning 2건 유지.
- Windows 실행 환경은 로컬에 없다. GitHub Actions Windows runner로 자동 검증을 시도한다.
- Windows CI: 실행 대기. 결과가 확인되기 전 통과로 처리하지 않는다.
- Windows 10/11 실제 데스크톱 수동 검증: 미실행.
- main 병합: Phase 1 개발·테스트 완료까지 보류.

자동 검증은 UI 생성, 응답별 표시, timeout 및 이벤트 루프 생존, 요청 중 종료,
실제 Backend 미실행→연결→종료→재기동 복구를 검사한다.
수동 확인 절차는 [개발 환경](../dev/development-setup.md)에 기록했다.
