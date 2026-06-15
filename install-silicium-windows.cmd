@echo off
setlocal
set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%install-silicium-windows.ps1" %*
exit /b %ERRORLEVEL%
