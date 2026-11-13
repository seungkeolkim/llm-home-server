#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$firewallRuleName = 'LlmHomeServerRemotePiHttpsInbound'

function Enable-RemotePiHttpsFirewall {
    <#
    .SYNOPSIS
    Remote Pi Caddy에 필요한 TCP 443 및 8789의 inbound만 허용합니다.
    .DESCRIPTION
    관리자 PowerShell에서 실행합니다. 기존 다른 firewall rule은 변경하지 않습니다.
    같은 이름의 rule이 있으면 설정을 검증하고, 예상과 다르면 중단합니다.
    #>
    $existingRule = Get-NetFirewallRule -Name $firewallRuleName -ErrorAction SilentlyContinue
    if ($existingRule) {
        $existingPortFilter = $existingRule | Get-NetFirewallPortFilter
        $existingPorts = @($existingPortFilter.LocalPort | Sort-Object)
        $expectedPorts = @('443', '8789')
        $portDifference = Compare-Object $expectedPorts $existingPorts
        if ($portDifference -or $existingRule.Direction -ne 'Inbound' -or
            $existingRule.Action -ne 'Allow' -or $existingPortFilter.Protocol -ne 'TCP') {
            throw "같은 이름의 기존 rule이 예상 설정과 다릅니다: $firewallRuleName"
        }
        Enable-NetFirewallRule -Name $firewallRuleName | Out-Null
    }
    else {
        New-NetFirewallRule -Name $firewallRuleName `
            -DisplayName 'LLM Home Server Remote Pi HTTPS' `
            -Description 'Remote Pi Caddy: TLS-ALPN-01 TCP 443 and Android relay TCP 8789.' `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443, 8789 `
            -Profile Any | Out-Null
    }

    Get-NetFirewallRule -Name $firewallRuleName |
        Select-Object Name, Enabled, Direction, Action, Profile
    Get-NetFirewallRule -Name $firewallRuleName |
        Get-NetFirewallPortFilter |
        Select-Object Protocol, LocalPort
}

$resultPath = Join-Path $PSScriptRoot '../../runtime/RemotePi/firewall-result.json'
try {
    $ruleDetails = @(Enable-RemotePiHttpsFirewall)
    $resultRecord = @{ success = $true; rule = $firewallRuleName; details = $ruleDetails }
}
catch {
    $resultRecord = @{ success = $false; rule = $firewallRuleName; error = $_.Exception.Message }
    throw
}
finally {
    [System.IO.File]::WriteAllText($resultPath, ($resultRecord | ConvertTo-Json -Depth 5))
}
