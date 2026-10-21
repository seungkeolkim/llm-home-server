<#
.SYNOPSIS
실제 방화벽을 변경하지 않고 운영 스크립트의 성공과 실패 경로를 검증합니다.
#>
[CmdletBinding()]
param(
    [ValidateSet('new_native', 'existing_native', 'access_denied', 'bad_verification')]
    [string]$Scenario = 'new_native',
    [int]$Port = 8588
)
$script:testScenario = $Scenario
$script:nativeRuleCreated = $false
function Get-NetFirewallRule {
    <# .SYNOPSIS Return the existing Windows rule without accessing the firewall. #>
    param($Name, $PolicyStore)
    [pscustomobject]@{Name=$Name;Enabled='True';Direction='Inbound';Action='Allow'}
}
function Set-NetFirewallRule {
    <# .SYNOPSIS Simulate a successful Windows rule update. #>
    param($Name, $Enabled, $Direction, $Action, $Protocol, $LocalPort, $Profile)
}
function New-NetFirewallRule {
    <# .SYNOPSIS Reject unexpected Windows rule creation in this fixture. #>
    throw 'Unexpected Windows rule creation'
}
function Get-NetFirewallPortFilter {
    <# .SYNOPSIS Return the expected Windows port for verification. #>
    param([Parameter(ValueFromPipeline=$true)]$InputObject)
    process { [pscustomobject]@{LocalPort='8588';Protocol='TCP'} }
}
function Get-NetFirewallHyperVRule {
    <# .SYNOPSIS Model inherited Windows rules separately from native WSL rules. #>
    param($Name, $PolicyStore)
    if ($Name -eq 'StrataLibreChatTcp8588') {
        return [pscustomobject]@{Name=$Name;PolicyStoreSourceType='HostFirewallLocal';VMCreatorId='Any'}
    }
    if ($script:nativeRuleCreated -or $script:testScenario -eq 'existing_native') {
        $reportedPort = '8588'
        if ($script:testScenario -eq 'bad_verification') { $reportedPort = '9999' }
        return [pscustomobject]@{Name=$Name;Enabled='True';Direction='Inbound';Action='Allow';Protocol='TCP';LocalPorts=$reportedPort;VMCreatorId='{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}';PolicyStoreSourceType='Local'}
    }
}
function New-NetFirewallHyperVRule {
    <# .SYNOPSIS Validate the native rule identity and simulate creation or denial. #>
    param($Name, $PolicyStore, $DisplayName, $Direction, $VMCreatorId, $Enabled, $Action, $Protocol, $LocalPorts)
    if ($script:testScenario -eq 'access_denied') { throw 'Simulated Access denied' }
    if ($Name -ne 'StrataLibreChatWslTcp8588' -or $VMCreatorId -ne '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}') { throw 'Incorrect native-rule identity' }
    $script:nativeRuleCreated = $true
}
function Set-NetFirewallHyperVRule {
    <# .SYNOPSIS Ensure inherited Windows rules are never modified through Hyper-V. #>
    param($Name, $PolicyStore, $VMCreatorId, $Enabled, $Direction, $Action, $Protocol, $LocalPorts)
    if ($Name -ne 'StrataLibreChatWslTcp8588') { throw 'Attempted to modify an inherited rule' }
}
$firewallScriptPath = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'scripts\LibreChat\allow-network-access.ps1'
$firewallScriptText = [IO.File]::ReadAllText($firewallScriptPath)
# 관리자 권한 선언만 제외하고 실제 운영 로직을 mock cmdlet로 실행합니다.
$firewallScriptText = $firewallScriptText -replace '(?m)^#Requires -RunAsAdministrator\r?\n', ''
& ([scriptblock]::Create($firewallScriptText)) -Port $Port