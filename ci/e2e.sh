#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=infra/bin/i18n.sh
. "$ROOT/infra/bin/i18n.sh"

SUMMARY_PATH="splitter/run_output/demo/summary.json"

log() {
  echo ">> $(sil_i18n_lookup "$1")"
}

have_docker() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

log "ci.e2e.build_demo"
make demo

log "ci.e2e.worker_emu"
./worker/worker --summary "$SUMMARY_PATH" --mode emu --output json >/dev/null

log "ci.e2e.worker_native"
./worker/worker --summary "$SUMMARY_PATH" --mode native --output json >/dev/null

if have_docker; then
  if ! docker image inspect dynamorio-runner >/dev/null 2>&1; then
    log "ci.e2e.build_dynamo"
    docker build -t dynamorio-runner -f infra/docker/dynamorio-runner/Dockerfile .
  fi
  log "ci.e2e.worker_dynamo"
  ./worker/worker --summary "$SUMMARY_PATH" --mode dynamo --runner-binary worker/dynamo_fragment_runner --output json >/dev/null

  log "ci.e2e.proxy_smoke"
  ./silicium smoke
else
  sil_i18n_echo "ci.e2e.warn_no_docker" >&2
fi

log "ci.e2e.python_tests"
python3 -m pip install -r requirements-dev.txt
python3 -m pytest

log "ci.e2e.ok"
