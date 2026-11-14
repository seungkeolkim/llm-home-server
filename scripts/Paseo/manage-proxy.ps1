<#
.SYNOPSIS
Paseo가 사용하는 기존 Caddy를 현재 project·인증서·network 이름으로 관리합니다.
.EXAMPLE
.\scripts\Paseo\manage-proxy.ps1 status
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'validate', 'reload')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$environmentPath = Join-Path $workspaceDirectory 'config/RemotePi/.env.local'
$composePath = Join-Path $workspaceDirectory 'config/RemotePi/compose.yaml'

function Invoke-PaseoProxyCompose {
    <#
    .SYNOPSIS
    공유 Caddy만 조작하고 Paseo Relay·Native daemon·LLM은 유지합니다.
    #>
    param([string]$RequestedAction)
    if (-not (Test-Path -LiteralPath $environmentPath)) {
        throw 'config/RemotePi/.env.example을 .env.local로 복사하고 DDNS를 지정해 주세요.'
    }
    $composeArguments = @('compose', '--env-file', $environmentPath, '-f', $composePath)
    switch ($RequestedAction) {
        'start' { & docker @composeArguments up -d caddy }
        'stop' { & docker @composeArguments stop caddy }
        'status' { & docker @composeArguments ps caddy }
        'logs' { & docker @composeArguments logs --no-color --tail 80 caddy }
        'validate' { & docker @composeArguments config --quiet }
        'reload' {
            & docker @composeArguments exec -T caddy caddy validate --config /etc/caddy/Caddyfile
            if ($LASTEXITCODE -ne 0) { throw 'Caddy 설정 검증에 실패했습니다.' }
            & docker @composeArguments exec -T caddy caddy reload --config /etc/caddy/Caddyfile
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Paseo Caddy 명령 실패: $RequestedAction" }
}

Invoke-PaseoProxyCompose -RequestedAction $Action
