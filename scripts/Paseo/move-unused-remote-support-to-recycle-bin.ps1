<#
.SYNOPSIS
Paseo에서 사용하지 않는 Remote Pi 설치 파일과 이전 Pi Remote APK를 휴지통으로 옮깁니다.
.DESCRIPTION
기본 동작은 대상 표시입니다. -Execute를 지정하면 휴지통으로 이동합니다.
Paseo와 공유하는 Caddy 설정·인증서·network·Pi SDK·gateway·Session은 대상에서 제외합니다.
.EXAMPLE
.\scripts\Paseo\move-unused-remote-support-to-recycle-bin.ps1
.EXAMPLE
.\scripts\Paseo\move-unused-remote-support-to-recycle-bin.ps1 -Execute
#>
[CmdletBinding()]
param([switch]$Execute)
$ErrorActionPreference = 'Stop'
$workspaceDirectory = [IO.Path]::GetFullPath((Split-Path (Split-Path $PSScriptRoot -Parent) -Parent))
$remoteHomeDirectory = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.pi/remote'))
$relativeTargets = @(
    'runtime/PiCodingAgent/agent/extensions/remote-pi.ts'
    'config/RemotePi/remote-pi.local.json'
    'config/RemotePi/remote-pi.local.json.template'
    'requirements/RemotePi'
    'scripts/RemotePi'
    'data/RemotePi'
    'runtime/RemotePi'
    'data/PiCodingAgent/downloads/pi-remote-0.7.7-android-arm64.apk'
    'scripts/PiCodingAgent/verify_android_apk.py'
)

function Get-VerifiedRemovalTarget {
    <#
    .SYNOPSIS
    고정 목록의 경로만 허용하고 링크를 통한 삭제 범위 확장을 거부합니다.
    #>
    param([string]$AbsolutePath, [string]$AllowedDirectory)
    $resolvedPath = [IO.Path]::GetFullPath($AbsolutePath)
    $directoryPrefix = $AllowedDirectory.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedPath.StartsWith($directoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "허용된 디렉터리 밖의 삭제 대상입니다: $resolvedPath"
    }
    if (-not (Test-Path -LiteralPath $resolvedPath)) { return }
    if ((Get-Item -LiteralPath $AllowedDirectory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "허용된 디렉터리가 링크입니다: $AllowedDirectory"
    }
    $targetItem = Get-Item -LiteralPath $resolvedPath -Force
    $ancestorPath = $targetItem.FullName
    while ($ancestorPath -ne $AllowedDirectory) {
        $ancestorItem = Get-Item -LiteralPath $ancestorPath -Force
        if ($ancestorItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "링크가 포함된 삭제 대상은 처리하지 않습니다: $ancestorPath"
        }
        $ancestorPath = Split-Path $ancestorPath -Parent
    }
    if ($targetItem.PSIsContainer) {
        $nestedLinks = @(Get-ChildItem -LiteralPath $resolvedPath -Recurse -Force -Attributes ReparsePoint)
        if ($nestedLinks.Count -gt 0) { throw "삭제 대상 내부에 링크가 있습니다: $resolvedPath" }
    }
    return $targetItem
}

$verifiedTargets = @()
foreach ($relativeTarget in $relativeTargets) {
    $absoluteTarget = [IO.Path]::GetFullPath((Join-Path $workspaceDirectory $relativeTarget))
    $targetItem = Get-VerifiedRemovalTarget -AbsolutePath $absoluteTarget -AllowedDirectory $workspaceDirectory
    if ($null -ne $targetItem) { $verifiedTargets += $targetItem }
}
$remoteHomeParent = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.pi'))
$remoteHomeTarget = Get-VerifiedRemovalTarget -AbsolutePath $remoteHomeDirectory -AllowedDirectory $remoteHomeParent
if ($null -ne $remoteHomeTarget) { $verifiedTargets += $remoteHomeTarget }

$protectedPaths = @(
    'config/RemotePi/Caddyfile'
    'config/RemotePi/compose.yaml'
    'config/RemotePi/.env.local'
    'config/Paseo/paseo.local.json'
    'data/Paseo/home/config.json'
    'data/Paseo/home/daemon-keypair.json'
    'runtime/Paseo/agent/settings.json'
    'runtime/Paseo/agent/models.json'
    'runtime/PiCodingAgent/agent/settings.json'
    'runtime/PiCodingAgent/agent/models.json'
)
$protectedHashes = @{}
foreach ($relativePath in $protectedPaths) {
    $absolutePath = Join-Path $workspaceDirectory $relativePath
    $protectedHashes[$absolutePath] = (Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256).Hash
}

foreach ($targetItem in $verifiedTargets) {
    Write-Output $targetItem.FullName
}
if (-not $Execute) {
    Write-Output '확인된 이동 대상입니다. 휴지통으로 옮기려면 -Execute를 지정해 주세요.'
    return
}

Add-Type -AssemblyName Microsoft.VisualBasic
foreach ($targetItem in $verifiedTargets) {
    if ($targetItem.PSIsContainer) {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
            $targetItem.FullName,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
        )
    }
    else {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
            $targetItem.FullName,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
        )
    }
}
foreach ($absolutePath in $protectedHashes.Keys) {
    if ((Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256).Hash -ne $protectedHashes[$absolutePath]) {
        throw "공유 설정이 변경됐습니다: $absolutePath"
    }
}
$statusDirectory = Join-Path $workspaceDirectory 'data/Paseo/cleanup/remote-support'
New-Item -ItemType Directory -Path $statusDirectory -Force | Out-Null
$result = @{ completed_at = [DateTime]::UtcNow.ToString('o'); recycled_paths = @($verifiedTargets.FullName); shared_files_unchanged = $true }
[IO.File]::WriteAllText((Join-Path $statusDirectory 'file-recycling.json'), ($result | ConvertTo-Json -Depth 4))
Write-Output 'Remote Pi 전용 파일을 휴지통으로 옮겼습니다. Paseo 공유 설정은 그대로입니다.'
