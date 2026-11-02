<#
.SYNOPSIS
PolyStrata 전용 venv와 고정 dependency를 준비한 뒤 Engine·tokenizer·Vision 설정을 검증합니다.
Service나 model은 기동하지 않습니다.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$bootstrapPython = Join-Path $workspaceDirectory '.venv\Strata\Scripts\python.exe'
$polystrataPython = Join-Path $workspaceDirectory '.venv\PolyStrata\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $polystrataPython)) {
    & $bootstrapPython -m venv (Join-Path $workspaceDirectory '.venv\PolyStrata')
    if ($LASTEXITCODE -ne 0) { throw 'PolyStrata venv 생성 실패' }
}
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $polystrataPython -m pip install -r (Join-Path $workspaceDirectory 'requirements\PolyStrata\requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'PolyStrata dependency 설치 실패' }
& $polystrataPython -B (Join-Path $PSScriptRoot 'prepare_environment.py')
if ($LASTEXITCODE -ne 0) { throw 'PolyStrata 환경 준비 실패' }
