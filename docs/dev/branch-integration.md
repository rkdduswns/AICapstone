# Client 개발 브랜치 통합 기준

## 2026-11-13 후속 통합

`feat/gangsearch-brand-integration`은 기존 `client_dev 69473fe`를 유지하면서 문서 정합·강써치 이름 변경과 다음 서버 작업을 합류한다.

| 포함한 작업 | 기준 커밋 | 범위 |
|---|---|---|
| PR #17 | `79078ec` | 실제 UTC 순간·문자열 ID 정렬 후 LIMIT |
| PR #18 | `fa99946` | 지원하는 보호 설정의 저장·수집 전 복원·실패 차단 |
| PR #19·#20 | `fa78f7f`·`ce10c6a` | 실제 출처를 보존하는 읽기 전용 본문 정규화·청크 CLI |

`d274643`의 색인 저장과 `c95b440`의 별도 Backend 전체는 합류하지 않는다. 두 검색 스키마 충돌과 수집 계약 차이는 [Backend 통합 설계](backend-integration-plan.md)에 기록한다.
최종 main 반영과 새 테스트·실행 파일 검증은 [강써치 통합 기록](../reports/gangsearch-integration.md)을 따른다. 아래 main 미반영·Draft 표기는 최초 정리 당시의 기록이다.

## 최초 client_dev 정리 이력

2026-11-13 확인한 `main`은 `7c307987182c629965da63824b60d36e41db4036`이다.
완료된 Client 작업은 `client_dev`에 통합하고, 후속 Client 기능은 이 브랜치를 기준으로 작은 `feat/...` 브랜치에서 진행한다.
기능 작업의 구현·검증 기록과 실제 `main` 반영 여부는 각각 남긴다.

`client_dev`는 해당 `main`에서 분기해 `feat/client-evidence-highlights`의 `7586349`를
병합 커밋 `2927871`로 통합했다. 병합 커밋의 첫 부모는 `7c30798`, 두 번째 부모는 `7586349`다.
이 병합의 코드 트리는 기존 Client 작업 끝과 동일하며, 파일 내용을 다시 조합하거나 기능을 중복 적용하지 않았다.
현재 `main`의 참조는 변경하지 않았다.

이 통합본은 Client UI와 기존 실제 연결 기반을 함께 포함한다.
`main` 대비 기존 작업 묶음에는 14개 커밋이 있으며, PR #16에서 들어온 Backend 7개·브라우저 확장 5개·Shared 2개로 이루어진
소스 14파일과 Backend 연결 테스트 2개도 포함된다.
Client 폴더만 변경하는 독립 패치로 설명하거나 Backend 의존성을 빠뜨려 검토하지 않는다.
[실제 연결 범위와 별도 Backend 계약 차이](compact-backend-integration.md)를 함께 따른다.

## 통합한 Client 작업

아래 8개 작업 끝은 모두 `2927871`의 조상임을 확인했다.
상위 작업 끝 `7586349`에 선행 Client 작업이 이미 포함되어 있으므로 이번 통합은 같은 내용을 여러 번 병합하지 않는다.
브랜치 참조를 정리한 뒤에도 이 커밋 이력은 `client_dev`에서 도달할 수 있다.

| 작업 브랜치 | 통합한 작업 끝 | 포함 내용 |
|---|---|---|
| `feat/phase12-client` | `d562783` | 자연어 검색 입력과 가상 결과 미리보기 |
| `design/compact-search-window` | `9426af7` | 소형 검색창 설계·답변 미리보기·결과 정렬 |
| `feat/compact-client-shell` | `021bec5` | 일반 실행의 소형 창과 기존 관리 화면 연결 |
| `feat/compact-client-usability` | `8947c21` | 연결 상태·요약 잘림·답변과 출처 복사 |
| `feat/compact-backend-integration` | `fe5f28b` | 소형 UI와 기존 실제 HTTP·이력 연결 통합 |
| `feat/client-reading-design` | `46404e3` | 읽기 영역 분리·공통 시각 규칙 |
| `feat/client-action-menus` | `803d36b` | 보조 동작을 한 단계 메뉴로 정리 |
| `feat/client-evidence-highlights` | `7586349` | 명시적 인용 강조·근거 선택 줄·메뉴 아이콘 |

기반 `feat/client-backend-integration`의 `b12a82a`와 `fix/capture-truncation-privacy`의 `37c9b4a`도
기존 병합 이력을 통해 포함된다. PR #16의 원격 작업 브랜치와 Draft 검토 상태는 유지한다.

## 최초 정리에서 별도로 유지했던 작업

다음 작업 끝은 이번 `client_dev` 통합에 포함하지 않았다.
각 변경의 책임과 검증 범위를 확인해 별도의 통합으로 진행한다.

| 작업 브랜치 | 확인한 작업 끝 | 별도 범위 |
|---|---|---|
| `fix/recent-record-order` | `79078ec` | PR #17, Backend의 최근 기록 제한·정렬 보정 |
| `feat/privacy-settings-persistence` | `fa99946` | PR #18, 보호 설정 저장·재시작 복원 |
| `feat/phase10-search-text-preparation` | `fa78f7f` | PR #19, 저장 본문 검색용 전처리 |
| `feat/phase10-search-chunks` | `ce10c6a` | PR #20, 출처를 보존하는 검색 조각 생성 |
| `feat/phase10-search-index` | `d274643` | 검색 조각 색인 저장·삭제 연결 |
| `feat/phase10-backend` | `c95b440` | 별도 Backend 검색·임베딩 내부 구현 |

