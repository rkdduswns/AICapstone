# 브라우저 Native Messaging 설치 경로

## 목적과 현재 범위

2026-11-20 (KST) `feat/browser-native-installation`의 작은 설치 준비 단계다.
설치 PC의 실제 호스트 위치와 Chrome/Edge 확장 ID로 설정을 생성·등록한다.
개발자 PC의 절대 경로를 저장소나 배포 ZIP에 넣지 않는다.

확인한 최신 원격은 `main 7e0991e`, `client_dev b6ef84b`,
`feat/phase10-backend c95b440`이다. `c95b440`은 검색·임베딩 Backend 구현이지만
`src/browser`에는 `.gitkeep`만 있고 Native Messaging 호스트·설치 스크립트는 없다.
공유받은 새 인증 기능의 커밋은 아직 확인하지 못했다. 현재 확장은 수동 Bearer 토큰 방식이다.
이 단계는 새 인증 프로토콜이나 Backend API·DB를 추정하여 바꾸지 않는다.

현재 `강써치.exe`는 UI/Backend 실행 파일이며 Native Messaging 호스트 역할이 없다.
이 EXE를 인증 호스트로 등록하지 않는다. 아래 도구는 **실제 인증 호스트가 제공된 뒤** 사용한다.
설정 등록 성공은 토큰 교환·브라우저 수집·검색 성공을 의미하지 않는다.

## 설치 방식

선행조건은 실제 `com.contexttrace.auth` 호스트 실행 파일 또는 실행 래퍼와
설치한 확장의 ID다. `.py`만으로는 Windows에서 직접 실행할 수 없으므로
호스트 담당자가 실행 가능한 `.exe`/`.cmd`/`.bat`를 제공해야 한다.
호스트 이름은 확장의 `sendNativeMessage`/`connectNative`와 같아야 한다.
호스트 통신은 브라우저가 요구하는 길이 접두사·UTF-8 JSON·표준 입출력 규격을 따라야 한다.

등록 도구는 `tools/install_browser_native_host.ps1`이다.
ZIP에는 같은 이름의 스크립트와 이 문서의 사본 `NATIVE-MESSAGING.md`를 포함한다.
사용자 설치 프로그램을 만들 때 호스트 파일 배치 후 이 도구를 호출하면 된다.
실행할 호스트는 설치 프로그램이 확정한 실제 경로를 넘긴다.
PyInstaller의 임시 압축 해제 경로를 영구 설치 위치로 사용하지 않는다.

Chrome과 Edge는 각자 설치된 확장 ID로 따로 등록한다.
팀 공통 ID를 정하지 않아도 개발 PC별 설치를 진행할 수 있다.
공통 배포 ID가 확정되면 설치 프로그램에서 그 값을 넘긴다. ID를 추정하거나 와일드카드로 허용하지 않는다.

```powershell
# 저장소 루트 기준. 호스트·확장 ID는 실제 설치 값을 사용한다.
$nativeHost = "C:\설치한 강써치\인증 호스트\auth-host.exe"
$chromeExtensionId = "실제_Chrome_확장_ID"
& .\tools\install_browser_native_host.ps1 -Action Install -Browser Chrome `
  -HostPath $nativeHost -ExtensionId $chromeExtensionId -WhatIf

# 계획을 확인한 뒤 실제 등록한다. 관리자 권한은 사용하지 않는다.
& .\tools\install_browser_native_host.ps1 -Action Install -Browser Chrome `
  -HostPath $nativeHost -ExtensionId $chromeExtensionId

# 현재 등록·설정·호스트 파일 존재 여부를 읽기 전용으로 확인한다.
& .\tools\install_browser_native_host.ps1 -Action Check -Browser Chrome

# Edge는 -Browser Edge와 해당 확장 ID로 별도 실행한다.
# 제거 시 실제 호스트 파일이나 사용자 DB·본문은 삭제하지 않는다.
& .\tools\install_browser_native_host.ps1 -Action Uninstall -Browser Chrome
```

실제 파일이 없는 경로, 잘못된 확장 ID와 다른 프로그램의 설정은 등록 전에 거부한다.
한글·공백이 있는 실제 절대 경로를 JSON으로 직렬화한다.
생성 파일은 기본적으로 `%LOCALAPPDATA%\GangSearch\NativeMessagingHosts\Chrome\com.contexttrace.auth.json`
또는 `Edge` 하위에 두며 UTF-8 BOM 없이 기록한다.
스크립트 자체는 Windows PowerShell 5.1의 한글 처리를 위해 UTF-8 BOM을 사용한다.
현재 사용자(HKCU)의 브라우저별 `NativeMessagingHosts\com.contexttrace.auth` 기본값만 등록한다.
등록 도중 실패하면 기존 설정을 복원한다. 재설치·경로 이동은 새 위치로 다시 등록하고 `Check`한다.
생성 JSON은 `.gitignore`로 제외하며, 토큰이나 개인 경로를 공유 문서에 붙여 넣지 않는다.

