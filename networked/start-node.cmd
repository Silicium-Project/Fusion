@echo off
setlocal
set "ROOT=%~dp0..\.."
pushd "%ROOT%"

if exist ".silicium\env\raytracer.env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".silicium\env\raytracer.env") do (
    if /I "%%A"=="SILICIUM_RAYTRACER_BIN" if not defined SILICIUM_RAYTRACER_BIN set "SILICIUM_RAYTRACER_BIN=%%B"
    if /I "%%A"=="SILICIUM_RAYTRACER_ASSETS_DIR" if not defined SILICIUM_RAYTRACER_ASSETS_DIR set "SILICIUM_RAYTRACER_ASSETS_DIR=%%B"
  )
)

if "%~1"=="" (
  echo Usage: demo\networked\start-node.cmd ^<node-id^> ^<roles^> ^<port^> ^<seed-url^> [advertise-host] [mesh-key] [reputation-score]
  echo Example worker: demo\networked\start-node.cmd worker-1 compute 46101 https://vps-910c1dbc.vps.ovh.net/orchestrator 192.168.1.11 demo-mesh 120
  echo Example verifier: demo\networked\start-node.cmd verifier-1 verify 46102 https://vps-910c1dbc.vps.ovh.net/orchestrator 192.168.1.12 demo-mesh 90
  exit /b 2
)

set "NODE_ID=%~1"
set "ROLES=%~2"
set "PORT=%~3"
set "SEED=%~4"
set "ADVERTISE=%~5"
set "MESH=%~6"
set "REPUTATION=%~7"

if "%ROLES%"=="" set "ROLES=compute"
if "%PORT%"=="" set "PORT=46101"
if "%ADVERTISE%"=="" set "ADVERTISE=127.0.0.1"
if "%MESH%"=="" set "MESH=demo-mesh"
if "%REPUTATION%"=="" set "REPUTATION=0"

py silicium node start ^
  --roles "%ROLES%" ^
  --node-id "%NODE_ID%" ^
  --export-dir ".silicium\networked\%NODE_ID%\export" ^
  --state-dir ".silicium\networked\%NODE_ID%\state" ^
  --peer-http-bind 0.0.0.0 ^
  --peer-http-port "%PORT%" ^
  --gossip-enable ^
  --gossip-bind 0.0.0.0 ^
  --gossip-port "%PORT%" ^
  --peer-advertise-host "%ADVERTISE%" ^
  --peer-advertise-port "%PORT%" ^
  --gossip-advertise-host "%ADVERTISE%" ^
  --gossip-advertise-port "%PORT%" ^
  --seed-peers "%SEED%" ^
  --mesh-key "%MESH%" ^
  --reputation-score "%REPUTATION%" ^
  --peer-sync-interval-s 5 ^
  --peer-stale-after-s 15 ^
  --idle-ms 250 ^
  --pull-tasks-enable ^
  --nat-punch-enable

popd
