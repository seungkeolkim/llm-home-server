<#
.SYNOPSIS
공식 Infernix Windows Release와 local Profile을 준비하고 모델은 기동하지 않습니다.
#>
[CmdletBinding()]
param([switch]$ConfigurationOnly)

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$managementPython = Join-Path $workspaceDirectory '.venv\ManagementServer\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $managementPython)) {
    throw '관리 서버 Python 환경을 먼저 준비해 주세요.'
}
$env:PYTHONUTF8 = '1'
$preparationArguments = @('-B', (Join-Path $PSScriptRoot 'prepare_environment.py'))
if ($ConfigurationOnly) { $preparationArguments += '--configuration-only' }
& $managementPython @preparationArguments
exit $LASTEXITCODE
