<#
.SYNOPSIS
LibreChat과 MongoDB를 실행하거나 조회하고 최초 관리자 계정을 생성합니다.
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'validate', 'create-admin')]
    [string]$Action = 'start'
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configurationDirectory = Join-Path $workspaceRoot 'config\LibreChat'
$environmentPath = Join-Path $configurationDirectory '.env.local'
if (-not (Test-Path -LiteralPath $environmentPath)) {
    throw 'scripts\LibreChat\prepare-environment.ps1을 먼저 실행해 주세요.'
}
if ($Action -eq 'start') {
    foreach ($requiredDirectoryName in @('uploads', 'application')) {
        $requiredDirectoryPath = Join-Path $workspaceRoot "data\LibreChat\$requiredDirectoryName"
        if (-not (Test-Path -LiteralPath $requiredDirectoryPath -PathType Container)) {
            throw '보존 데이터 경로가 없습니다. 기존 데이터 이전 또는 최초 환경 준비를 먼저 완료해 주세요.'
        }
    }
    foreach ($legacyDirectoryName in @('uploads', 'data')) {
        if (Test-Path -LiteralPath (Join-Path $workspaceRoot "runtime\LibreChat\$legacyDirectoryName")) {
            throw '이전 runtime 데이터 경로가 남아 있습니다. 저장 위치 이전을 확인한 뒤 기동해 주세요.'
        }
    }
}
if ($Action -in @('start', 'create-admin')) {
    & (Join-Path $PSScriptRoot 'prepare-environment.ps1') -ValidateOnly
}
$composeArguments = @(
    'compose', '--env-file', $environmentPath,
    '-f', (Join-Path $configurationDirectory 'compose.yaml')
)

switch ($Action) {
    'start' { & docker @composeArguments up -d --wait --wait-timeout 240 }
    'stop' { & docker @composeArguments stop }
    'status' { & docker @composeArguments ps }
    'logs' { & docker @composeArguments logs --tail 100 librechat }
    'validate' { & docker @composeArguments config --quiet }
    'create-admin' {
        $credentialsPath = Join-Path $configurationDirectory 'admin-credentials.local.json'
        $previousOutputEncoding = $OutputEncoding
        try {
            $OutputEncoding = [Text.UTF8Encoding]::new($false)
            Get-Content -LiteralPath $credentialsPath -Raw -Encoding UTF8 |
                & docker @composeArguments exec -T librechat node config/provision-admin.cjs
        } finally {
            $OutputEncoding = $previousOutputEncoding
        }
    }
}
exit $LASTEXITCODE
