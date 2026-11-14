<#
.SYNOPSIS
Paseo의 검증된 CLI와 Windows Desktop을 전용 경로에 준비합니다.
.DESCRIPTION
기존 Pi dependency와 설정을 읽기만 하며, 이미 만들어진 Paseo 설정은 보존합니다.
Relay 배치와 Caddy reload는 운영 문서의 별도 절차로 수행합니다.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$managementPythonPath = Join-Path $workspaceDirectory '.venv/ManagementServer/Scripts/python.exe'
$paseoPackageDirectory = Join-Path $workspaceDirectory 'data/Paseo/npm'
New-Item -ItemType Directory -Path $paseoPackageDirectory -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $workspaceDirectory 'requirements/Paseo/package.json') -Destination $paseoPackageDirectory
Copy-Item -LiteralPath (Join-Path $workspaceDirectory 'requirements/Paseo/package-lock.json') -Destination $paseoPackageDirectory
& npm.cmd ci --prefix $paseoPackageDirectory --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Paseo CLI dependency 준비 실패' }
& $managementPythonPath -X utf8 -B (Join-Path $PSScriptRoot 'download_desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Paseo Desktop 검증 실패' }
& $managementPythonPath -X utf8 -B (Join-Path $PSScriptRoot 'configure_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'Paseo runtime 준비 실패' }
