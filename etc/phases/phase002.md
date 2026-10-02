# Phase 2 - Windows 활성 창 감지

상태: **IN_PROGRESS** — Client 우선 구현 및 가상 HTTP 검증 완료(2026-09-24).
Backend 감지 및 실제 Windows 창 전환 검증은 미완료이며 Phase 전체를 완료 처리하지 않는다.

선행조건: Phase 1 DONE, PySide6/QtNetwork와 기존 HTTP 응답 형태 유지.
작업 분할: 2A Shared 계약 + Client 표시/조회 → 2B Backend 감지/API → 2C 실제 통합 검증.
[현재 창 API 계약](../../docs/dev/current-activity-api.md) · [2A 검증 결과](../../docs/reports/phase2-client.md)

## 목표
현재 사용자가 보고 있는 Windows 프로그램과 창 제목을 안정적으로 감지한다.

## Client
- [x] 현재 감지 프로그램 표시
- [x] 현재 창 제목 표시
- [x] 수집 상태 표시

Client 체크는 가상 응답 기준이다. 1초 간격 자동 조회, 3초 timeout, 실패 시 이전 정보 제거,
자동 복구, 요청 중 종료를 포함한다. Windows 감지 코드는 Client에 두지 않는다.

## Backend
- [ ] 활성 창 감지
- [ ] 프로세스 ID 확인
- [ ] 프로세스명 확인
- [ ] 프로그램명 정규화
- [ ] 창 제목 추출
- [ ] 지원하지 않는 창 처리

## Shared
- [x] 현재 작업 정보 구조 정의

## Tests
- [x] 가상 HTTP 응답으로 전환/동일 창/활성 창 없음/미지원/감지 오류 검증
- [x] 통신 실패·시간 초과·응답 검증·자동 복구·요청 취소 검증

아래 항목은 실제 Windows Backend 감지와 연결한 뒤 검증한다.

- [ ] Chrome → VS Code 전환
- [ ] Word → Explorer 전환
- [ ] 동일 창 유지
- [ ] 최소화 / 바탕화면
- [ ] 종료되는 프로그램 처리

## 완료 조건
- [ ] 현재 활성 프로그램을 확인할 수 있다.
- [ ] 현재 창 제목을 확인할 수 있다.
- [ ] 창 전환이 Client에 반영된다.
