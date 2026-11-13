<#
.SYNOPSIS
기존 Pi 설정을 덮어쓰지 않고 Remote Pi loader 한 개를 추가합니다.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

function Install-RemotePiNativeExtension {
    <#
    .SYNOPSIS
    기존 Pi runtime의 자동 discovery 경로에 별도 wrapper를 연결합니다.
    .DESCRIPTION
    같은 loader는 유지하고 내용이 다른 기존 파일은 덮어쓰지 않습니다.
    Pi 설정·기존 Extension 및 실행 중 프로세스는 변경하지 않습니다.
    #>
    $agentDirectory = Join-Path $workspaceDirectory 'runtime/PiCodingAgent/agent'
    $wrapperPath = Join-Path $PSScriptRoot 'remote-pi-extension.ts'
    $dependencyPath = Join-Path $workspaceDirectory 'data/RemotePi/npm/node_modules/remote-pi/dist/index.js'
    foreach ($requiredPath in @((Join-Path $agentDirectory 'settings.json'), $wrapperPath, $dependencyPath)) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "먼저 Pi와 Remote Pi dependency를 준비해 주세요: $requiredPath"
        }
    }
    $loaderDirectory = Join-Path $agentDirectory 'extensions'
    $loaderPath = Join-Path $loaderDirectory 'remote-pi.ts'
    $loaderContent = @(
        '/** 기존 Pi 설정을 수정하지 않고 Remote Pi policy wrapper를 추가합니다. */'
        'export { default } from "../../../../scripts/RemotePi/remote-pi-extension.ts";'
    ) -join "`n"
    if (Test-Path -LiteralPath $loaderPath) {
        $existingContent = [IO.File]::ReadAllText($loaderPath).Replace("`r`n", "`n").Trim()
        if ($existingContent -ne $loaderContent.Trim()) {
            throw "내용이 다른 기존 loader를 덮어쓰지 않았습니다: $loaderPath"
        }
    }
    else {
        [IO.Directory]::CreateDirectory($loaderDirectory) | Out-Null
        [IO.File]::WriteAllText($loaderPath, $loaderContent + "`n")
    }
    [pscustomobject]@{ Loader = $loaderPath; ExistingPiSettingsChanged = $false }
}

Install-RemotePiNativeExtension | Format-List
