#Requires -RunAsAdministrator
<#
.SYNOPSIS
Windows와 WSL Hyper-V 방화벽에서 LibreChat의 TCP host port만 허용합니다.
.DESCRIPTION
관리자 CMD 또는 PowerShell에서 실행합니다. 공유기 설정과 다른 service의 규칙은 변경하지 않습니다.
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8588
)

$ErrorActionPreference = 'Stop'
$windowsFirewallRuleName = "StrataLibreChatTcp$Port"
$hyperVFirewallRuleName = "StrataLibreChatWslTcp$Port"
$wslCreatorIdentifier = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'

try {
    $windowsFirewallRule = Get-NetFirewallRule -Name $windowsFirewallRuleName -ErrorAction SilentlyContinue
    if ($windowsFirewallRule) {
        Set-NetFirewallRule -Name $windowsFirewallRuleName -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Any -ErrorAction Stop | Out-Null
    }
    else {
        New-NetFirewallRule -Name $windowsFirewallRuleName -DisplayName "Strata LibreChat TCP $Port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Any -ErrorAction Stop | Out-Null
    }

    # Windows에서 반영된 HostFirewallLocal 항목은 Hyper-V cmdlet로 수정하지 않습니다.
    $hyperVFirewallRule = Get-NetFirewallHyperVRule -Name $hyperVFirewallRuleName -PolicyStore PersistentStore -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.PolicyStoreSourceType -eq 'Local' -and [string]$_.VMCreatorId -eq $wslCreatorIdentifier }
    if ($hyperVFirewallRule) {
        Set-NetFirewallHyperVRule -Name $hyperVFirewallRuleName -PolicyStore PersistentStore -VMCreatorId $wslCreatorIdentifier -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPorts $Port -ErrorAction Stop | Out-Null
    }
    else {
        New-NetFirewallHyperVRule -Name $hyperVFirewallRuleName -PolicyStore PersistentStore -DisplayName "Strata LibreChat WSL TCP $Port" -Direction Inbound -VMCreatorId $wslCreatorIdentifier -Enabled True -Action Allow -Protocol TCP -LocalPorts $Port -ErrorAction Stop | Out-Null
    }

    $verifiedWindowsRule = Get-NetFirewallRule -Name $windowsFirewallRuleName -PolicyStore ActiveStore -ErrorAction Stop
    $verifiedWindowsPort = $verifiedWindowsRule | Get-NetFirewallPortFilter -ErrorAction Stop
    if ([string]$verifiedWindowsRule.Enabled -ne 'True' -or [string]$verifiedWindowsRule.Action -ne 'Allow' -or [string]$verifiedWindowsRule.Direction -ne 'Inbound' -or [string]$verifiedWindowsPort.LocalPort -ne [string]$Port -or [string]$verifiedWindowsPort.Protocol -notin @('TCP', '6')) {
        throw 'Windows firewall rule verification failed.'
    }

    $verifiedHyperVRule = Get-NetFirewallHyperVRule -Name $hyperVFirewallRuleName -PolicyStore ActiveStore -ErrorAction Stop |
        Where-Object { [string]$_.PolicyStoreSourceType -eq 'Local' -and [string]$_.VMCreatorId -eq $wslCreatorIdentifier }
    if (-not $verifiedHyperVRule -or [string]$verifiedHyperVRule.Enabled -ne 'True' -or [string]$verifiedHyperVRule.Action -ne 'Allow' -or [string]$verifiedHyperVRule.Direction -ne 'Inbound' -or [string]$verifiedHyperVRule.LocalPorts -ne [string]$Port -or [string]$verifiedHyperVRule.Protocol -notin @('TCP', '6') -or [string]$verifiedHyperVRule.VMCreatorId -ne $wslCreatorIdentifier) {
        throw 'WSL Hyper-V firewall rule verification failed.'
    }
}
catch {
    Write-Error ("Firewall configuration failed: {0}" -f $_.Exception.Message) -ErrorAction Continue
    exit 1
}

Write-Output "Verified Windows and WSL inbound TCP $Port rules."
exit 0
