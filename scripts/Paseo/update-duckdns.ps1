<#
.SYNOPSIS
Windows 서버의 공인 IPv4를 DuckDNS에 등록하고 갱신합니다.
.DESCRIPTION
Configure는 Token을 이 PC의 현재 사용자에게 귀속된 DPAPI로 암호화합니다.
수동 실행만 지원하며 Task를 등록하지 않습니다. Token은 출력하지 않습니다.
Update는 HTTPS 요청의 접속 IPv4를 DuckDNS가 감지하게 합니다.
.EXAMPLE
.\scripts\Paseo\update-duckdns.ps1 Configure
.EXAMPLE
.\scripts\Paseo\update-duckdns.ps1 Status
#>
[CmdletBinding()]
param(
    [ValidateSet('Configure', 'Update', 'Status')]
    [string]$Action = 'Status',
    [ValidatePattern('^[a-z0-9][a-z0-9-]*\.duckdns\.org$')]
    [string]$Hostname = 'azzi-home.duckdns.org'
)

$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configurationPath = Join-Path $workspaceDirectory 'config/Paseo/duckdns.local.json'
$statusPath = Join-Path $workspaceDirectory 'runtime/Paseo/duckdns-status.json'

function Read-DuckDnsConfiguration {
    <# .SYNOPSIS 현재 사용자에게 귀속된 암호화 Token 설정을 읽습니다. #>
    if (-not (Test-Path -LiteralPath $configurationPath)) {
        throw 'DuckDNS Token이 설정되지 않았습니다. 먼저 Configure를 실행해 주세요.'
    }
    return Get-Content -LiteralPath $configurationPath -Raw | ConvertFrom-Json
}

function Invoke-DuckDnsUpdate {
    <#
    .SYNOPSIS
    Token을 출력하지 않고 HTTPS로 서버의 공인 IPv4를 갱신합니다.
    .DESCRIPTION
    DuckDNS 응답에는 공개 IP와 갱신 결과만 포함합니다. 요청 실패 시 URI나 Token이
    오류 메시지에 노출되지 않도록 고정된 오류 문구로 바꿉니다.
    #>
    param([object]$Configuration)

    if ($Configuration.hostname -notmatch '^[a-z0-9][a-z0-9-]*\.duckdns\.org$') {
        throw 'DuckDNS hostname 형식이 올바르지 않습니다.'
    }
    $secureToken = ConvertTo-SecureString -String $Configuration.encrypted_token
    $tokenPointer = [IntPtr]::Zero
    try {
        $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
        $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
        $domainName = $Configuration.hostname -replace '\.duckdns\.org$', ''
        $requestAddress = 'https://www.duckdns.org/update?domains=' +
            [Uri]::EscapeDataString($domainName) + '&token=' +
            [Uri]::EscapeDataString($plainToken) + '&verbose=true'
        try {
            $responseText = Invoke-RestMethod -Uri $requestAddress -TimeoutSec 20 -ErrorAction Stop
        }
        catch {
            throw 'DuckDNS HTTPS 요청이 실패했습니다. 네트워크와 Token을 확인해 주세요.'
        }
    }
    finally {
        if ($tokenPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
        }
        $plainToken = $null
        $requestAddress = $null
        $secureToken.Dispose()
    }

    $responseLines = @(([string]$responseText).Trim() -split '\r?\n')
    if ($responseLines.Count -lt 2 -or $responseLines[0] -ne 'OK') {
        throw 'DuckDNS가 갱신을 거부했습니다. hostname과 Token을 확인해 주세요.'
    }
    $detectedAddress = $null
    if (-not [Net.IPAddress]::TryParse($responseLines[1], [ref]$detectedAddress) -or
        $detectedAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'DuckDNS가 유효한 IPv4를 반환하지 않았습니다.'
    }
    $updateStatus = [ordered]@{
        hostname = $Configuration.hostname
        ipv4 = $detectedAddress.ToString()
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
        result = $responseLines[-1]
    }
    [IO.Directory]::CreateDirectory((Split-Path $statusPath -Parent)) | Out-Null
    [IO.File]::WriteAllText($statusPath, ($updateStatus | ConvertTo-Json))
    return [pscustomobject]$updateStatus
}

function Set-DuckDnsConfiguration {
    <# .SYNOPSIS Token을 터미널에서 입력받아 DPAPI로 암호화하고 한 번 갱신합니다. #>
    $enteredToken = Read-Host 'DuckDNS Token (hidden)' -AsSecureString
    try {
        if ($enteredToken.Length -eq 0) {
            throw 'Token을 입력하지 않았습니다.'
        }
        $newConfiguration = [pscustomobject]@{
            hostname = $Hostname
            encrypted_token = ConvertFrom-SecureString -SecureString $enteredToken
        }
        $initialUpdateStatus = Invoke-DuckDnsUpdate -Configuration $newConfiguration
        [IO.File]::WriteAllText($configurationPath, ($newConfiguration | ConvertTo-Json))
        return $initialUpdateStatus
    }
    finally {
        $enteredToken.Dispose()
    }
}

switch ($Action) {
    'Configure' { Set-DuckDnsConfiguration | Format-List }
    'Update' { Invoke-DuckDnsUpdate -Configuration (Read-DuckDnsConfiguration) | Format-List }
    'Status' {
        [pscustomobject]@{
            Configured = Test-Path -LiteralPath $configurationPath
            UpdateMode = 'Manual'
        } | Format-List
        if (Test-Path -LiteralPath $statusPath) {
            Get-Content -LiteralPath $statusPath -Raw
        }
    }
}
