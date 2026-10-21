# Phase 9 - 로컬 문서 내용 수집

## 2026-10-21 통합 상태

실제 PDF/DOCX 추출 API에 문서 가져오기 탭을 연결했다. 명시적 업로드의 파일 이름/가져온 시각만 표시하며, 자동 파일 감지·절대 경로·작업 열람 이력 연결은 남아 있다.
브랜치: `feat/client-backend-integration`. [통합 검증](../../docs/reports/client-backend-integration.md).
아래 기존 날짜의 범위 설명은 최초 Client 선행 개발 시점의 기록이다. 전체 Phase는 IN_PROGRESS다.

## 목표
PDF와 DOCX 등 로컬 문서의 내용을 추출하고 실제 파일 경로와 작업 기록에 연결한다.

## 진행 상태와 범위

- 2026-10-12: **Client DONE / 전체 IN_PROGRESS**, feat/phase9-client.
- 근거: Linux 전체 348개 테스트·정적/의존성 검사·가상 화면 검증. Windows CI 결과는 PR에 기록한다.
- 선행조건: Phase 4 최근 기록과 Phase 8 상세 조회 구조. 미병합 feat/phase8-client에서 분기한다.
- 기획의 PDF/DOCX 추출은 핵심 검색 안정화 후 확장 범위다. 구현 순서를 재검토하여
  이번에는 기존 Client 선행 흐름의 출처 표시·저장 본문 조회 계약만 추가한다.
  실제 파일 감지·추출 라이브러리 도입은 검색 흐름(Phase 10–12) 안정화 후 Backend에서 진행한다.
- 범위: 최근 기록 파일 경로·유형, 저장 문서 본문·추출 시각, 빈 결과·오류·일부 저장 상태 표시.
- Client는 파일/UNC 서버를 열거나 경로를 추정하지 않으며 PDF/DOCX를 직접 추출하지 않는다.
- [API 계약](../../docs/dev/document-content-api.md), [검증 보고서](../../docs/reports/phase9-client.md).

## Backend
- [ ] 열려 있는 파일 경로 식별
- [x] 지원 파일 유형 판별
- [x] PDF 텍스트 추출
- [x] DOCX 텍스트 추출
- [ ] 문서 내용과 파일 경로 연결
- [ ] 열람 시각과 작업 기록 연결
- [ ] 동일 파일 재처리 최소화

## Client
- [x] 최근 기록에서 파일 경로 표시
- [x] 파일 출처 상세보기

## Shared
- [x] 문서 출처와 작업별 저장 본문 조회 계약

## Tests
- [x] 가상 HTTP 문서 조회·선택 전환·오류·취소·복구
- [x] Windows 파일 출처·본문 계약·길이·구형 응답 검증
- [x] 일반 PDF
- [ ] 여러 페이지 PDF
- [x] 일반 DOCX
- [x] 내용 없는 문서
- [ ] 이동/삭제된 파일
- [ ] 동일 파일 재열람

## 완료 조건
- [x] PDF 내용을 추출할 수 있다.
- [x] DOCX 내용을 추출할 수 있다.
- [ ] 추출된 내용에서 실제 파일 경로로 역추적할 수 있다.
