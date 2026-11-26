<#
.SYNOPSIS
공식 Basalt Windows release와 전용 dependency를 모델 기동 없이 준비합니다.
#>
[CmdletBinding()]
param([switch]$ConfigurationOnly, [string]$ConfigurationPath)

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$managementPython = Join-Path $workspaceDirectory '.venv\ManagementServer\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $managementPython)) {
    throw '관리 서버 Python 환경을 먼저 준비해 주세요.'
}
$preparationArguments = @('-X', 'utf8', '-u', '-B', (Join-Path $PSScriptRoot 'prepare_environment.py'))
if ($ConfigurationOnly) { $preparationArguments += '--configuration-only' }
if ($ConfigurationPath) { $preparationArguments += @('--configuration', $ConfigurationPath) }
& $managementPython @preparationArguments
exit $LASTEXITCODE
