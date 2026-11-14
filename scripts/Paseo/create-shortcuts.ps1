<#
.SYNOPSIS
사용자 Desktop에 Paseo 전용 ON/OFF 바로가기를 만듭니다.
.DESCRIPTION
끄기는 Paseo daemon과 그 자식 Pi를 종료합니다. 기존 Pi·LLM·LibreChat과 Relay는 유지합니다.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$workspaceDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$desktopDirectory = [Environment]::GetFolderPath('Desktop')
$powerShellExecutablePath = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$paseoRunnerPath = Join-Path $workspaceDirectory 'run-paseo.ps1'
$desktopExecutablePath = Join-Path $workspaceDirectory 'data/Paseo/desktop/0.15.4/Paseo.exe'
$shortcutManager = New-Object -ComObject WScript.Shell

function New-PaseoShortcut {
    <#
    .SYNOPSIS
    작업 위치와 무관하게 실행되는 절대경로 Paseo 바로가기를 기록합니다.
    #>
    param([string]$ShortcutName, [string]$Action, [string]$Description)
    $shortcutPath = Join-Path $desktopDirectory $ShortcutName
    $shortcut = $shortcutManager.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powerShellExecutablePath
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $paseoRunnerPath + '" ' + $Action
    $shortcut.WorkingDirectory = $workspaceDirectory
    $shortcut.WindowStyle = 7
    $shortcut.IconLocation = $desktopExecutablePath + ',0'
    $shortcut.Description = $Description
    $shortcut.Save()
    Write-Output $shortcutPath
}

New-PaseoShortcut -ShortcutName 'Paseo 켜기.lnk' -Action 'desktop' -Description 'Paseo daemon과 Windows Desktop을 시작합니다.'
New-PaseoShortcut -ShortcutName 'Paseo 끄기.lnk' -Action 'stop' -Description 'Paseo 작업과 daemon을 종료합니다. LLM과 Relay는 유지합니다.'
