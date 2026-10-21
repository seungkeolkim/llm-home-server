<#
.SYNOPSIS
현재 Windows 계정에서 LLM Home Server를 수동 실행합니다. 기본으로 reload를 사용합니다.
#>
[CmdletBinding()]
param([switch]$NoReload)

$ErrorActionPreference = 'Stop'
$managementPython = Join-Path $PSScriptRoot '.venv\ManagementServer\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $managementPython)) {
    throw 'scripts\ManagementServer\prepare-environment.ps1을 먼저 실행해 주세요.'
}
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location -LiteralPath $PSScriptRoot
try {
    $serverArguments = @('-B', '-m', 'management_server')
    if ($NoReload) { $serverArguments += '--no-reload' }
    & $managementPython @serverArguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
