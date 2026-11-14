<#
.SYNOPSIS
기존 LLM 및 Remote Pi와 별도로 Paseo를 시작하거나 종료합니다.
.EXAMPLE
.\run-paseo.ps1 desktop
.EXAMPLE
.\run-paseo.ps1 pair
#>
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('start', 'stop', 'status', 'desktop', 'pair')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$managementPythonPath = Join-Path $PSScriptRoot '.venv\ManagementServer\Scripts\python.exe'
$paseoRuntimeScriptPath = Join-Path $PSScriptRoot 'scripts\Paseo\service_runtime.py'
& $managementPythonPath -X utf8 -B $paseoRuntimeScriptPath $Action
exit $LASTEXITCODE
