@echo off
setlocal
cd /d "%~dp0"

if not exist ".\dist\index.html" (
  echo Frontend build not found. Run npm.cmd run build first.
  exit /b 1
)

call .\node_modules\.bin\tauri.cmd build --bundles nsis
exit /b %errorlevel%
