"""실제 PowerShell 파일 처리와 격리한 등록 상태로 브라우저 설치 경계를 검증한다."""

import base64
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/install_browser_native_host.ps1"
POWERSHELL = shutil.which("powershell.exe") if sys.platform == "win32" else None
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell 전용 검증")
ID_A = "a" * 32
ID_B = "b" * 32


def ps_literal(value):
    """인자 자료를 PowerShell 단일 인용 문자열로 전달해 경로를 코드로 실행하지 않는다."""
    return "'" + str(value).replace("'", "''") + "'"


def run_powershell(body, *, check=True):
    """UTF-16 명령과 UTF-8 결과로 한글 경로를 유지하고 실제 사용자 등록은 건드리지 않는다."""
    prefix = """[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
"""
    encoded = base64.b64encode((prefix + body).encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        capture_output=True, encoding="utf-8", errors="replace", timeout=35,
    )
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def result_json(result):
    """ShouldProcess 안내와 분리한 최종 테스트 결과만 읽는다."""
    lines = [line.removeprefix("RESULT:") for line in result.stdout.splitlines()
             if line.startswith("RESULT:")]
    assert len(lines) == 1, result.stdout + result.stderr
    return json.loads(lines[0])


def isolated(body):
    """등록 I/O 세 함수만 대체하며 실제 설치·검사·파일 쓰기·복구 코드를 실행한다.

    임의 레지스트리 경로를 받는 실행 옵션을 제품에 추가하지 않는다. dot-source로 읽은
    함수의 등록 경계만 메모리로 바꾸므로 사용자의 Chrome/Edge 설정은 읽거나 쓰지 않는다.
    """
    return run_powershell(f". {ps_literal(SCRIPT)}\n" + r"""
$script:registrationState = @{Registry32=$null; Registry64=$null}
$script:registryWrites = 0
$script:failView = $null
$script:failurePending = $false
function Get-GangSearchRegistrations {
    param([string]$Browser)
    foreach ($view in @('Registry32', 'Registry64')) {
        $item = $script:registrationState[$view]
        [pscustomobject]@{View=$view; HasValue=($null -ne $item)
            Value=$(if ($null -ne $item) {$item.Value} else {$null})
            Kind=$(if ($null -ne $item) {$item.Kind} else {
                [Microsoft.Win32.RegistryValueKind]::String})}
    }
}
function Set-GangSearchRegistration {
    param([string]$Browser, [string]$View, [object]$Value,
          [Microsoft.Win32.RegistryValueKind]$Kind = 'String')
    $script:registryWrites++
    if ($script:failurePending -and $View -eq $script:failView) {
        $script:failurePending = $false
        throw 'synthetic registry failure'
    }
    $script:registrationState[$View] = [pscustomobject]@{Value=$Value; Kind=$Kind}
}
function Remove-GangSearchRegistration {
    param([string]$Browser, [string]$View)
    $script:registryWrites++
    $script:registrationState[$View] = $null
}
""" + body)


def report(expression):
    """검증할 객체 하나를 충분한 깊이로 직렬화한다."""
    return f"'RESULT:' + (ConvertTo-Json -InputObject ({expression}) -Depth 12 -Compress)"


@pytest.fixture
def host_paths(tmp_path):
    """실행하지 않는 호스트와 한글·공백·작은따옴표가 있는 설치 경로를 준비한다."""
    root = tmp_path / "한글 설치 '자료"
    root.mkdir()
    host = root / "native host.cmd"
    host.write_text("@exit /b 91\n", encoding="ascii")
    return host, root / "생성 설정"


def invoke_arguments(host, directory, *, browser="Chrome", ids=(ID_A,)):
    """명시한 자료만 설치 함수에 전달한다."""
    extensions = ",".join(ps_literal(item) for item in ids)
    return (f"-Browser {browser} -HostPath {ps_literal(host)} "
            f"-ManifestDirectory {ps_literal(directory)} -ExtensionId @({extensions})")


def test_script_parses_in_windows_powershell():
    """Windows 기본 PowerShell에서 배포 스크립트 구문을 먼저 검사한다."""
    result = run_powershell(f"""
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    {ps_literal(SCRIPT)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{throw ($errors | Out-String)}}
""" + report("@{errors=$errors.Count}"))
    assert result_json(result) == {"errors": 0}


