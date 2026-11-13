<#
.SYNOPSIS
LLM 및 LibreChat과 독립적으로 Pi Desktop과 CLI를 제어합니다.
.EXAMPLE
.\run-pi-coding-agent.ps1 start
.EXAMPLE
.\run-pi-coding-agent.ps1 cli -- --continue
#>
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('start', 'stop', 'status', 'cli')]
    [string]$Action = 'status',
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$PiArguments
)

$ErrorActionPreference = 'Stop'
$managementPythonPath = Join-Path $PSScriptRoot '.venv\ManagementServer\Scripts\python.exe'
$piServiceScriptPath = Join-Path $PSScriptRoot 'scripts\PiCodingAgent\service_runtime.py'
& $managementPythonPath -X utf8 -B $piServiceScriptPath $Action @PiArguments
exit $LASTEXITCODE
