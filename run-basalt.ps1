<#
.SYNOPSIS
관리 서버와 같은 소유권으로 등록된 Basalt Profile을 조회·기동·종료합니다.
#>
[CmdletBinding()]
param(
    [ValidateSet('status', 'start', 'stop')][string]$Action = 'status',
    [string]$ProfileIdentifier
)

$ErrorActionPreference = 'Stop'
$managementPython = Join-Path $PSScriptRoot '.venv\ManagementServer\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $managementPython)) {
    throw '관리 서버 Python 환경을 먼저 준비해 주세요.'
}
$runnerArguments = @('-X', 'utf8', '-B', (Join-Path $PSScriptRoot 'scripts\Basalt\run_profile.py'), $Action)
if ($ProfileIdentifier) { $runnerArguments += @('--profile', $ProfileIdentifier) }
& $managementPython @runnerArguments
exit $LASTEXITCODE