@pytest.mark.parametrize("browser", ["Chrome", "Edge"])
def test_default_manifest_directory_is_per_user_and_browser(host_paths, browser):
    """설치 위치와 브라우저가 달라도 개발자 PC 경로를 재사용하지 않는다."""
    host, directory = host_paths
    result = isolated(f"""
$env:LOCALAPPDATA={ps_literal(directory)}
$plan=Invoke-GangSearchNativeHost -Action Install -Browser {browser} `
    -HostPath {ps_literal(host)} -ExtensionId {ps_literal(ID_A)} -WhatIf
""" + report("@{plan=$plan; writes=$script:registryWrites}"))
    data = result_json(result)
    expected = directory / "GangSearch" / "NativeMessagingHosts" / browser
    assert data["plan"]["manifest"] == str(expected / "com.contexttrace.auth.json")
    assert data["writes"] == 0
    assert not directory.exists()


@pytest.mark.parametrize("browser", ["Chrome", "Edge"])
def test_whatif_plans_unicode_manifest_without_writes(host_paths, browser):
    """미리보기는 등록·폴더 생성 없이 실제 경로와 명시한 ID만 계획한다."""
    host, directory = host_paths
    result = isolated(
        f"$plan=Invoke-GangSearchNativeHost -Action Install "
        f"{invoke_arguments(host, directory, browser=browser, ids=(ID_B, ID_A, ID_A))} -WhatIf\n"
        + report("@{plan=$plan; writes=$script:registryWrites}")
    )
    data = result_json(result)
    assert data["writes"] == 0
    assert data["plan"]["path"] == str(host.resolve())
    assert sorted(data["plan"]["extension_ids"]) == [ID_A, ID_B]
    assert data["plan"]["configuration_only"] is True
    assert not directory.exists()
    assert host.read_text(encoding="ascii") == "@exit /b 91\n"


@pytest.mark.parametrize("browser", ["Chrome", "Edge"])
def test_install_check_update_uninstall_preserves_host(host_paths, browser):
    """생성·양쪽 등록·검사·다른 ID/이동 경로 갱신·해제까지 파일 경계를 확인한다."""
    host, directory = host_paths
    moved = host.with_name("이동한 host.cmd")
    moved.write_text("@exit /b 92\n", encoding="ascii")
    first = invoke_arguments(host, directory, browser=browser)
    second = invoke_arguments(moved, directory, browser=browser, ids=(ID_B,))
    result = isolated(f"""
$installed=Invoke-GangSearchNativeHost -Action Install {first}
$manifest=Get-Content -LiteralPath $installed.manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$bytes=[System.IO.File]::ReadAllBytes($installed.manifest)
$checked=Invoke-GangSearchNativeHost -Action Check {first}
$updated=Invoke-GangSearchNativeHost -Action Install {second}
$current=Get-Content -LiteralPath $updated.manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$registrations=@(Get-GangSearchRegistrations -Browser {browser})
$removed=Invoke-GangSearchNativeHost -Action Uninstall {second}
""" + report("@{installed=$installed; checked=$checked; manifest=$manifest; "
                 "prefix=@($bytes | Select-Object -First 3); updated=$updated; "
                 "current=$current; registrations=$registrations; removed=$removed; "
                 "remaining=@(Get-GangSearchRegistrations -Browser '" + browser + "') }"))
    data = result_json(result)
    assert data["installed"]["ok"] is True
    assert data["checked"]["ok"] is True
    assert data["updated"]["ok"] is True
    assert data["removed"]["ok"] is True
    assert data["manifest"] == {
        "name": "com.contexttrace.auth",
        "description": "GangSearch browser authentication host (generated)",
        "type": "stdio", "path": str(host.resolve()),
        "allowed_origins": [f"chrome-extension://{ID_A}/"],
    }
    assert data["prefix"] != [239, 187, 191]
    assert data["current"]["path"] == str(moved.resolve())
    assert data["current"]["allowed_origins"] == [f"chrome-extension://{ID_B}/"]
    assert {item["View"] for item in data["registrations"]} == {"Registry32", "Registry64"}
    assert all(item["Value"] == data["updated"]["manifest"]
               for item in data["registrations"])
    assert all(item["HasValue"] is False for item in data["remaining"])
    assert not Path(data["removed"]["manifest"]).exists()
    assert host.is_file() and moved.is_file()


