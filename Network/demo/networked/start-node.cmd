@echo off
setlocal
set "ROOT=%~dp0..\.."
pushd "%ROOT%"

if "%~1"=="" (
  echo Usage: demo\networked\start-node.cmd ^<node-id^> ^<roles^> ^<port^> ^<seed-url^> [advertise-host] [mesh-key] [reputation-score]
  echo Example worker: demo\networked\start-node.cmd worker-1 compute 46101 http://192.168.1.10:46100 192.168.1.11 demo-mesh 120
  echo Example verifier: demo\networked\start-node.cmd verifier-1 verify 46102 http://192.168.1.10:46100 192.168.1.12 demo-mesh 90
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
  --peer-advertise-host "%ADVERTISE%" ^
  --peer-advertise-port "%PORT%" ^
  --seed-peers "%SEED%" ^
  --mesh-key "%MESH%" ^
  --reputation-score "%REPUTATION%" ^
  --idle-ms 250

popd
