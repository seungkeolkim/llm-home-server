<#
.SYNOPSIS
바깥 환경에서 Strata의 managed runtime을 실행하고 조회하거나 종료합니다.
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status', 'plan', 'verify', 'foreground')]
    [string]$Action = 'start'
)

$ErrorActionPreference = 'Stop'
$virtualPython = Join-Path $PSScriptRoot '.venv\Strata\Scripts\strata-runtime-python.exe'
if (-not (Test-Path -LiteralPath $virtualPython)) {
    throw 'Run prepare-strata-environment.ps1 first.'
}
& $virtualPython -I -B (Join-Path $PSScriptRoot 'scripts\Strata\strata_runner.py') $Action
exit $LASTEXITCODE
