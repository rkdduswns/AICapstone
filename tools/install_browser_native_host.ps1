<#
설치된 실제 Native Messaging host의 경로만 등록한다. 인증·토큰 발급은 구현하지 않는다.
Chrome/Edge별 확장 ID를 명시하며 사용자별 HKCU에만 등록한다.
Windows PowerShell 5.1의 한국어 처리를 위해 이 스크립트는 UTF-8 BOM으로 보관한다.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Install', 'Check', 'Uninstall')][string]$Action = 'Install',
    [ValidateSet('Chrome', 'Edge')][string]$Browser = 'Chrome',
    [string[]]$ExtensionId,
    [string]$HostPath,
    [string]$ManifestDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-GangSearchPlainPath {
    param([string]$Path)
    # 상위 디렉터리까지 검사해 연결 경로의 다른 파일을 덮어쓰거나 지우지 않는다.
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw '연결된 경로 대신 파일과 폴더의 실제 경로를 지정해 주세요.'
            }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
}

function Get-GangSearchHostPath {
    param([string]$Path)
    # .py 파일이나 GUI 앱을 자동으로 wrapper/인증 host로 변환하지 않는다.
    $file = Get-Item -LiteralPath $Path -Force
    if ($file.PSIsContainer -or $file.Extension.ToLowerInvariant() -notin @('.exe', '.cmd', '.bat')) {
        throw '실제 Native Messaging host 실행 파일(.exe/.cmd/.bat)을 지정해 주세요.'
    }
    if ($file.Name -in @('강써치.exe', '강써치-Client.exe', '강써치-Backend.exe')) {
        throw '현재 강써치 GUI/서버 EXE는 인증 host가 아닙니다. 별도 Native Messaging host를 지정해 주세요.'
    }
    Assert-GangSearchPlainPath $file.FullName
    return $file.FullName
}

function Get-GangSearchRegistryPath {
    param([string]$Browser)
    $vendor = if ($Browser -eq 'Chrome') { 'Google\Chrome' } else { 'Microsoft\Edge' }
    return "Software\$vendor\NativeMessagingHosts\com.contexttrace.auth"
}

function Get-GangSearchRegistrations {
    param([string]$Browser)
    # 두 뷰를 함께 관리해 기존 32비트 등록이 새 설치를 가리는 문제를 막는다.
    $views = if ([Environment]::Is64BitOperatingSystem) { @('Registry32', 'Registry64') } else { @('Default') }
    foreach ($view in $views) {
        $hive = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $view)
        $key = $null
        try {
            $key = $hive.OpenSubKey((Get-GangSearchRegistryPath $Browser))
            $hasValue = $null -ne $key -and $key.GetValueNames() -contains ''
            [pscustomobject]@{
                View = $view
                HasValue = $hasValue
                Value = if ($hasValue) { $key.GetValue('', $null, 'DoNotExpandEnvironmentNames') } else { $null }
                Kind = if ($hasValue) { $key.GetValueKind('') } else { [Microsoft.Win32.RegistryValueKind]::String }
            }
        } finally {
            if ($null -ne $key) { $key.Dispose() }
            $hive.Dispose()
        }
    }
}

function Set-GangSearchRegistration {
    param([string]$Browser, [string]$View, [object]$Value,
        [Microsoft.Win32.RegistryValueKind]$Kind = [Microsoft.Win32.RegistryValueKind]::String)
    # 이름이 고정된 앱 키의 기본값만 기록한다. 관리자 권한/HKLM은 사용하지 않는다.
    $hive = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $View)
    $key = $null
    try {
        $key = $hive.CreateSubKey((Get-GangSearchRegistryPath $Browser))
        $key.SetValue('', $Value, $Kind)
    } finally {
        if ($null -ne $key) { $key.Dispose() }
        $hive.Dispose()
    }
}

function Remove-GangSearchRegistration {
    param([string]$Browser, [string]$View)
    # 기본값만 제거하고 다른 값·하위 키·브라우저 사용자 데이터는 건드리지 않는다.
    $hive = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $View)
    $key = $null
    try {
        $key = $hive.OpenSubKey((Get-GangSearchRegistryPath $Browser), $true)
        if ($null -ne $key) { $key.DeleteValue('', $false) }
    } finally {
        if ($null -ne $key) { $key.Dispose() }
        $hive.Dispose()
    }
}