@pytest.mark.parametrize("bad_id", ["a" * 31, "a" * 33, "q" * 32, "A" * 32,
                                        "*", "chrome-extension://" + ID_A + "/"])
def test_invalid_id_is_rejected_before_mutation(host_paths, bad_id):
    """확장 주소·와일드카드·허용 범위 밖 ID를 등록하지 않는다."""
    host, directory = host_paths
    result = isolated(f"""
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Install {
    invoke_arguments(host, directory, ids=(bad_id,))} | Out-Null}}
catch {{$rejected=$true}}
""" + report("@{rejected=$rejected; writes=$script:registryWrites}"))
    assert result_json(result) == {"rejected": True, "writes": 0}
    assert not directory.exists()


def test_case_insensitive_deduplication_cannot_hide_invalid_id(host_paths):
    """대소문자 중복 제거 전에 각 ID를 검증해 잘못된 주소가 유실되지 않게 한다."""
    host, directory = host_paths
    result = isolated(f"""
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Install {
    invoke_arguments(host, directory, ids=(ID_A, ID_A.upper()))} | Out-Null}}
catch {{$rejected=$true}}
""" + report("@{rejected=$rejected; writes=$script:registryWrites}"))
    assert result_json(result) == {"rejected": True, "writes": 0}
    assert not directory.exists()


@pytest.mark.parametrize("kind", ["missing", "python", "directory"])
def test_invalid_host_is_rejected_without_registration(host_paths, kind):
    """실행 파일이 없는 경로나 직접 실행 불가 Python 파일·폴더를 등록하지 않는다."""
    host, directory = host_paths
    bad = host.with_name("missing.exe")
    if kind == "python":
        bad = host.with_suffix(".py")
        bad.write_text("raise RuntimeError('must not run')", encoding="ascii")
    elif kind == "directory":
        bad = host.parent
    result = isolated(f"""
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Install {
    invoke_arguments(bad, directory)} | Out-Null}}
catch {{$rejected=$true}}
""" + report("@{rejected=$rejected; writes=$script:registryWrites}"))
    assert result_json(result) == {"rejected": True, "writes": 0}
    assert not directory.exists()


@pytest.mark.parametrize("name", ["강써치.exe", "강써치-Client.exe", "강써치-Backend.exe"])
def test_existing_gui_executable_is_not_registered_as_native_host(host_paths, name):
    """현재 배포 GUI의 이름을 인증 host로 바꿔 등록 완료로 오해시키지 않는다."""
    host, directory = host_paths
    gui = host.with_name(name)
    gui.write_bytes(b"MZsynthetic-do-not-run")
    result = isolated(f"""
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Install {
    invoke_arguments(gui, directory)} | Out-Null}}
catch {{$rejected=$true}}
""" + report("@{rejected=$rejected; writes=$script:registryWrites}"))
    assert result_json(result) == {"rejected": True, "writes": 0}
    assert not directory.exists()
    assert gui.read_bytes() == b"MZsynthetic-do-not-run"


@pytest.mark.parametrize("view", ["Registry32", "Registry64"])
@pytest.mark.parametrize("kind", ["String", "ExpandString", "DWord"])
def test_install_refuses_existing_foreign_registration(host_paths, view, kind):
    """한쪽 뷰의 다른 경로·자료형을 새 등록으로 덮어쓰지 않는다."""
    host, directory = host_paths
    value = "42" if kind == "DWord" else ps_literal(str(host.parent / "other.json"))
    result = isolated(f"""
$script:registrationState.{view}=[pscustomobject]@{{Value={value}
    Kind=[Microsoft.Win32.RegistryValueKind]::{kind}}}
$before=$script:registrationState.{view}.Value
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Install {
    invoke_arguments(host, directory)} | Out-Null}}
catch {{$rejected=$true}}
""" + report("@{rejected=$rejected; writes=$script:registryWrites; "
                 "preserved=($before -eq $script:registrationState." + view + ".Value)}"))
    assert result_json(result) == {"rejected": True, "writes": 0, "preserved": True}
    assert not directory.exists()


def test_check_is_readonly_and_detects_missing_registration(host_paths):
    """미등록 검사는 설정 폴더를 만들거나 문제를 자동으로 고치지 않는다."""
    host, directory = host_paths
    result = isolated(f"""
$rejected=$false
try {{$checked=Invoke-GangSearchNativeHost -Action Check {
    invoke_arguments(host, directory)}}}
catch {{$rejected=$true}}
""" + report("@{failed=($rejected -or -not $checked.ok); writes=$script:registryWrites}"))
    assert result_json(result) == {"failed": True, "writes": 0}
    assert not directory.exists()