PR #17~20과 위 별도 작업의 원격 브랜치도 이번 정리에서 유지한다.
`feat/phase10-backend`의 API와 현재 실제 연결 기반의 계약 차이는 기존 비교 문서에 기록되어 있다.
해당 브랜치의 적용 순서는 포함할 기능과 계약을 대조해 정하며, 이번 브랜치 정리만으로 서버 규격을 바꾸지 않는다.

## `main` 직접 병합 검토

초기 정리에서는 `client_dev`를 Client 개발 통합 대상으로 사용했다.
[PR #16](https://github.com/rkdduswns/AICapstone/pull/16)은 확인 시점에 Draft이며 기존 본문에 `main` 병합 보류가 명시돼 있었다.
2026-11-13 사용자는 문서 정합 검토·프로젝트명 변경과 함께 **검토 후 main에 병합할 수 있는 범위의 반영**을 요청했다.
따라서 과거 보류 문구를 새 요청 전체의 금지로 해석하지 않는다. 실제 병합 결과·대상 커밋·검증은 별도로 기록하며,
PR 상태나 본문의 완료 표시도 실제 결과를 확인하기 전에는 변경 완료로 취급하지 않는다.

현재 문서 대조 기준은 `main`의 `7c30798`과 `client_dev`의 `69473fe`다. 이 문서 수정만으로 main 참조를 변경한 것은 아니다.
Client 작업 묶음은 PR #16의 실제 연결 변경도 포함하므로, UI 검증 통과만으로 포함된 Backend·확장·보호 계약을 검토 완료로 처리하지 않는다.

`main` 검토에서는 최신 `main`과 통합본의 전체 차이, 실제 포함된 API·저장·보호 계약,
검증한 환경과 남은 수동 확인, 배포 파일에 포함되는 변경을 함께 제시한다.
저장소의 기존 개발 지침에 따라 팀원 검토 후 반영 범위를 결정한다.
남아 있는 모든 Phase의 완료를 일괄 선행조건으로 새로 정하는 것은 아니며,
별도 Backend 브랜치 적용도 합의한 범위에 따라 판단한다.

## 게시와 브랜치 정리

1. 통합본을 검증하고 `client_dev`만 원격에 게시한다.
2. 원격 `client_dev`의 작업 끝과 로컬 작업 끝이 같은지, 위 8개 커밋이 모두 조상인지 확인한다.
3. 확인한 8개 완료 Client 작업의 로컬 브랜치 참조를 정리한다. 커밋 이력은 `client_dev`에 보존한다.
4. 기존 원격 `feat/...`·Draft PR head, 독립 Backend 작업과 학습 관련 참조는 유지한다.

위 단계는 최초 `client_dev` 정리의 실행 기록이며 그 자체는 `main` 병합이나 원격 기능 브랜치 삭제를 포함하지 않았다.
새 main 반영 요청은 앞 절의 전체 차이·계약·검증 검토를 거쳐 별도로 처리한다.
특히 `feat/phase2-client`·`feat/phase3-client`·`feat/phase4-client`의 원격 참조에는 학습 문서 관련 추가 커밋이 남아 있어
일반 Client 코드가 `main`에 있다는 이유만으로 이미 병합된 브랜치로 분류하지 않는다.

## 검증 기록

병합 커밋 `2927871`과 Client 작업 끝 `7586349`의 Git 트리 SHA가
`6395911fed5bbb16d1157c48e560aaa18f325883`으로 같음을 확인했다.
위 8개 작업 끝의 조상 관계도 확인했다.

로컬 검증은 Windows Python 3.14.7·Qt 오프스크린에서 맑은 고딕 10pt를 적용해 전체 pytest
**620 passed, 1 skipped**, Node 확장 테스트 **11 passed**를 확인했다.
Ruff와 의존성 검사도 통과했다. 운영체제 수집 입력에는 가상 자료를 사용하며 실제 Windows·Chrome/Edge 수동 검증과 구분한다.

Windows 검증 워크플로의 push·PR 대상에 `client_dev`를 추가했다.

2026-11-13 원격 `client_dev`와 로컬 작업 끝이 `c2f14d7b1f1aab905b081592642633377cd3f10d`로
일치함을 GitHub API와 다시 가져온 `origin/client_dev` 참조에서 확인했다.
GitHub 비교에서도 `7586349`가 공통 조상이고 통합본은 그보다 2개 커밋 앞서며 뒤처진 커밋은 없었다.
위 8개 작업 끝이 원격 이력에 포함된 것을 다시 확인한 후 해당 로컬 브랜치만 `git branch -d`로 정리했다.
PR #16 기반 참조와 독립 Backend·원격 Draft·학습 관련 참조는 유지했다.

코드 통합본 `c2f14d7`의 [Windows 자동 검증](https://github.com/rkdduswns/AICapstone/actions/runs/43373146175)은
Python 3.11·3.12 두 환경 모두 성공했다. 이 기록 추가는 실행 코드와 기존 검증 범위를 바꾸지 않는다.

2026-11-13 문서 대조 시작 시 로컬·원격 `client_dev`는 `69473fe`로 일치했다.
후속 문서 검토와 수정 범위는 [문서 정합 검토](../reports/documentation-reconciliation.md)에 기록한다.