function Invoke-GangSearchNativeHost {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [ValidateSet('Install', 'Check', 'Uninstall')][string]$Action = 'Install',
        [ValidateSet('Chrome', 'Edge')][string]$Browser = 'Chrome',
        [string[]]$ExtensionId,
        [string]$HostPath,
        [string]$ManifestDirectory
    )
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw '이 등록 도구는 Windows에서만 실행합니다.'
    }
    $Browser = if ($Browser -eq 'Chrome') { 'Chrome' } else { 'Edge' }
    if (@($ExtensionId | Where-Object { $_ -cnotmatch '^[a-p]{32}$' }).Count) {
        throw '확장 ID는 a~p 소문자 32자로 지정해 주세요.'
    }
    $ids = @($ExtensionId | Sort-Object -Unique)
    if (-not $ManifestDirectory) {
        if (-not $env:LOCALAPPDATA) { throw '사용자 LOCALAPPDATA 경로를 확인할 수 없습니다.' }
        $ManifestDirectory = Join-Path $env:LOCALAPPDATA "GangSearch\NativeMessagingHosts\$Browser"
    }
    $directory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ManifestDirectory)
    Assert-GangSearchPlainPath $directory
    if ((Test-Path -LiteralPath $directory) -and -not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw '설정 파일을 저장할 폴더 경로를 지정해 주세요.'
    }
    $manifest = Join-Path $directory 'com.contexttrace.auth.json'
    Assert-GangSearchPlainPath $manifest
    $registrations = @(Get-GangSearchRegistrations $Browser)
    [byte[]]$previous = $null
    if (Test-Path -LiteralPath $manifest -PathType Leaf) { $previous = [IO.File]::ReadAllBytes($manifest) }
    $saved = $null
    if ($null -ne $previous) {
        # 다른 도구가 만든 동명 파일을 이 도구의 설치/제거 대상으로 간주하지 않는다.
        $saved = [Text.Encoding]::UTF8.GetString($previous).TrimStart([char]0xFEFF) | ConvertFrom-Json
        if ($saved.name -ne 'com.contexttrace.auth' -or $saved.type -ne 'stdio' -or
            $saved.description -ne 'GangSearch browser authentication host (generated)') {
            throw '이 도구가 생성하지 않은 기존 설정 파일은 변경하지 않습니다.'
        }
    }
    $resolvedHost = if ($HostPath) { Get-GangSearchHostPath $HostPath } else { $null }
    if ($Action -eq 'Install') {
        if (-not $resolvedHost -or $ids.Count -eq 0) {
            throw '설치에는 실제 HostPath와 ExtensionId를 함께 지정해 주세요.'
        }
        foreach ($entry in $registrations) {
            if ($entry.HasValue -and ($entry.Kind -ne 'String' -or $entry.Value -ine $manifest)) {
                throw '다른 위치를 가리키는 기존 등록은 변경하지 않습니다.'
            }
        }
    } elseif ($Action -eq 'Check') {
        if ($null -eq $saved) { throw '등록된 설정 파일이 없습니다.' }
        $actualHost = Get-GangSearchHostPath $saved.path
        if (-not [IO.Path]::IsPathRooted($saved.path) -or $actualHost -cne $saved.path) {
            throw '설정의 host 경로가 실제 절대 경로와 일치하지 않습니다.'
        }
        if ($resolvedHost -and $resolvedHost -ine $actualHost) { throw '요청한 host 경로와 설정이 다릅니다.' }
        $resolvedHost = $actualHost
        $actualOrigins = @($saved.allowed_origins)
        if ($actualOrigins.Count -eq 0 -or @($actualOrigins | Where-Object {
            $_ -cnotmatch '^chrome-extension://[a-p]{32}/$'
        }).Count) { throw '설정의 허용 확장 ID가 올바르지 않습니다.' }
        $actualIds = @($actualOrigins | ForEach-Object { $_.Substring(19, 32) } | Sort-Object -Unique)
        if ($ids.Count -and @((Compare-Object $ids $actualIds)).Count) { throw '요청한 확장 ID와 설정이 다릅니다.' }
        $ids = $actualIds
        foreach ($entry in $registrations) {
            if (-not $entry.HasValue -or $entry.Kind -ne 'String' -or $entry.Value -ine $manifest) {
                throw '브라우저 레지스트리와 설정 파일의 절대 경로가 일치하지 않습니다.'
            }
        }
    } else {
        # 다른 위치로 변경된 등록은 삭제하지 않으며 설정 파일만 남겨 오해시키지도 않는다.
        foreach ($entry in $registrations) {
            if ($entry.HasValue -and ($entry.Kind -ne 'String' -or $entry.Value -ine $manifest)) {
                throw '다른 위치를 가리키는 기존 등록은 제거하지 않습니다.'
            }
        }
        if ($null -ne $saved) { $resolvedHost = $saved.path }
    }
    $result = [ordered]@{ ok = $true; action = $Action; browser = $Browser; manifest = $manifest;
        path = $resolvedHost; extension_ids = $ids; changed = $false; configuration_only = $true }
    if ($Action -eq 'Check' -or -not $PSCmdlet.ShouldProcess($manifest, "$Action $Browser Native Messaging 등록")) {
        return [pscustomobject]$result
    }
    $staging = Join-Path $directory ('.native-host-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        if ($Action -eq 'Install') {
            [IO.Directory]::CreateDirectory($directory) | Out-Null
            $contents = [ordered]@{ name = 'com.contexttrace.auth'; description = 'GangSearch browser authentication host (generated)';
                path = $resolvedHost; type = 'stdio'; allowed_origins = @($ids | ForEach-Object { "chrome-extension://$_/" }) }
            [IO.File]::WriteAllText($staging, ($contents | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
            if ($null -ne $previous) { [IO.File]::Replace($staging, $manifest, [NullString]::Value) }
            else { [IO.File]::Move($staging, $manifest) }
            foreach ($entry in $registrations) { Set-GangSearchRegistration -Browser $Browser -View $entry.View -Value $manifest }
        } else {
            foreach ($entry in $registrations) { Remove-GangSearchRegistration -Browser $Browser -View $entry.View }
            if ($null -ne $previous) { [IO.File]::Delete($manifest) }
        }
        $result.changed = $Action -eq 'Install' -or $null -ne $previous -or @($registrations | Where-Object HasValue).Count -gt 0
    } catch {
        # 중간 실패 시 이전 기본값과 JSON을 복원한다. host·토큰·DB는 읽거나 수정하지 않는다.
        $failure = $_
        try {
            if ($null -ne $previous) { [IO.File]::WriteAllBytes($manifest, $previous) }
            elseif (Test-Path -LiteralPath $manifest -PathType Leaf) { [IO.File]::Delete($manifest) }
            foreach ($entry in $registrations) {
                if ($entry.HasValue) { Set-GangSearchRegistration -Browser $Browser -View $entry.View -Value $entry.Value -Kind $entry.Kind }
                else { Remove-GangSearchRegistration -Browser $Browser -View $entry.View }
            }
        } catch { throw "설정 복구를 확인해 주세요. 원래 오류: $($failure.Exception.Message); 복구 오류: $($_.Exception.Message)" }
        throw $failure
    } finally {
        if (Test-Path -LiteralPath $staging -PathType Leaf) { [IO.File]::Delete($staging) }
    }
    return [pscustomobject]$result
}

# dot-source는 함수만 제공한다. 테스트는 레지스트리 helper만 대체해 실제 사용자 등록을 보존한다.
if ($MyInvocation.InvocationName -ne '.') {
    try {
        Invoke-GangSearchNativeHost @PSBoundParameters | ConvertTo-Json -Depth 5 -Compress
    } catch {
        [pscustomobject]@{ ok = $false; action = $Action; browser = $Browser; error = $_.Exception.Message } |
            ConvertTo-Json -Compress
        exit 1
    }
}
