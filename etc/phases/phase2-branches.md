# Phase 2 Client / Backend 브랜치 운영

기준일: 2026-09-24. 사용자는 주로 Client를 담당하며 두 영역의 변경을 별도 브랜치와 PR로 관리한다.

| 브랜치 | 작업 범위 | 현재 상태 |
|---|---|---|
| `feat/phase2-client` | `src/client/`, `tests/client/`, Client 미리보기/문서 | Client 구현 완료, Draft PR #2에서 검토 및 후속 작업 |
| `feat/phase2-backend` | `src/backend/`, `tests/backend/`, Backend 통합 테스트/문서 | 개발 시작용 브랜치. Windows 감지 및 endpoint 미구현 |

두 브랜치는 Phase 1 완료 main (`efafd8e489ef87e42679495ad675c27261feccb5`)에서 분기한다.
Backend 브랜치는 Client 구현 전체를 포함하지 않으며, Client의 `33792af4113c59c1446874bc3cd4e78fe87518e9`에서
아래 두 공통 파일만 내용 변경 없이 가져왔다.

- `src/shared/activity.py`
- `docs/dev/current-activity-api.md`

Backend 브랜치의 README와 기존 Phase 체크리스트는 분기 시점의 main 상태이다.
Client의 현재 진행 상태와 검증 결과는 [Client PR #2](https://github.com/rkdduswns/AICapstone/pull/2)를 기준으로 확인한다.
이 준비 커밋은 Backend 기능 구현이나 Phase 2 완료를 의미하지 않는다.

## 작업 원칙

1. Client UI와 Backend 감지를 각 담당 브랜치에서 수정한다. 동일 파일의 동시 편집은 피한다.
2. `src/shared/`와 API 규격은 공동 계약이다. 필드/상태 변경은 먼저 양쪽 영향과 변경 내용을 합의하고,
   하나의 PR에서 변경한 뒤 다른 브랜치에도 동일한 변경을 반영한다. 각자 다른 규격으로 수정하지 않는다.
3. Phase 전체 체크리스트는 Client PR #2의 상태를 먼저 기준으로 사용하고,
   Backend 구현 결과는 별도 보고서에 기록한다. 통합 시 전체 체크리스트를 갱신한다.
4. Client는 가상 데이터 미리보기로 계속 작업할 수 있다. Backend는 API/감지 테스트로 독립 검증한다.
5. 각 영역은 별도 PR로 `main`에 병합한다. Client PR을 먼저 반영하고 Backend 브랜치에 최신 main을 병합하면
   실제 Client로 통합 검증할 수 있다. 공통 파일은 같은 초기 내용이므로 이후 변경이 없다면 중복 추가가 충돌하지 않는다.
6. 두 PR의 검토·테스트와 실제 Windows 창 전환 검증을 마친 뒤 Phase 2를 완료 처리한다.
   main 병합은 별도 검토를 거치며 브랜치 생성만으로 수행하지 않는다.

## 로컬 전환

먼저 현재 변경을 커밋하거나 임시 보관한다. 한 작업 폴더에서는 한 브랜치만 활성화된다.

Client 작업:

```powershell
git fetch origin
git switch feat/phase2-client
```

Backend 작업을 처음 시작할 때:

```powershell
git fetch origin
git switch --track origin/feat/phase2-backend
```

다른 팀원은 자신의 clone에서 Backend 브랜치를 사용하면 된다.
한 PC에서 둘을 동시에 실행·편집해야 할 때만 별도 worktree를 만들고 각 작업 폴더의 가상환경을 따로 사용한다.
