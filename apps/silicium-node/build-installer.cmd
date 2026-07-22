@echo off
setlocal
cd /d "%~dp0"

if "%SILICIUM_RELEASE_CHANNEL%"=="" set "SILICIUM_RELEASE_CHANNEL=dev"
if "%SILICIUM_RELEASE_VERSION%"=="" (
  if /I "%SILICIUM_RELEASE_CHANNEL%"=="prod" (
    set "SILICIUM_RELEASE_VERSION=0.2.16"
  ) else (
    set "SILICIUM_RELEASE_VERSION=0.2.9-dev.10"
  )
)
if "%SILICIUM_RELEASE_BUILD%"=="" set "SILICIUM_RELEASE_BUILD=local"

if /I not "%SILICIUM_SKIP_RUNTIME_PREPARE%"=="1" (
  call npm.cmd run prepare:runtime
  if errorlevel 1 exit /b 1
)

if /I "%SILICIUM_RELEASE_CHANNEL%"=="prod" (
  call .\node_modules\.bin\tauri.cmd build --bundles nsis --config src-tauri\tauri.prod.conf.json
) else (
  call .\node_modules\.bin\tauri.cmd build --bundles nsis
)
exit /b %errorlevel%
