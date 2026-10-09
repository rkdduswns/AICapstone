# Phase 7 - 브라우저 기본 연동

## 목표
Chrome/Edge의 현재 탭 제목과 URL을 Windows 작업 기록에 연결한다.

## 진행 상태와 범위

- 2026-10-09: **Client DONE / 전체 IN_PROGRESS**, `feat/phase7-client`.
- Client 선행조건: Phase 4 최근 기록과 Phase 5/6 개인정보 설정. 미병합 `feat/phase6-client`에서 분기.
- 이번 범위: 브라우저 출처 표시, URL 차단 입력, Shared 계약, 가상 HTTP 검증.
- Client 완료 근거: 전체 263개 테스트 통과, 정적 검사·의존성 확인·가상 화면 배치 확인.
- 실제 Browser 수집·Backend 연결/차단/저장은 후속 구현 및 통합 검증 대상이다.
- [API 계약](../../docs/dev/browser-api.md), [검증 보고서](../../docs/reports/phase7-client.md).

## Browser
- [ ] 확장 프로그램 기본 실행
- [ ] 현재 활성 탭 감지
- [ ] 탭 제목 수집
- [ ] URL 수집
- [ ] 탭 변경 이벤트 감지
- [ ] Backend로 정보 전달

## Backend
- [ ] 브라우저 정보 수신
- [ ] Windows 활성 브라우저 작업과 연결
- [ ] URL 변경 처리
- [ ] 브라우저 작업 기록 갱신
- [ ] URL 차단 검사

## Client
- [x] 최근 작업 기록에 URL 표시
- [x] 차단 URL 설정 입력

## Shared
- [x] 브라우저 출처의 선택 필드와 조회 계약
- [x] URL 차단 규칙 및 개별 변경 계약

## Tests
- [x] 가상 HTTP 브라우저 출처 표시·구형 응답·오류 처리
- [x] 가상 HTTP URL 설정·초안 보존·적용 확인·실패 복구
- [ ] Chrome 탭 전환
- [ ] Edge 탭 전환
- [ ] 동일 탭 URL 변경
- [ ] 새 탭 / 빈 탭
- [ ] 차단 URL
- [ ] Browser와 Windows 기록 연결

## 완료 조건
- [ ] Chrome/Edge의 페이지 제목과 URL을 기록할 수 있다.
- [ ] 브라우저 탭 변경이 작업 기록에 반영된다.
- [ ] 차단 URL은 저장되지 않는다.
