<#
.SYNOPSIS
검증한 공식 Release에서 Windows Portable EXE를 내려받고 hash를 대조합니다.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$workspaceDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifestPath = Join-Path $workspaceDirectory 'config\PiCodingAgent\desktop-release-manifest.json'
$releaseManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$downloadDirectory = Join-Path $workspaceDirectory 'data\PiCodingAgent\downloads'
New-Item -ItemType Directory -Path $downloadDirectory -Force | Out-Null
foreach ($releaseAsset in $releaseManifest.assets) {
    if ([IO.Path]::GetFileName($releaseAsset.name) -ne $releaseAsset.name) {
        throw 'Release asset 파일 이름이 올바르지 않습니다.'
    }
    $downloadPath = Join-Path $downloadDirectory $releaseAsset.name
    if (Test-Path -LiteralPath $downloadPath) {
        if ((Get-FileHash -LiteralPath $downloadPath).Hash.ToLowerInvariant() -ne $releaseAsset.sha256) {
            throw "기존 asset hash가 일치하지 않습니다. 파일을 보존하고 중단합니다: $downloadPath"
        }
        Write-Output "검증 완료: $($releaseAsset.name)"
        continue
    }
    $partialDownloadPath = $downloadPath + '.partial'
    Invoke-WebRequest -Uri $releaseAsset.url -OutFile $partialDownloadPath
    if ((Get-FileHash -LiteralPath $partialDownloadPath).Hash.ToLowerInvariant() -ne $releaseAsset.sha256) {
        throw "다운로드 hash가 일치하지 않습니다: $partialDownloadPath"
    }
    Move-Item -LiteralPath $partialDownloadPath -Destination $downloadPath
    Write-Output "다운로드 및 hash 검증 완료: $($releaseAsset.name)"
}
