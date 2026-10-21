<#
.SYNOPSIS
관리 서버 전용 Python 환경과 local 설정을 준비합니다.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$managementPython = Join-Path $workspaceDirectory '.venv\ManagementServer\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $managementPython)) {
    & python -m venv (Join-Path $workspaceDirectory '.venv\ManagementServer')
    if ($LASTEXITCODE) { throw '관리 서버 Python 환경 생성에 실패했습니다.' }
}
& $managementPython -m pip install -r (Join-Path $workspaceDirectory 'requirements\ManagementServer\runtime.txt')
if ($LASTEXITCODE) { throw '관리 서버 dependency 설치에 실패했습니다.' }
& $managementPython -B (Join-Path $PSScriptRoot 'prepare_environment.py')
exit $LASTEXITCODE
