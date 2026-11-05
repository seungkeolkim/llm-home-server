<#
.SYNOPSIS
관리 서버와 동일한 Profile 소유권으로 Infernix를 조회·기동·종료하거나 메모리 Plan을 만듭니다.
#>
[CmdletBinding()]
param([ValidateSet('status', 'start', 'stop', 'plan')][string]$Action = 'status')

$ErrorActionPreference = 'Stop'
$managementPython = Join-Path $PSScriptRoot '.venv\ManagementServer\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $managementPython)) {
    throw '관리 서버 Python 환경을 먼저 준비해 주세요.'
}
$env:PYTHONUTF8 = '1'
& $managementPython -B (Join-Path $PSScriptRoot 'scripts\Infernix\run_profile.py') $Action
exit $LASTEXITCODE
