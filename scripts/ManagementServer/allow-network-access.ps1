#Requires -RunAsAdministrator
<#
.SYNOPSIS
Windows native 관리 서버의 TCP 8788 inbound만 허용합니다.
#>
[CmdletBinding()]
param([ValidateRange(1, 65535)][int]$Port = 8788)

$ErrorActionPreference = 'Stop'
$ruleName = "LlmHomeServerTcp$Port"
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -Name $ruleName -Enabled True -Direction Inbound -Action Allow -Profile Any
    Get-NetFirewallRule -Name $ruleName | Get-NetFirewallPortFilter |
        Set-NetFirewallPortFilter -Protocol TCP -LocalPort $Port
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName "LLM Home Server TCP $Port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Any | Out-Null
}
$verifiedRule = Get-NetFirewallRule -Name $ruleName -PolicyStore ActiveStore
$verifiedPort = $verifiedRule | Get-NetFirewallPortFilter
if ([string]$verifiedRule.Enabled -ne 'True' -or [string]$verifiedRule.Direction -ne 'Inbound' -or [string]$verifiedRule.Action -ne 'Allow' -or [string]$verifiedPort.LocalPort -ne [string]$Port) {
    throw '관리 서버 방화벽 규칙을 확인하지 못했습니다.'
}
Write-Output "Verified Windows inbound TCP $Port."
