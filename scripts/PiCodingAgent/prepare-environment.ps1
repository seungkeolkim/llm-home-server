<#
.SYNOPSIS
고정된 Pi dependency와 격리 설정, 전용 브라우저를 준비합니다.
#>
[CmdletBinding()]
param([switch]$SkipBrowserInstall)

$ErrorActionPreference = 'Stop'
$workspaceDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$piPackageDirectory = Join-Path $workspaceDirectory 'data\PiCodingAgent\npm'
$managementPythonPath = Join-Path $workspaceDirectory '.venv\ManagementServer\Scripts\python.exe'
New-Item -ItemType Directory -Path $piPackageDirectory -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $workspaceDirectory 'requirements\PiCodingAgent\package.json') -Destination $piPackageDirectory
Copy-Item -LiteralPath (Join-Path $workspaceDirectory 'requirements\PiCodingAgent\package-lock.json') -Destination $piPackageDirectory
& npm.cmd ci --prefix $piPackageDirectory --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Pi npm 설치에 실패했습니다.' }
& (Join-Path $PSScriptRoot 'download-desktop.ps1')
& $managementPythonPath -X utf8 -B (Join-Path $PSScriptRoot 'configure_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'Pi 설정 준비에 실패했습니다.' }
$desktopSdkModulesPath = Join-Path $workspaceDirectory 'runtime\PiCodingAgent\desktop\sdk\current\node_modules'
if (-not (Test-Path -LiteralPath $desktopSdkModulesPath)) {
    New-Item -ItemType Junction -Path $desktopSdkModulesPath -Target (Join-Path $piPackageDirectory 'node_modules') | Out-Null
}
if (-not $SkipBrowserInstall) {
    & node (Join-Path $PSScriptRoot 'browser_cli.mjs') install
    if ($LASTEXITCODE -ne 0) { throw 'agent-browser 전용 브라우저 설치에 실패했습니다.' }
}
