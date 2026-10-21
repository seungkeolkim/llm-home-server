@echo off
rem Run this launcher from an elevated Command Prompt.
powershell.exe -NoProfile -File "%~dp0allow-network-access.ps1" %*
exit /b %ERRORLEVEL%
