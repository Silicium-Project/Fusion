#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SUMMARY_PATH="splitter/run_output/demo/summary.json"

log() {
  echo ">> $*"
}

have_docker() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

log "Build and run splitter demo"
make demo

log "Worker run (emu)"
./worker/worker --summary "$SUMMARY_PATH" --mode emu --output json >/dev/null

log "Worker run (native)"
./worker/worker --summary "$SUMMARY_PATH" --mode native --output json >/dev/null

if have_docker; then
  if ! docker image inspect dynamorio-runner >/dev/null 2>&1; then
    log "Building dynamorio-runner image"
    docker build -t dynamorio-runner -f infra/docker/dynamorio-runner/Dockerfile .
  fi
  log "Worker run (dynamo)"
  ./worker/worker --summary "$SUMMARY_PATH" --mode dynamo --runner-binary worker/dynamo_fragment_runner --output json >/dev/null

  log "Proxy smoke test"
  ./silicium smoke
else
  echo "[WARN] Docker indisponible, ÃƒÂ©tapes dynamo et proxy ignorÃƒÂ©es" >&2
fi

log "Python tests"
python3 -m pip install -r requirements-dev.txt
python3 -m pytest

log "E2E pipeline OK"
