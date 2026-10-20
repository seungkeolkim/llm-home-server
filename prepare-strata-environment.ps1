<#
.SYNOPSIS
Strata 전용 Python 환경에 dependency와 CUDA runtime을 설치합니다.
#>
[CmdletBinding()]
param(
    [string]$PythonExecutable = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    [string]$DataDirectory = 'C:\Strata-data'
)

$ErrorActionPreference = 'Stop'

function Invoke-CheckedCommand {
    <# .SYNOPSIS 외부 명령 실패 시 준비 작업을 중단합니다. #>
    param([string]$Executable, [string[]]$CommandArguments)
    & $Executable @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Executable $($CommandArguments -join ' ')"
    }
}

function Initialize-DirectRuntimePython {
    <# .SYNOPSIS venv launcher 중계로 PID가 바뀌지 않도록 실행용 interpreter를 venv 내부에 준비합니다. #>
    param([string]$VirtualPython)
    $basePythonExecutable = & $VirtualPython -I -B -c 'import sys; print(sys._base_executable)'
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not resolve the base Python executable.'
    }
    $basePythonDirectory = Split-Path -Parent $basePythonExecutable
    $virtualScriptsDirectory = Split-Path -Parent $VirtualPython
    $runtimeExecutable = Join-Path $virtualScriptsDirectory 'strata-runtime-python.exe'
    $runtimeFiles = @(@{ Source = $basePythonExecutable; Destination = $runtimeExecutable })
    foreach ($runtimeLibrary in (Get-ChildItem -LiteralPath $basePythonDirectory -File)) {
        if ($runtimeLibrary.Name -like 'python3*.dll' -or $runtimeLibrary.Name -like 'vcruntime*.dll') {
            $runtimeFiles += @{ Source = $runtimeLibrary.FullName; Destination = (Join-Path $virtualScriptsDirectory $runtimeLibrary.Name) }
        }
    }
    foreach ($runtimeFile in $runtimeFiles) {
        if ((Test-Path -LiteralPath $runtimeFile.Destination) -and
            (Get-FileHash -LiteralPath $runtimeFile.Source).Hash -eq (Get-FileHash -LiteralPath $runtimeFile.Destination).Hash) {
            continue
        }
        Copy-Item -LiteralPath $runtimeFile.Source -Destination $runtimeFile.Destination
    }
    $identityCheck = @'
import subprocess
import sys

child_process = subprocess.Popen(
    [sys.executable, "-I", "-B", "-c", "import os; print(os.getpid())"],
    stdout=subprocess.PIPE,
    text=True,
)
reported_process_id = child_process.communicate()[0]
assert child_process.returncode == 0, "Python child process failed"
assert child_process.pid == int(reported_process_id.strip()), "Python launcher PID mismatch"
'@
    Invoke-CheckedCommand $runtimeExecutable @('-I', '-B', '-c', $identityCheck)
}

$previousEnvironment = @{}
foreach ($environmentName in @('PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE', 'PIP_CACHE_DIR')) {
    $previousEnvironment[$environmentName] = [Environment]::GetEnvironmentVariable($environmentName, 'Process')
}

try {
    $resolvedDataDirectory = [IO.Path]::GetFullPath($DataDirectory)
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PIP_CACHE_DIR = Join-Path $resolvedDataDirectory 'cache\pip'
    $virtualPython = Join-Path $PSScriptRoot '.venv\Strata\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $virtualPython)) {
        Invoke-CheckedCommand $PythonExecutable @('-I', '-B', '-m', 'venv', (Join-Path $PSScriptRoot '.venv\Strata'))
    }
    Initialize-DirectRuntimePython $virtualPython
    Invoke-CheckedCommand $virtualPython @('-I', '-B', '-m', 'pip', 'install', '-r', (Join-Path $PSScriptRoot 'requirements\Strata\runtime.txt'))
    Invoke-CheckedCommand $virtualPython @('-I', '-B', '-m', 'pip', 'check')
    Invoke-CheckedCommand $virtualPython @('-I', '-B', (Join-Path $PSScriptRoot 'scripts\Strata\strata_runner.py'), 'prepare', '--data-directory', $resolvedDataDirectory)
}
finally {
    foreach ($environmentName in $previousEnvironment.Keys) {
        if ($null -eq $previousEnvironment[$environmentName]) {
            Remove-Item -LiteralPath "Env:$environmentName" -ErrorAction SilentlyContinue
        }
        else {
            [Environment]::SetEnvironmentVariable($environmentName, $previousEnvironment[$environmentName], 'Process')
        }
    }
}
