@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%"

if exist "config\verifier.env" call "scripts\load-env.cmd" "config\verifier.env"
if "%~1" neq "" set "SILICIUM_ORCHESTRATOR_URL=%~1"
if "%~2" neq "" set "SILICIUM_NODE_ADVERTISE_HOST=%~2"

if not defined SILICIUM_NODE_ID set "SILICIUM_NODE_ID=verifier-1"
if not defined SILICIUM_NODE_ROLES set "SILICIUM_NODE_ROLES=verify"
if not defined SILICIUM_NODE_PORT set "SILICIUM_NODE_PORT=46102"
if not defined SILICIUM_NODE_ADVERTISE_HOST set "SILICIUM_NODE_ADVERTISE_HOST=127.0.0.1"
if not defined SILICIUM_ORCHESTRATOR_URL set "SILICIUM_ORCHESTRATOR_URL=http://127.0.0.1:46100"
if not defined SILICIUM_MESH_KEY set "SILICIUM_MESH_KEY=demo-mesh"
if not defined SILICIUM_REPUTATION_SCORE set "SILICIUM_REPUTATION_SCORE=90"

echo Starting Silicium verifier %SILICIUM_NODE_ID%
echo   advertise: %SILICIUM_NODE_ADVERTISE_HOST%:%SILICIUM_NODE_PORT%
echo   seed:      %SILICIUM_ORCHESTRATOR_URL%

call "demo\networked\start-node.cmd" "%SILICIUM_NODE_ID%" "%SILICIUM_NODE_ROLES%" "%SILICIUM_NODE_PORT%" "%SILICIUM_ORCHESTRATOR_URL%" "%SILICIUM_NODE_ADVERTISE_HOST%" "%SILICIUM_MESH_KEY%" "%SILICIUM_REPUTATION_SCORE%"
popd
