# Phase 9 Client 구현 및 검증

작업일: 2026-10-12. 브랜치: feat/phase9-client. **Client DONE / 전체 IN_PROGRESS**.

## 기준과 범위

main d9c47d1be5469085728e18dc9d53e2de0625459b에는 Client Phase 2–4가 병합됐다.
Phase 5–8은 Draft PR #8–11에 있고 최신 Client 기준은 Phase 8
ec99f73778075806ac0a79819a9241051c5a17b9다.
그 커밋에서 분기하여 PR base를 feat/phase8-client로 둔다.
선행 PR 병합 후 main 기준으로 갱신한다.

인수인계 자료의 기술·경로·진행 상태 미확정 항목은 최신 코드/지침을 기준으로 확인했다.
실제 경로는 src/client, src/backend, src/browser, src/shared이며
Python·PySide6·FastAPI·loopback HTTP+JSON 구조를 유지한다.

기획과 Phase 안내의 순서를 재검토했다. PDF/DOCX 실제 추출은 검색 안정화 후 확장 범위이고,
이번에는 Client의 파일 출처 표시와 저장 본문 조회만 추가한다.
실제 추출·DB·검색 구현과 새 외부 의존성은 추가하지 않는다.

## 구현

- 최근 기록의 선택적 document 출처. 구형 응답의 생략/null 호환.
- 파일 출처 표 열·툴팁, 작업 상세의 전체 경로·유형.
- 상세 문서 본문 탭의 지연 조회·새로고침·원문·추출 시각.
- Windows 절대 경로와 유형 검증. 실제 파일/UNC 서버 접근이나 자동 실행 없음.
- 작업 ID 및 파일 경로/유형 대조. 같은 ID의 출처 변경 시 목록 갱신 안내.
- 빈 결과·50,000자 일부 저장·미지원·거부·출처 조회 불가·timeout 구분.
- 선택/목록 갱신/재연결/종료에서 요청·본문 정리, 중복 요청 방지.
- Shared 계약, 가상 미리보기, 한국어 함수 설명·처리 흐름·설계 이유 주석.

## 검증

검증 환경: Linux x86_64, Python 3.12.14, PySide6/Qt 6.12.0, offscreen.
Windows 검증은 GitHub CI로 확인하고 결과를 PR에 기록한다.

| 범위 | 결과 |
|---|---|
| 신규 파일 출처/본문 계약·가상 HTTP | **51 passed** (전체 실행에서 확인) |
| 기존 297개 회귀 포함 전체 pytest | **348 passed**, 55.54초, 기존 경고 1건 |
| Ruff: src tests tools | 통과 |
| pip check | 의존성 문제 없음 |
| git diff --check | 통과 |
| PDF 정상/DOCX 50,000자 일부 저장/조회 거부 미리보기 | 한글·전체 출처·추출 시각·원문·버튼, 620×740 배치 확인 |

드라이브/UNC/한글 경로, 유형·확장자 일치, 구형 출처 생략, 잘못된 계약/시각/길이를 검증했다.
가상 HTTP로 지연 조회, 파일 경로 표시, 빈 본문, ID 인코딩, 늦은 응답 취소,
같은 ID의 출처 변경 후 목록 갱신, 403/404/410/500/잘못된 JSON, timeout·중복 요청·
재연결·종료·수동 복구를 확인했다.

최초 전체 실행은 Qt 이벤트 처리 중 segmentation fault로 종료됐다.
신규 테스트 fixture에서 창 종료 후 deleteLater 및 DeferredDelete 이벤트 처리로
창·자식 네트워크 객체를 명시적으로 정리했다.
수정 후 전체 344개가 통과했고, 경로 예외 4개 추가 후 최종 348개도 통과했다.
첫 종료의 정확한 내부 원인은 확정하지 않았다. Windows CI에서도 재발 여부를 확인한다.
기존 Starlette/httpx deprecation warning 1건은 유지된다.

개별 Phase와 통합 현황은 Client 2개·Shared 1개·가상 검증 2개, **5/21** 완료다.
실제 PDF/DOCX 추출 검증 항목은 미완료로 유지한다.

## 미리보기와 남은 작업

실행: python tools/preview_phase9_client.py
옵션: --file-type pdf|docx, --document-state empty|truncated|unsupported|denied|gone.
--snapshot 옵션은 선택 화면을 PNG로 저장하고 종료한다.
가상 텍스트와 가상 Windows 경로만 사용하며 실제 문서는 읽지 않는다.

실제 파일 감지·PDF/DOCX 추출·개인정보 검사·저장·재처리 최소화·원본 역추적 통합은 남아 있다.
Client 완료와 전체 Phase 완료를 구분한다. 계약: [문서 본문 API](../dev/document-content-api.md).
