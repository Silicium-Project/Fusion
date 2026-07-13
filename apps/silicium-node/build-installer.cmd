@echo off
setlocal
cd /d "%~dp0"

call .\node_modules\.bin\tauri.cmd build --bundles nsis
exit /b %errorlevel%