@pytest.mark.parametrize("origins", [[], ["*"], [f"chrome-extension://{ID_A.upper()}/"], [ID_A]])
def test_check_rejects_invalid_origins_without_repair(host_paths, origins):
    """검사는 손상된 허용 대상을 자동 확대하거나 수정하지 않는다."""
    host, directory = host_paths
    encoded = ps_literal(json.dumps(origins))
    result = isolated(f"""
$installed=Invoke-GangSearchNativeHost -Action Install {invoke_arguments(host, directory)}
$saved=Get-Content -LiteralPath $installed.manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$saved.allowed_origins=@(ConvertFrom-Json {encoded})
[IO.File]::WriteAllText($installed.manifest, ($saved | ConvertTo-Json -Depth 5),
    [Text.UTF8Encoding]::new($false))
$previous=[Convert]::ToBase64String([IO.File]::ReadAllBytes($installed.manifest))
$before=$script:registryWrites
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Check {
    invoke_arguments(host, directory)} | Out-Null}}
catch {{$rejected=$true}}
$current=[Convert]::ToBase64String([IO.File]::ReadAllBytes($installed.manifest))
""" + report("@{rejected=$rejected; wrote=($before -ne $script:registryWrites); "
                 "same=($previous -eq $current)}"))
    assert result_json(result) == {"rejected": True, "wrote": False, "same": True}


def test_uninstall_whatif_preserves_manifest_and_registration(host_paths):
    """해제 미리보기 역시 파일과 양쪽 등록을 그대로 보존한다."""
    host, directory = host_paths
    arguments = invoke_arguments(host, directory)
    result = isolated(f"""
$installed=Invoke-GangSearchNativeHost -Action Install {arguments}
$previous=[Convert]::ToBase64String([IO.File]::ReadAllBytes($installed.manifest))
$before=$script:registryWrites
$plan=Invoke-GangSearchNativeHost -Action Uninstall {arguments} -WhatIf
$current=[Convert]::ToBase64String([IO.File]::ReadAllBytes($installed.manifest))
$checked=Invoke-GangSearchNativeHost -Action Check {arguments}
""" + report("@{plan=$plan; same=($previous -eq $current); "
                 "wrote=($before -ne $script:registryWrites); checked=$checked}"))
    data = result_json(result)
    assert data["plan"]["changed"] is False
    assert data["same"] is True and data["wrote"] is False
    assert data["checked"]["ok"] is True
    assert host.is_file()


def test_registry_failure_restores_previous_manifest_and_registrations(host_paths):
    """두 번째 등록 실패 시 이전 파일과 두 등록 값을 함께 복원한다."""
    host, directory = host_paths
    first = invoke_arguments(host, directory)
    second = invoke_arguments(host, directory, ids=(ID_B,))
    result = isolated(f"""
$installed=Invoke-GangSearchNativeHost -Action Install {first}
$previous=[System.Convert]::ToBase64String([System.IO.File]::ReadAllBytes($installed.manifest))
$script:failView='Registry64'
$script:failurePending=$true
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Install {second} | Out-Null}}
catch {{$rejected=$true}}
$current=[System.Convert]::ToBase64String([System.IO.File]::ReadAllBytes($installed.manifest))
$checked=Invoke-GangSearchNativeHost -Action Check {first}
""" + report("@{rejected=$rejected; previous=$previous; current=$current; checked=$checked; "
                 "failureReached=(-not $script:failurePending)}"))
    data = result_json(result)
    assert data["rejected"] is True
    assert data["failureReached"] is True
    assert data["previous"] == data["current"]
    assert data["checked"]["ok"] is True
    assert host.is_file()


@pytest.mark.parametrize("action", ["Install", "Uninstall"])
def test_unrelated_manifest_is_not_overwritten_or_deleted(host_paths, action):
    """같은 이름의 다른 설정 파일은 소유 확인 실패로 보존한다."""
    host, directory = host_paths
    directory.mkdir()
    manifest = directory / "com.contexttrace.auth.json"
    content = b'{"name":"another.application","path":"do-not-touch"}'
    manifest.write_bytes(content)
    result = isolated(f"""
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action {action} {
    invoke_arguments(host, directory)} | Out-Null}}
catch {{$rejected=$true}}
""" + report("@{rejected=$rejected; writes=$script:registryWrites}"))
    assert result_json(result) == {"rejected": True, "writes": 0}
    assert manifest.read_bytes() == content
    assert host.is_file()


