param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-p]{32}$')]
    [string]$ExtensionId
)

$ErrorActionPreference = 'Stop'
$HostName = 'com.contexttrace.auth'
# 현재 디렉토리와 관계없이 스크립트 옆의 저장소 구조에서 런타임 경로를 구한다.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$HostDirectory = Join-Path $RepoRoot 'src/browser/contexttrace/native_host'
$HostLauncher = Join-Path $HostDirectory 'native_host.cmd'
$ManifestPath = Join-Path $HostDirectory "$HostName.json"
$RegistryPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName"

if (-not (Test-Path $HostLauncher)) {
    throw "Native host launcher not found: $HostLauncher"
}

$Manifest = @{
    name = $HostName
    description = 'ContextTrace local authentication bridge'
    path = $HostLauncher
    type = 'stdio'
    allowed_origins = @("chrome-extension://$ExtensionId/")
} | ConvertTo-Json -Depth 4

[System.IO.File]::WriteAllText($ManifestPath, $Manifest, [System.Text.UTF8Encoding]::new($false))
New-Item -Path $RegistryPath -Force | Out-Null
Set-Item -Path $RegistryPath -Value $ManifestPath

Write-Host 'ContextTrace Chrome Native Messaging host registered.' -ForegroundColor Green
Write-Host "Extension ID: $ExtensionId"
Write-Host "Manifest: $ManifestPath"
Write-Host 'Restart Chrome after loading the unpacked extension.'