근거: [Chrome Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging),
[Edge Native Messaging](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/native-messaging).

## 현재 확장 호환 처리

브라우저 수집 요청은 데스크톱 Client가 아닌 `src/browser/extension`에서 수행한다.
현재 코드의 `/browser/source`는 현재 활성 작업에서 받은 `record_id`를 보내며,
`/browser/content`는 출처 ID·본문·`truncated`를 전송한다.
새 `context_id` 전환과 Native Messaging 인증은 서버의 실제 수신 계약을 확인한 뒤 연결한다.
가장 최근 작업을 임의로 찾아 연결하거나 토큰 검사를 제거하지 않는다.

이 단계는 기존 응답 검증도 보완한다.
최종 연결 작업 ID는 실제 양수 SQLite ID인지 확인하되, URL 이동으로 서버가 새 세션을 만든 경우는 허용한다.
본문 저장 응답은 유효한 저장 ID와 요청한 출처 ID가 확인된 경우만 성공으로 안내한다.
401·403은 응답 JSON 모양과 무관하게 실패이며 자동 재전송하지 않는다.
출처가 연결된 뒤 본문 응답만 확인할 수 없으면 전체 성공으로 표시하지 않는다.

본문 수집은 사용자 버튼으로 실행한 현재 HTTP(S) 탭에 한정한다.
일시정지·다른 앱 상태에서는 DOM을 읽기 전에 중단한다.
표시 본문 `main/article`, 없으면 `body`를 사용하며 최대 100,000 UTF-16 단위와
`truncated` 표시를 유지한다. 자동 탭 수집·URL 차단·민감정보 저장 동의는 추가하지 않는다.

## 검증과 완료 조건

이 단계의 완료 조건은 PC 경로를 하드코딩하지 않는 설정 생성·등록·조회·제거 도구,
배포 ZIP 포함과 기존 확장의 응답 검증이다.
테스트는 한글·공백 경로, 잘못된 ID/경로, 재설치, 실패 복구, 다른 설정 보존,
읽기 전용 확인과 안전한 제거를 가상 호스트·격리된 등록 저장소로 확인한다.
검증에서 실제 Chrome/Edge 등록 정보나 사용자 토큰을 변경하지 않는다.

2026-11-20 Windows Python 3.14.7에서 관련 Python 검증 **194 passed**,
Node 확장 검증 **20 passed**, Ruff·공백·문서 링크 검사를 통과했다.
Python 실행에는 설치 검증 **37개**, 패키징 검증 **44개**와 기존 실제 HTTP·SQLite·Client 회귀를 포함한다.
설치 검증은 Windows PowerShell 5.1을 실제로 실행한다. 레지스트리 쓰기 함수도 고유 임시 키에서
기본값 등록·제거와 다른 값 보존을 확인했으며, 실제 브라우저 등록은 변경하지 않았다.
PowerShell 5.1의 설정 갱신 인수 오류와 다른 설치 등록을 덮어쓸 수 있던 문제는 수정 후 검증했다.
개인 설정 JSON이 배포 폴더·ZIP에 남아 있으면 빌드·검증을 중단한다.

아직 확인할 항목:

- 새 인증 호스트·확장·설치 스크립트의 실제 커밋과 메시지/토큰 계약.
- 호스트를 설치 위치에 배치하는 최종 설치 프로그램의 호출 연결.
- Chrome/Edge가 실제 호스트를 시작하고 인증이 성공/실패하는지.
- 실제 활성 브라우저에서 출처 → 본문 → Backend 저장 → Client 조회.
- 개인정보 거부 시 본문·검색 색인에 남지 않는지와 수집 잘림의 서버 보존.
- 웹·문서 색인·임베딩·삭제 구현을 현재 보호·출처 계약과 합류하는 별도 Backend 검증.

Phase 7·8·10·14의 전체 완료 표시는 바꾸지 않는다.
기존 [실제 연결 안내](history-source-linking.md)와 [Backend 통합 설계](backend-integration-plan.md)를 함께 따른다.