def test_uninstall_refuses_different_registered_manifest(host_paths):
    """등록이 다른 위치를 가리키면 해제로 그 등록이나 파일을 지우지 않는다."""
    host, directory = host_paths
    arguments = invoke_arguments(host, directory)
    result = isolated(f"""
$installed=Invoke-GangSearchNativeHost -Action Install {arguments}
$other=Join-Path (Split-Path -Parent $installed.manifest) 'another.json'
$script:registrationState.Registry32=[pscustomobject]@{{Value=$other
    Kind=[Microsoft.Win32.RegistryValueKind]::String}}
$writesBefore=$script:registryWrites
$rejected=$false
try {{Invoke-GangSearchNativeHost -Action Uninstall {arguments} | Out-Null}}
catch {{$rejected=$true}}
""" + report("@{rejected=$rejected; wrote=($script:registryWrites -ne $writesBefore); "
                 "other=$other; registered=$script:registrationState.Registry32.Value; "
                 "manifest=$installed.manifest}"))
    data = result_json(result)
    assert data["rejected"] is True and data["wrote"] is False
    assert data["registered"] == data["other"]
    assert Path(data["manifest"]).is_file()
    assert host.is_file()


def test_actual_registry_helpers_use_isolated_leaf_and_preserve_named_values():
    """실제 등록 I/O는 브라우저 경로 대신 이 테스트만 만든 단일 잎 키에서 확인한다.

    등록 함수 자체는 대체하지 않는다. 경로 조회만 고유 테스트 키로 제한하고 finally에서
    그 키만 비재귀 삭제한다. 실제 Chrome/Edge 키와 다른 사용자의 키에는 접근하지 않는다.
    """
    test_key = "Software\\GangSearchNativeHostTest_" + uuid.uuid4().hex
    result = run_powershell(f". {ps_literal(SCRIPT)}\n" + f"""
$script:testRegistryPath={ps_literal(test_key)}
function Get-GangSearchRegistryPath {{param([string]$Browser); return $script:testRegistryPath}}
$views=@('Registry32', 'Registry64')
$ownedViews=@()
try {{
    foreach ($view in $views) {{
        $hive=[Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $view)
        try {{
            if ($null -ne $hive.OpenSubKey($script:testRegistryPath)) {{throw 'test key already exists'}}
        }} finally {{$hive.Dispose()}}
    }}
    foreach ($view in $views) {{
        Set-GangSearchRegistration -Browser Chrome -View $view -Value 'C:\\virtual host\\manifest.json'
        $ownedViews+=@($view)
        $hive=[Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $view)
        $key=$null
        try {{
            $key=$hive.OpenSubKey($script:testRegistryPath, $true)
            $key.SetValue('sentinel', 'preserve')
        }} finally {{if ($null -ne $key) {{$key.Dispose()}}; $hive.Dispose()}}
    }}
    $installed=@(Get-GangSearchRegistrations -Browser Chrome)
    foreach ($view in $views) {{
        Remove-GangSearchRegistration -Browser Chrome -View $view
    }}
    $removed=@(Get-GangSearchRegistrations -Browser Chrome)
    $sentinels=@(foreach ($view in $views) {{
        $hive=[Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $view)
        $key=$null
        try {{
            $key=$hive.OpenSubKey($script:testRegistryPath)
            $key.GetValue('sentinel')
        }} finally {{if ($null -ne $key) {{$key.Dispose()}}; $hive.Dispose()}}
    }})
}} finally {{
    foreach ($view in $ownedViews) {{
        $hive=[Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', $view)
        try {{$hive.DeleteSubKey($script:testRegistryPath, $false)}} finally {{$hive.Dispose()}}
    }}
}}
""" + report("@{installed=$installed; removed=$removed; sentinels=$sentinels}"))
    data = result_json(result)
    assert all(item["HasValue"] is True and item["Kind"] == 1 for item in data["installed"])
    assert all(item["Value"] == r"C:\virtual host\manifest.json" for item in data["installed"])
    assert all(item["HasValue"] is False for item in data["removed"])
    assert data["sentinels"] == ["preserve", "preserve"]
