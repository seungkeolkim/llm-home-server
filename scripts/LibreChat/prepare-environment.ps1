<#
.SYNOPSIS
Strata local config를 읽어 LibreChat 설정과 최초 관리자 자격 증명을 준비합니다.
#>
[CmdletBinding()]
param(
    [string]$PublicUrl = '',
    [ValidateRange(1, 65535)]
    [int]$Port = 8588
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configurationDirectory = Join-Path $workspaceRoot 'config\LibreChat'
$runtimeDirectory = Join-Path $workspaceRoot 'runtime\LibreChat'
$dataDirectory = Join-Path $workspaceRoot 'data\LibreChat'
$environmentPath = Join-Path $configurationDirectory '.env.local'

foreach ($legacyPath in @(
    (Join-Path $runtimeDirectory 'uploads'),
    (Join-Path $runtimeDirectory 'data'),
    (Join-Path $runtimeDirectory 'admin-credentials.local.json')
)) {
    if (Test-Path -LiteralPath $legacyPath) {
        throw '기존 runtime의 보존 데이터를 먼저 이전해야 합니다. docs/LibreChat/README.md의 저장 위치 이전 안내를 확인해 주세요.'
    }
}

function New-RandomSecret {
    <#
    .SYNOPSIS
    Cryptographic random bytes를 hexadecimal secret으로 만듭니다.
    #>
    param([int]$ByteCount = 32)
    $randomBytes = New-Object byte[] $ByteCount
    $randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomGenerator.GetBytes($randomBytes)
    }
    finally {
        $randomGenerator.Dispose()
    }
    return ([BitConverter]::ToString($randomBytes)).Replace('-', '').ToLowerInvariant()
}

function Read-EnvironmentSettings {
    <#
    .SYNOPSIS
    기존 local env의 값을 읽어 재준비 시 secret과 운영 설정을 보존합니다.
    #>
    param([string]$Path)
    $environmentSettings = [ordered]@{}
    if (Test-Path -LiteralPath $Path) {
        foreach ($environmentLine in Get-Content -LiteralPath $Path) {
            if ([string]::IsNullOrWhiteSpace($environmentLine) -or $environmentLine.StartsWith('#')) {
                continue
            }
            $environmentParts = $environmentLine.Split('=', 2)
            if ($environmentParts.Count -eq 2) {
                $environmentSettings[$environmentParts[0]] = $environmentParts[1]
            }
        }
    }
    return $environmentSettings
}

$strataConfigurationPath = Join-Path $workspaceRoot 'config\Strata\strata.local.json'
$strataConfiguration = Get-Content -LiteralPath $strataConfigurationPath -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($strataConfiguration.api_key)) {
    throw 'Strata local config에 api_key가 없습니다.'
}
$contextArgumentIndex = [Array]::IndexOf($strataConfiguration.args, '--max-context')
if ($contextArgumentIndex -lt 0) {
    throw 'Strata local config에 --max-context가 없습니다.'
}
$contextTokenLimit = [int]$strataConfiguration.args[$contextArgumentIndex + 1]
$environmentSettings = Read-EnvironmentSettings -Path $environmentPath
if (-not $PSBoundParameters.ContainsKey('Port') -and $environmentSettings['LIBRECHAT_PORT']) {
    $Port = [int]$environmentSettings['LIBRECHAT_PORT']
}

if ([string]::IsNullOrWhiteSpace($PublicUrl)) {
    if ($environmentSettings['DOMAIN_CLIENT']) {
        $PublicUrl = $environmentSettings['DOMAIN_CLIENT']
    }
    else {
        $PublicUrl = "http://localhost:$Port"
    }
}
$publicAddress = [Uri]$PublicUrl
if (-not $publicAddress.IsAbsoluteUri -or $publicAddress.Scheme -notin @('http', 'https')) {
    throw 'PublicUrl은 http 또는 https의 absolute URL이어야 합니다.'
}
$PublicUrl = $PublicUrl.TrimEnd('/')

