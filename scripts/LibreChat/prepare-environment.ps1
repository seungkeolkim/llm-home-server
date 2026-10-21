<#
.SYNOPSIS
Template에서 복사한 LibreChat 설정과 관리자 자격 증명을 검증하고 경로를 준비합니다.
#>
[CmdletBinding()]
param(
    [string]$PublicUrl = '',
    [ValidateRange(1, 65535)]
    [int]$Port = 8588,
    [switch]$ValidateOnly
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

function Assert-ConfiguredValue {
    <#
    .SYNOPSIS
    필수 설정이 비어 있거나 template의 안내 문자열인 경우 항목명만 표시하고 중단합니다.
    #>
    param([string]$FieldName, [string]$FieldValue)
    if ([string]::IsNullOrWhiteSpace($FieldValue) -or $FieldValue.StartsWith('CHANGE_ME_') -or $FieldValue -eq '${API_KEY}') {
        throw "$FieldName 항목을 실제 값으로 바꿔 주세요."
    }
}

function Read-EnvironmentSettings {
    <#
    .SYNOPSIS
    기존 local env의 값을 읽어 재준비 시 secret과 운영 설정을 보존합니다.
    #>
    param([string]$Path)
    $environmentSettings = [ordered]@{}
    if (Test-Path -LiteralPath $Path) {
        foreach ($environmentLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
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

$localConfigurationPath = Join-Path $configurationDirectory 'librechat.local.yaml'
$administratorCredentialsPath = Join-Path $configurationDirectory 'admin-credentials.local.json'
foreach ($requiredPath in @($environmentPath, $localConfigurationPath, $administratorCredentialsPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "$requiredPath.template을 $requiredPath 파일로 복사하고 필수 값을 바꿔 주세요."
    }
}
$strataConfigurationPath = Join-Path $workspaceRoot 'config\Strata\strata.local.json'
$strataConfiguration = Get-Content -LiteralPath $strataConfigurationPath -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-ConfiguredValue -FieldName 'Strata api_key' -FieldValue $strataConfiguration.api_key
$contextArgumentIndex = [Array]::IndexOf($strataConfiguration.args, '--max-context')
if ($contextArgumentIndex -lt 0) {
    throw 'Strata local config에 --max-context가 없습니다.'
}
$contextTokenLimit = [int]$strataConfiguration.args[$contextArgumentIndex + 1]
$environmentSettings = Read-EnvironmentSettings -Path $environmentPath
foreach ($requiredSettingName in @(
    'DOMAIN_CLIENT', 'DOMAIN_SERVER', 'LIBRECHAT_PORT', 'MONGO_URI', 'STRATA_BASE_URL',
    'STRATA_API_KEY', 'CREDS_KEY', 'CREDS_IV', 'JWT_SECRET', 'JWT_REFRESH_SECRET'
)) {
    Assert-ConfiguredValue -FieldName $requiredSettingName -FieldValue $environmentSettings[$requiredSettingName]
}
if ($environmentSettings['STRATA_API_KEY'] -cne [string]$strataConfiguration.api_key) {
    throw 'STRATA_API_KEY는 Strata local config의 api_key와 같아야 합니다.'
}
if ($environmentSettings['CREDS_KEY'] -notmatch '^[0-9a-fA-F]{64}$' -or $environmentSettings['CREDS_IV'] -notmatch '^[0-9a-fA-F]{32}$') {
    throw 'CREDS_KEY는 64자리 hex, CREDS_IV는 32자리 hex여야 합니다.'
}
foreach ($secretSettingName in @('JWT_SECRET', 'JWT_REFRESH_SECRET')) {
    if ($environmentSettings[$secretSettingName].Length -lt 32) {
        throw "$secretSettingName 항목은 32자 이상이어야 합니다."
    }
}
$administratorCredentials = Get-Content -LiteralPath $administratorCredentialsPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($credentialFieldName in @('email', 'name', 'username', 'password')) {
    Assert-ConfiguredValue -FieldName "admin-credentials.local.json $credentialFieldName" -FieldValue $administratorCredentials.$credentialFieldName
}
if ($administratorCredentials.password.Length -lt 8) {
    throw '관리자 password는 8자 이상이어야 합니다.'
}
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
foreach ($originSettingName in @('DOMAIN_CLIENT', 'DOMAIN_SERVER')) {
    $configuredOrigin = [Uri]$environmentSettings[$originSettingName]
    if (-not $configuredOrigin.IsAbsoluteUri -or $configuredOrigin.Scheme -notin @('http', 'https')) {
        throw "$originSettingName 항목은 http 또는 https의 absolute URL이어야 합니다."
    }
}
if ($Port -lt 1 -or $Port -gt 65535) {
    throw 'LIBRECHAT_PORT는 1부터 65535 사이여야 합니다.'
}
if ($ValidateOnly) {
    if ([IO.File]::ReadAllText($localConfigurationPath) -match '__STRATA_(PORT|MODEL_NAME|CONTEXT_TOKENS)__') {
        throw 'LibreChat 설정의 경로 확장을 위해 prepare-environment.ps1을 먼저 실행해 주세요.'
    }
    Write-Output 'LibreChat local configuration verified.'
    return
}

foreach ($directoryPath in @(
    $configurationDirectory,
    (Join-Path $dataDirectory 'uploads'),
    (Join-Path $dataDirectory 'application'),
    (Join-Path $runtimeDirectory 'logs'),
    (Join-Path $runtimeDirectory 'diagnostics')
)) {
    New-Item -ItemType Directory -Path $directoryPath -Force | Out-Null
}

# 명시적인 port·origin 변경만 반영하고 사용자가 작성한 주석과 secret은 유지합니다.
$updatedSettings = @{}
if ($PSBoundParameters.ContainsKey('PublicUrl')) {
    $updatedSettings['DOMAIN_CLIENT'] = $PublicUrl
    $updatedSettings['DOMAIN_SERVER'] = $PublicUrl
    $updatedSettings['SESSION_COOKIE_SECURE'] = ([string]($publicAddress.Scheme -eq 'https')).ToLowerInvariant()
}
if ($PSBoundParameters.ContainsKey('Port')) {
    $updatedSettings['LIBRECHAT_PORT'] = [string]$Port
}
if ($updatedSettings.Count) {
    $environmentLines = foreach ($environmentLine in [IO.File]::ReadAllLines($environmentPath)) {
        $environmentParts = $environmentLine.Split('=', 2)
        if ($environmentParts.Count -eq 2 -and $updatedSettings.ContainsKey($environmentParts[0])) {
            '{0}={1}' -f $environmentParts[0], $updatedSettings[$environmentParts[0]]
        } else {
            $environmentLine
        }
    }
    [IO.File]::WriteAllLines($environmentPath, [string[]]$environmentLines, [Text.UTF8Encoding]::new($false))
}

$originalConfigurationText = [IO.File]::ReadAllText($localConfigurationPath)
$configurationText = $originalConfigurationText
$configurationText = $configurationText.Replace('__STRATA_MODEL_NAME__', $strataConfiguration.model_name)
$configurationText = $configurationText.Replace('__STRATA_PORT__', [string]$strataConfiguration.port)
$configurationText = $configurationText.Replace('__STRATA_CONTEXT_TOKENS__', [string]$contextTokenLimit)
if ($configurationText -cne $originalConfigurationText) {
    [IO.File]::WriteAllText($localConfigurationPath, $configurationText, [Text.UTF8Encoding]::new($false))
}
Write-Output "LibreChat 설정 준비 완료: $localConfigurationPath"
Write-Output "접속 주소: $PublicUrl / host port: $Port"
Write-Output "관리자 자격 증명 파일: $administratorCredentialsPath"
