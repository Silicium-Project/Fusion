@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%"

if exist "config\orchestrator.env" call "scripts\load-env.cmd" "config\orchestrator.env"

set "SCENE=%~1"
set "JOB_ID=%~2"
if "%SCENE%"=="" set "SCENE=workloads\raytracer\examples\silicium-multi-fragment-scene.cfg"
if "%JOB_ID%"=="" set "JOB_ID=raytracer-p2p-%RANDOM%"

if not defined SILICIUM_ORCHESTRATOR_ID set "SILICIUM_ORCHESTRATOR_ID=orchestrator-1"
if not defined SILICIUM_ORCHESTRATOR_HOST set "SILICIUM_ORCHESTRATOR_HOST=127.0.0.1"
if not defined SILICIUM_ORCHESTRATOR_PORT set "SILICIUM_ORCHESTRATOR_PORT=46100"
if not defined SILICIUM_WORKER_URL set "SILICIUM_WORKER_URL=http://127.0.0.1:46101"
if not defined SILICIUM_VERIFIER_URL set "SILICIUM_VERIFIER_URL=http://127.0.0.1:46102"
if not defined SILICIUM_MESH_KEY set "SILICIUM_MESH_KEY=demo-mesh"
if not defined SILICIUM_MIN_COMPUTE_REPUTATION set "SILICIUM_MIN_COMPUTE_REPUTATION=50"
if not defined SILICIUM_MIN_VERIFY_REPUTATION set "SILICIUM_MIN_VERIFY_REPUTATION=40"
if not defined SILICIUM_DEVNET_TRACE set "SILICIUM_DEVNET_TRACE=1"
if not defined SILICIUM_DEVNET_TX_DELAY_MS set "SILICIUM_DEVNET_TX_DELAY_MS=2500"

set "DEVNET_ARGS="
if not "%SILICIUM_DEVNET_TRACE%"=="0" set "DEVNET_ARGS=--devnet-trace --devnet-tx-delay-ms %SILICIUM_DEVNET_TX_DELAY_MS%"

echo Running raytracer P2P job %JOB_ID%
echo   orchestrator: %SILICIUM_ORCHESTRATOR_HOST%:%SILICIUM_ORCHESTRATOR_PORT%
echo   peers:        %SILICIUM_WORKER_URL%,%SILICIUM_VERIFIER_URL%

py workloads\raytracer\run_network_job.py "%SCENE%" ^
  --job-id "%JOB_ID%" ^
  --node-mode network ^
  --network-node-id "%SILICIUM_ORCHESTRATOR_ID%" ^
  --network-port "%SILICIUM_ORCHESTRATOR_PORT%" ^
  --network-advertise-host "%SILICIUM_ORCHESTRATOR_HOST%" ^
  --network-advertise-port "%SILICIUM_ORCHESTRATOR_PORT%" ^
  --network-seed-peers "%SILICIUM_WORKER_URL%,%SILICIUM_VERIFIER_URL%" ^
  --network-mesh-key "%SILICIUM_MESH_KEY%" ^
  --min-compute-reputation "%SILICIUM_MIN_COMPUTE_REPUTATION%" ^
  --min-verify-reputation "%SILICIUM_MIN_VERIFY_REPUTATION%" ^
  --result-timeout-s 300 ^
  %DEVNET_ARGS%

popd
