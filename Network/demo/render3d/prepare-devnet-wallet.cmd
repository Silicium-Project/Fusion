@echo off
setlocal
set "DEMO_DIR=%~dp0"
set "NETWORK_DIR=%DEMO_DIR%..\.."
set "SOLANA_LAYER_DIR=%NETWORK_DIR%\solana-layer"
pushd "%SOLANA_LAYER_DIR%" > nul
if "%~1"=="" (
  npx.cmd ts-node scripts/prepare_devnet_wallet.ts "%NETWORK_DIR%\.silicium\solana\id.json"
) else (
  npx.cmd ts-node scripts/prepare_devnet_wallet.ts %*
)
set "STATUS=%ERRORLEVEL%"
popd > nul
exit /b %STATUS%
