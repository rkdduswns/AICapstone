# Phase 1 - 실행 골격 및 Client-Backend 연결

## 목표
Client와 Backend가 각각 실행되고, 최소한의 상태 요청/응답이 가능한 프로젝트 실행 골격을 만든다.

## Client
- [ ] Client 실행 진입점 구성
- [ ] 기본 메인 화면 구성
- [ ] Backend 연결 상태 표시
- [ ] 상태 확인 요청 전송

## Backend
- [ ] Backend 실행 진입점 구성
- [ ] 상태 확인 요청 처리
- [ ] 실행 상태 반환
- [ ] 기본 예외 처리

## Shared
- [ ] 공통 응답 형태 정의
- [ ] 상태 정보 구조 정의

## Tests
- [ ] Client 단독 실행
- [ ] Backend 단독 실행
- [ ] Client → Backend 상태 요청
- [ ] Backend 미실행 상태 처리

## 2인 작업 예시
**개발자 A:** Client 실행 구조, 상태 화면  
**개발자 B:** Backend 실행 구조, 상태 응답  
**공동:** 연결 테스트

## 완료 조건
- [ ] Client와 Backend가 각각 실행된다.
- [ ] Client에서 Backend 연결 여부를 확인할 수 있다.
- [ ] 연결 실패 시 프로그램이 비정상 종료되지 않는다.
