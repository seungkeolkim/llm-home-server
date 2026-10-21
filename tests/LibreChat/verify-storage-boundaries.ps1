<#
.SYNOPSIS
임시 workspace에서 데이터 보존과 이전 경로의 기동 거부를 검증합니다.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$fixtureDirectory = Join-Path $workspaceDirectory ('runtime\LibreChat\diagnostics\storage-boundary-test-' + [guid]::NewGuid().ToString('N'))
$powershellExecutable = (Get-Process -Id $PID).Path

function Invoke-ExpectedScriptResult {
    <#
    .SYNOPSIS
    별도 PowerShell에서 fixture 스크립트의 종료 코드와 예상 메시지를 확인합니다.
    #>
    param(
        [string]$ScriptPath,
        [string[]]$ScriptArguments = @(),
        [int]$ExpectedExitCode = 0,
        [string]$ExpectedMessage = ''
    )
    $scriptOutput = & $powershellExecutable -NoProfile -File $ScriptPath @ScriptArguments 2>&1
    if ($LASTEXITCODE -ne $ExpectedExitCode) {
        throw "예상하지 못한 종료 코드: $scriptOutput"
    }
    if ($ExpectedMessage -and ($scriptOutput -join "`n") -notlike "*$ExpectedMessage*") {
        throw '예상한 데이터 경로 확인 메시지가 없습니다.'
    }
}

foreach ($relativeDirectory in @('scripts\LibreChat', 'config\LibreChat', 'config\Strata')) {
    New-Item -ItemType Directory -Path (Join-Path $fixtureDirectory $relativeDirectory) -Force | Out-Null
}
foreach ($scriptName in @('prepare-environment.ps1', 'run-librechat.ps1')) {
    Copy-Item -LiteralPath (Join-Path $workspaceDirectory "scripts\LibreChat\$scriptName") -Destination (Join-Path $fixtureDirectory 'scripts\LibreChat')
}
Copy-Item -LiteralPath (Join-Path $workspaceDirectory 'config\LibreChat\librechat.template.yaml') -Destination (Join-Path $fixtureDirectory 'config\LibreChat')
@{
    api_key = 'fixture-api-key'
    port = 8488
    model_name = 'fixture-model'
    args = @('--max-context', '163840')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $fixtureDirectory 'config\Strata\strata.local.json') -Encoding utf8

$prepareScriptPath = Join-Path $fixtureDirectory 'scripts\LibreChat\prepare-environment.ps1'
$runnerScriptPath = Join-Path $fixtureDirectory 'scripts\LibreChat\run-librechat.ps1'
Invoke-ExpectedScriptResult -ScriptPath $prepareScriptPath -ScriptArguments @('-PublicUrl', 'http://localhost:8588')

foreach ($relativeDirectory in @('data\LibreChat\uploads', 'data\LibreChat\application', 'runtime\LibreChat\logs', 'runtime\LibreChat\diagnostics')) {
    if (-not (Test-Path -LiteralPath (Join-Path $fixtureDirectory $relativeDirectory) -PathType Container)) {
        throw "필수 저장 경로 누락: $relativeDirectory"
    }
}
$protectedRelativePaths = @(
    'config\LibreChat\.env.local',
    'config\LibreChat\admin-credentials.local.json',
    'data\LibreChat\uploads\preservation-check.txt',
    'data\LibreChat\application\preservation-check.txt'
)
foreach ($relativePath in $protectedRelativePaths | Select-Object -Skip 2) {
    Set-Content -LiteralPath (Join-Path $fixtureDirectory $relativePath) -Value 'preserve-existing-data'
}
$protectedHashes = @{}
foreach ($relativePath in $protectedRelativePaths) {
    $protectedHashes[$relativePath] = (Get-FileHash -LiteralPath (Join-Path $fixtureDirectory $relativePath)).Hash
}
Invoke-ExpectedScriptResult -ScriptPath $prepareScriptPath
foreach ($relativePath in $protectedRelativePaths) {
    if ((Get-FileHash -LiteralPath (Join-Path $fixtureDirectory $relativePath)).Hash -ne $protectedHashes[$relativePath]) {
        throw "재준비 중 보존 대상이 변경되었습니다: $relativePath"
    }
}
Write-Output 'Preparation paths and repeated preparation preservation: OK'

New-Item -ItemType Directory -Path (Join-Path $fixtureDirectory 'runtime\LibreChat\uploads') | Out-Null
Invoke-ExpectedScriptResult -ScriptPath $prepareScriptPath -ExpectedExitCode 1 -ExpectedMessage '기존 runtime의 보존 데이터'
Invoke-ExpectedScriptResult -ScriptPath $runnerScriptPath -ScriptArguments @('start') -ExpectedExitCode 1 -ExpectedMessage '이전 runtime 데이터 경로'
Write-Output 'Legacy data rejected before preparation or Docker startup: OK'

$missingDataFixture = Join-Path $fixtureDirectory 'missing-data-workspace'
New-Item -ItemType Directory -Path (Join-Path $missingDataFixture 'scripts\LibreChat') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $missingDataFixture 'config\LibreChat') -Force | Out-Null
Copy-Item -LiteralPath $runnerScriptPath -Destination (Join-Path $missingDataFixture 'scripts\LibreChat\run-librechat.ps1')
Set-Content -LiteralPath (Join-Path $missingDataFixture 'config\LibreChat\.env.local') -Value 'LIBRECHAT_PORT=8588'
Invoke-ExpectedScriptResult -ScriptPath (Join-Path $missingDataFixture 'scripts\LibreChat\run-librechat.ps1') -ScriptArguments @('start') -ExpectedExitCode 1 -ExpectedMessage '보존 데이터 경로가 없습니다'
Write-Output 'Missing persistent data rejected before Docker startup: OK'
exit 0
