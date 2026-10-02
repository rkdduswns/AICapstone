# Phase 1 - 실행 골격 및 Client-Backend 연결

상태: **DONE** — 2026-09-24 사용자 테스트 결과 및 완료·병합 승인 기준.

검증 근거: [자동 및 사용자 검증 결과](../../docs/reports/phase1-client-windows.md).

## 목표
Client와 Backend가 각각 실행되고, 최소한의 상태 요청/응답이 가능한 프로젝트 실행 골격을 만든다.

## Client
- [x] Client 실행 진입점 구성
- [x] 기본 메인 화면 구성
- [x] Backend 연결 상태 표시
- [x] 상태 확인 요청 전송

## Backend
- [x] Backend 실행 진입점 구성
- [x] 상태 확인 요청 처리
- [x] 실행 상태 반환
- [x] 기본 예외 처리

## Shared
- [x] 공통 응답 형태 정의
- [x] 상태 정보 구조 정의

## Tests
- [x] Client 단독 실행
- [x] Backend 단독 실행
- [x] Client → Backend 상태 요청
- [x] Backend 미실행 상태 처리

## 2인 작업 예시
**개발자 A:** Client 실행 구조, 상태 화면  
**개발자 B:** Backend 실행 구조, 상태 응답  
**공동:** 연결 테스트

## 완료 조건
- [x] Client와 Backend가 각각 실행된다.
- [x] Client에서 Backend 연결 여부를 확인할 수 있다.
- [x] 연결 실패 시 프로그램이 비정상 종료되지 않는다.
