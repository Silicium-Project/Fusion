@echo off
setlocal
cd /d "%~dp0"

if "%SILICIUM_RELEASE_CHANNEL%"=="" set "SILICIUM_RELEASE_CHANNEL=dev"
if "%SILICIUM_RELEASE_VERSION%"=="" (
  if /I "%SILICIUM_RELEASE_CHANNEL%"=="prod" (
    for /f "usebackq delims=" %%V in (`node -p "require('./src-tauri/tauri.prod.conf.json').version"`) do set "SILICIUM_RELEASE_VERSION=%%V"
  ) else (
    for /f "usebackq delims=" %%V in (`node -p "require('./package.json').version"`) do set "SILICIUM_RELEASE_VERSION=%%V"
  )
)
if "%SILICIUM_RELEASE_BUILD%"=="" set "SILICIUM_RELEASE_BUILD=local"
if "%SILICIUM_UPDATE_MANIFEST_URL%"=="" (
  if /I "%SILICIUM_RELEASE_CHANNEL%"=="prod" (
    set "SILICIUM_UPDATE_MANIFEST_URL=https://vps-910c1dbc.vps.ovh.net/downloads/update-manifest.json"
  ) else (
    set "SILICIUM_UPDATE_MANIFEST_URL=https://10.77.0.1:8443/downloads/update-manifest.json"
  )
)

if /I not "%SILICIUM_SKIP_RUNTIME_PREPARE%"=="1" (
  call npm.cmd run prepare:runtime
  if errorlevel 1 exit /b 1
)

if /I "%SILICIUM_RELEASE_CHANNEL%"=="prod" (
  if "%SILICIUM_TAURI_CONFIG%"=="" (
    call .\node_modules\.bin\tauri.cmd build --bundles nsis --config src-tauri\tauri.prod.conf.json
  ) else (
    call .\node_modules\.bin\tauri.cmd build --bundles nsis --config src-tauri\tauri.prod.conf.json --config "%SILICIUM_TAURI_CONFIG%"
  )
) else (
  if "%SILICIUM_TAURI_CONFIG%"=="" (
    call .\node_modules\.bin\tauri.cmd build --bundles nsis
  ) else (
    call .\node_modules\.bin\tauri.cmd build --bundles nsis --config "%SILICIUM_TAURI_CONFIG%"
  )
)
exit /b %errorlevel%
