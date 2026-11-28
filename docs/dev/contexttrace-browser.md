# ContextTrace Chrome 커넥터 (소스 설치용)

| 구현 | 수집 시점과 인증 | 배포 |
|---|---|---|
| [강써치 페이지 연결](../../src/browser/extension) | 허용한 사이트의 현재 페이지 주소·제목을 자동 연결한다. 본문은 수동 옵션에서 연결한다. 팝업의 **연결 토큰**을 사용한다. | Windows ZIP의 `browser-extension`. [설치 및 사용](history-source-linking.md) |
| [ContextTrace](../../src/browser/contexttrace) | 활성 HTTP(S) 페이지를 로드할 때 출처·본문을 전송한다. Chrome이 로컬 Native Messaging 호스트에 토큰을 요청한다. | 소스 전용. Windows ZIP에 포함하지 않는다. |

두 확장의 권한과 수집 시점이 다르므로 같은 확장의 두 설치 단계로 취급하지 않는다.
확장과 네이티브 호스트는 실행 중에도 필요한 프로그램이므로 `src/browser/`에 두고,
Windows에서 한 번 실행하는 등록 스크립트는 `tools/`에 둔다.

## 기존 루트 browser/ 설치를 옮기는 경우

1. 기존 ContextTrace 확장을 비활성화한다. Chrome의 확장 관리 화면에서 개발자 모드를 켜고
   새 폴더 `src/browser/contexttrace/extension`을 **압축해제된 확장 프로그램 로드**로 선택한다.
2. 새로 표시된 확장 ID를 복사한다. 경로가 달라졌으므로 예전 ID를 그대로 가정하지 않는다.
3. Windows PowerShell에서 저장소 루트를 기준으로 아래 명령을 실행한다.
   호스트를 실행하려면 Windows에서 Python 3을 사용할 수 있어야 한다.

   ```powershell
   .\tools\setup_chrome.ps1 -ExtensionId '여기에_새_확장_ID'
   ```

4. 등록 스크립트는 새 호스트 폴더에 매니페스트를 생성하고 현재 사용자 Chrome 레지스트리 항목을
   갱신한다. Chrome을 다시 시작한다. 이전 확장은 제거해도 된다.

Windows ZIP의 확장을 쓰는 사용자는 이 이전·재등록 절차를 수행할 필요가 없다.

## 인증 상태와 확인 범위

ContextTrace 호스트는 현재 사용자의 `%USERPROFILE%\.contexttrace\browser-token` 파일을 읽는다.
이 통합 브랜치의 [Backend](../../src/backend/app.py)는 브라우저 API 인증에 환경변수
`GANGSEARCH_BROWSER_TOKEN`(미지정 시 `CONTEXTTRACE_BROWSER_TOKEN`)을 사용한다.
파일 생성 [함수](../../src/backend/browser_auth.py)는 있지만 기본 실행 경로에서 호출하지 않는다.
따라서 Backend를 시작하거나 확장 ID를 등록하는 것만으로 양쪽 토큰이 준비되지는 않는다.
이 경로 정리는 인증 방식을 변경하지 않으며, Windows Chrome에서 자동 수집 성공을 검증한 것은 아니다.

등록을 해제하려면 ContextTrace 확장을 제거한 뒤 PowerShell에서 다음을 실행한다.

```powershell
Remove-Item 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.contexttrace.auth' -Recurse -Force
```
