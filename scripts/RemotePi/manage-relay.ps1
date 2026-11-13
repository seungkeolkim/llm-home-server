<#
.SYNOPSIS
Pi의 ON/OFF와 독립적으로 Self-hosted Relay 및 Caddy만 제어합니다.
.EXAMPLE
.\scripts\RemotePi\manage-relay.ps1 status
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'validate')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$environmentPath = Join-Path $workspaceDirectory 'config/RemotePi/.env.local'
$composePath = Join-Path $workspaceDirectory 'config/RemotePi/compose.yaml'

function Invoke-RemotePiCompose {
    <#
    .SYNOPSIS
    Remote Pi 전용 project의 Compose 명령만 실행합니다.
    .DESCRIPTION
    다른 Compose project나 Windows Native Pi, LLM, LibreChat은 제어하지 않습니다.
    stop은 데이터를 삭제하지 않고 두 container만 중지합니다.
    #>
    param([string]$RequestedAction)

    if (-not (Test-Path -LiteralPath $environmentPath)) {
        throw 'config/RemotePi/.env.example을 .env.local로 복사하고 DDNS를 지정해 주세요.'
    }
    $composeArguments = @('compose', '--env-file', $environmentPath, '-f', $composePath)
    switch ($RequestedAction) {
        'start' { & docker @composeArguments up -d }
        'stop' { & docker @composeArguments stop }
        'status' { & docker @composeArguments ps }
        'logs' { & docker @composeArguments logs --no-color --tail 80 }
        'validate' { & docker @composeArguments config --quiet }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Remote Pi Compose 명령이 실패했습니다: $RequestedAction"
    }
}

Invoke-RemotePiCompose -RequestedAction $Action
