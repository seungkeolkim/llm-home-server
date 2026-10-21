@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0allow-network-access.ps1"
exit /b %errorlevel%
