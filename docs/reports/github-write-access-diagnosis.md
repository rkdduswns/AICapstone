# GitHub 쓰기 권한 복구 기록

## 증상

ChatGPT의 GitHub 연결로 브랜치를 생성할 때 `403: Resource not accessible by integration` 오류가 발생했다. 계정의 저장소 권한은 admin/push가 모두 true였으며 main은 보호되지 않았고 ruleset 목록도 비어 있었다.

## 확인된 원인과 조치

계정은 `rkdduswns`로 저장소 소유자와 일치했다. GitHub의 Authorized GitHub Apps에는 ChatGPT Codex Connector가 있었으나 Installed GitHub Apps는 비어 있었고, 연결의 설치 목록 조회도 빈 목록을 반환했다.

사용자가 ChatGPT Codex Connector 설치를 완료한 뒤 설치 목록에 rkdduswns 계정이 나타났고, 동일한 연결을 통한 브랜치 생성이 성공했다. 이번 장애는 저장소에 대한 앱 설치 누락과 관련된 쓰기 권한 문제로 확인되었다.

## 검증 범위

- 기준 main: `942cc2c5ce96cd4142837ef4a0c852727af661c6`
- 복구 후 `chore/github-write-diagnosis` 브랜치 생성 성공
- 이 문서는 해당 브랜치에서 Contents API로 생성하며, 성공 시 파일 작성과 원격 커밋 생성까지 검증된다.
- main 및 기존 기획/코드는 변경하지 않는다.
- 이전 Phase1 로컬 산출물의 복구나 업로드는 이 검증에 포함되지 않는다.

## 재발 시 확인 순서

1. 연결된 GitHub 사용자명이 저장소 접근 계정과 일치하는지 확인한다.
2. GitHub Settings → Applications → Installed GitHub Apps에서 앱 설치 및 대상 저장소 접근 범위를 확인한다.
3. 계정의 push 권한과 별개로 앱에 Contents 쓰기 권한이 있는지 확인한다.
4. 브랜치 생성 및 파일 커밋 후 원격 브랜치/파일을 다시 읽어 실제 반영을 확인한다.

ChatGPT의 액션 승인 설정과 GitHub의 앱 권한은 별개다. GitHub Developer settings의 GitHub Apps 목록은 직접 개발한 앱을 관리하는 화면이므로 설치 여부 확인에 사용하지 않는다.