foreach ($directoryPath in @(
    $configurationDirectory,
    (Join-Path $dataDirectory 'uploads'),
    (Join-Path $dataDirectory 'application'),
    (Join-Path $runtimeDirectory 'logs'),
    (Join-Path $runtimeDirectory 'diagnostics')
)) {
    New-Item -ItemType Directory -Path $directoryPath -Force | Out-Null
}

$managedSettings = [ordered]@{
    HOST = '0.0.0.0'
    PORT = '3080'
    NODE_ENV = 'production'
    CONFIG_PATH = '/app/librechat.yaml'
    MONGO_URI = 'mongodb://mongodb:27017/LibreChat'
    DOMAIN_CLIENT = $PublicUrl
    DOMAIN_SERVER = $PublicUrl
    LIBRECHAT_PORT = [string]$Port
    STRATA_BASE_URL = "http://host.docker.internal:$($strataConfiguration.port)/v1"
    STRATA_API_KEY = $strataConfiguration.api_key
    ENDPOINTS = 'Strata,agents'
    SEARCH = 'false'
    ALLOW_EMAIL_LOGIN = 'true'
    ALLOW_REGISTRATION = 'false'
    ALLOW_SOCIAL_LOGIN = 'false'
    ALLOW_SOCIAL_REGISTRATION = 'false'
    ALLOW_PASSWORD_RESET = 'false'
    ALLOW_UNVERIFIED_EMAIL_LOGIN = 'false'
    SESSION_COOKIE_SECURE = ([string]($publicAddress.Scheme -eq 'https')).ToLowerInvariant()
    NO_INDEX = 'true'
    DEBUG_LOGGING = 'false'
    DEBUG_CONSOLE = 'false'
    SCHEDULES_SINGLE_PROCESS = 'true'
    NO_PROXY = 'localhost,127.0.0.1,::1,mongodb,host.docker.internal'
    LIBRECHAT_TEMP_CREDENTIALS_PATH = '/app/data/.env.temp'
}
foreach ($settingName in $managedSettings.Keys) {
    $environmentSettings[$settingName] = $managedSettings[$settingName]
}
foreach ($secretName in @('CREDS_KEY', 'JWT_SECRET', 'JWT_REFRESH_SECRET')) {
    if (-not $environmentSettings[$secretName]) {
        $environmentSettings[$secretName] = New-RandomSecret
    }
}
if (-not $environmentSettings['CREDS_IV']) {
    $environmentSettings['CREDS_IV'] = New-RandomSecret -ByteCount 16
}
$environmentLines = foreach ($settingName in $environmentSettings.Keys) {
    '{0}={1}' -f $settingName, $environmentSettings[$settingName]
}
[IO.File]::WriteAllLines($environmentPath, [string[]]$environmentLines, [Text.UTF8Encoding]::new($false))

$configurationTemplatePath = Join-Path $configurationDirectory 'librechat.template.yaml'
$configurationText = [IO.File]::ReadAllText($configurationTemplatePath)
$configurationText = $configurationText.Replace('__STRATA_MODEL_NAME__', $strataConfiguration.model_name)
$configurationText = $configurationText.Replace('__STRATA_PORT__', [string]$strataConfiguration.port)
$configurationText = $configurationText.Replace('__STRATA_CONTEXT_TOKENS__', [string]$contextTokenLimit)
$localConfigurationPath = Join-Path $configurationDirectory 'librechat.local.yaml'
[IO.File]::WriteAllText($localConfigurationPath, $configurationText, [Text.UTF8Encoding]::new($false))

$administratorCredentialsPath = Join-Path $configurationDirectory 'admin-credentials.local.json'
if (-not (Test-Path -LiteralPath $administratorCredentialsPath)) {
    $administratorCredentials = [ordered]@{
        email = 'admin@strata.home'
        name = 'Strata Administrator'
        username = 'strata-admin'
        password = New-RandomSecret -ByteCount 18
    }
    [IO.File]::WriteAllText(
        $administratorCredentialsPath,
        ($administratorCredentials | ConvertTo-Json),
        [Text.UTF8Encoding]::new($false)
    )
}
Write-Output "LibreChat 설정 준비 완료: $localConfigurationPath"
Write-Output "접속 주소: $PublicUrl / host port: $Port"
Write-Output "관리자 자격 증명 파일: $administratorCredentialsPath"
