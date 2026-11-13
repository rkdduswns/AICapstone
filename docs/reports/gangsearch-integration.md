# 강써치 이름 변경·main 통합 검증

작업일: 2026-11-13 (KST). 문서 대조 시작점은 `main 7c30798`, `client_dev 69473fe`다.
이 문서는 이번 통합 결과를 기록하며 과거 PR의 테스트 수·기능 완료 상태를 소급해서 바꾸지 않는다.

## 포함 범위와 이름

- 기존 Client 통합 이력과 PR #16의 실제 HTTP·SQLite·출처 연결 기반을 보존했다.
- PR #17(`79078ec`)의 최근 기록 정렬, PR #18(`fa99946`)의 보호 설정 영속화,
  PR #19·#20(`fa78f7f`·`ce10c6a`)의 읽기 전용 본문 전처리·청크 생성을 합류했다.
- 화면·확장·문서·미리보기·새 배포 파일의 제품명을 **강써치**로 변경했다.
  Python 배포명은 패키지 이름 규격에 맞는 `gangsearch`다. 실행 모듈 `client`·`backend`·`shared`는 유지한다.
- 새 Windows 파일은 `강써치-Client.exe`, `강써치-Backend.exe`, `강써치-Windows-x64.zip`이다.
  PR #16의 과거 ZIP은 구버전이며 새 이름·설정 영속화가 반영된 산출물로 설명하지 않는다.

기존 설치와의 연결을 보존하는 식별자는 제품 표시명과 구분한다.

| 유지하는 값 | 이유 |
|---|---|
| 저장소 `rkdduswns/AICapstone`과 실제 URL | GitHub 저장소 이름 자체를 변경한 것은 아니다. 기존 링크·clone 경로를 보존한다. |
| API v1 `service: contexttrace-backend`, `X-ContextTrace-Client` | 기존 Client·Backend 간 통신 계약을 깨지 않는다. |
| 사용자 홈 `.contexttrace/activity.db` | 기존 기록과 보호 설정을 같은 DB에서 이어 읽는다. 새 빈 DB로 전환하지 않는다. |
| `CONTEXTTRACE_BROWSER_TOKEN` | 새 `GANGSEARCH_BROWSER_TOKEN`이 없을 때만 호환 수용한다. 명시 인수가 최우선이고 새 빈 값도 보존한다. |

기획 원문은 이름만 바꾸고 설계 내용을 재작성하지 않았다. `etc/study/`와 프로젝트의 읽기 전용 동기화 자료는 수정하지 않았다.

## 문서 정합

실제 Backend 수집·저장·시간·보호 검사가 아직 없다고 적힌 현재형 설명을 수정했다.
현재 계약과 과거 Phase 보고서, Client 답변 미리보기와 실제 검색/RAG 서비스를 분리했다.
설정 영속화·정렬·읽기 전용 청크의 이번 합류를 현재 문서에 반영했다.
[문서별 수정 근거](documentation-reconciliation.md)와 [브랜치 포함 범위](../dev/branch-integration.md)를 따른다.

## Backend 통합 설계와 제외 범위

`c95b440`의 앱·저장소 전체와 `d274643`의 색인 저장은 합치지 않았다.
문서 업로드의 필수 ID·원본/사본 경로, 기존 조회·보호 API 누락, 서로 다른 `search_chunks` 스키마가 충돌한다.
현재 보호 정책과 출처 연결을 유지하며 기능별로 합류하는 [통합 설계](../dev/backend-integration-plan.md)를 작성했다.

다음 최소 단계는 `context_id`/`record_id` 호환과 `truncated`의 저장·상세·검색 메타데이터 전달이다.
403 저장 거부는 유지한다. 그 뒤 DB 이관·색인, 조건 검색 HTTP, 의미 검색, RAG를 각각 검증한다.
메모·중요도·민감 본문 저장 동의와 토큰 없는 Chrome 수집은 합의·계약 확정 전 후순위다.

## 새 검증과 실제 반영

- `2e3b68e` 실행 코드: 로컬 Windows Python 3.14.7 전체 **680 통과·1 건너뜀**(POSIX 날짜 경계), Node **11 통과**, Ruff·의존성 검사 통과.
- 52개 Markdown의 로컬 링크 대상 누락 0건, 14개 Phase의 개별 체크와 통합표 개수 일치 확인.
- 기획 원문은 `69473fe` 대비 이름 교체만 있고 학습 폴더 변경은 없음을 확인.
- 최초 `2e3b68e` 패키징에서 두 환경 문제를 확인하고 수정했다. 영문 Windows cp1252 출력에서 한글 경로가 실패하므로 빌드/검증 출력은 UTF-8로 설정한다.
- 로컬 PATH의 Poppler ICU DLL은 `ucnv_open_78`만 제공하고 Qt가 요구하는 Windows ICU의 `ucnv_open`과 호환되지 않았다. PyInstaller 자식의 PATH를 Python·Windows 경로로 제한하여 다른 도구 DLL 혼입을 막는다.
- 수정 커밋 `f3d2617`의 로컬 Windows x64 빌드·실행 **8항목 모두 통과**: 소스 import 차단, 한글/공백 경로, 설치 버전 메타데이터, HTTP·SQLite, PDF/DOCX, 일시정지 403, 재시작 후 일시정지 복원, native Qt frozen Client 연결. `BUILD.json`의 commit과 두 EXE의 SHA256도 일치했다.
- `2e3b68e` [Windows 3.11·3.12 전체 검사](https://github.com/rkdduswns/AICapstone/actions/runs/43428473620)는 각각 **680 통과·1 건너뜀**이다. `f3d2617`은 이 커밋 대비 `src/`·`tests/` 변경이 없으며 패키징 경로/출력과 문서만 보완했다.
- `f3d2617` [새 Windows 3.12 패키징·실행 검사](https://github.com/rkdduswns/AICapstone/actions/runs/43429290518)는 성공했다. 새 이름 ZIP은 해당 실행의 검증된 artifact로 구분한다.

최종 통합 대상은 [PR #21](https://github.com/rkdduswns/AICapstone/pull/21)이다. 마지막 문서 변경을 포함한 head 검사·실제 main 병합 시각과 SHA는 해당 PR의 GitHub 기록을 기준으로 확인한다. 과거 Draft PR의 보류 문구를 이번 결과로 소급 변경하지 않는다. 검증 전 보호 규칙을 우회하거나 main에 직접 push하지 않는다.

Windows 10/11의 실제 창 전환·복사·파일 경로, Chrome/Edge 확장 설치·수동 캡처·403 안내,
IME·배율·다중 모니터 수동 검증은 수행하지 않았다. 자동 탭/파일 감지·URL 차단·재방문 합산과 실제 검색/LLM도 미완료다.
이 통합은 현재 구현의 개발 기준을 main으로 모으는 작업이며 전체 Phase 완료나 정식 배포 준비 완료 선언이 아니다.
