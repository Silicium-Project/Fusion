#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
E2E_COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.e2e.yml"
MANIFEST_FILE="$ROOT/Network/ci/e2e-manifest.json"
DATA_DIR="/var/lib/silicium/network/orchestrator/export"
EXPERIMENT_API_ENV="/etc/silicium/experiment-api.env"
E2E_TIMEOUT_S="${E2E_TIMEOUT_S:-2400}"
E2E_WAIT_S="${E2E_WAIT_S:-1200}"
DOCKER_CLIENT_TIMEOUT="${DOCKER_CLIENT_TIMEOUT:-1200}"
COMPOSE_HTTP_TIMEOUT="${COMPOSE_HTTP_TIMEOUT:-1200}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/compose/e2e.sh $ROOT" >&2
  exit 1
fi

[[ -f "$E2E_COMPOSE_FILE" ]] || { echo "Missing e2e compose file: $E2E_COMPOSE_FILE" >&2; exit 1; }
[[ -d "$ROOT/Network" ]] || { echo "Missing Network checkout: $ROOT/Network" >&2; exit 1; }
[[ -f "$EXPERIMENT_API_ENV" ]] || { echo "Missing experiment API env: $EXPERIMENT_API_ENV" >&2; exit 1; }

set -a
. "$EXPERIMENT_API_ENV"
set +a
if [[ -z "${SILICIUM_MCP_TOKEN:-}" ]]; then
  echo "Missing SILICIUM_MCP_TOKEN in $EXPERIMENT_API_ENV" >&2
  exit 1
fi

healthz_headers=(-H "Authorization: Bearer ${SILICIUM_MCP_TOKEN}")
export DOCKER_CLIENT_TIMEOUT
export COMPOSE_HTTP_TIMEOUT

log() {
  printf '==> %s\n' "$*"
}

cleanup() {
  local status=$?
  set +e
  if [ "$status" -ne 0 ]; then
    echo "---- docker compose ps"
    docker compose -f "$E2E_COMPOSE_FILE" ps || true
    echo "---- docker compose logs (tail 200)"
    docker compose -f "$E2E_COMPOSE_FILE" logs --no-color --timestamps --tail 200 || true
  fi
  docker compose -f "$E2E_COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
  exit "$status"
}

trap cleanup EXIT

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not available on this host." >&2
  exit 1
fi

mkdir -p "$DATA_DIR"
TASK_PREFIX="vps-$(date -u +%Y%m%d%H%M%S)-$$"
export E2E_TASK_PREFIX="$TASK_PREFIX"

log "Starting VPS e2e worker overlay"
docker compose -f "$E2E_COMPOSE_FILE" up -d --remove-orphans \
  e2e-worker-compute-a \
  e2e-worker-compute-b \
  e2e-worker-verify-a \
  e2e-worker-verify-b

log "Waiting for local services"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:46100/health" >/dev/null && \
     curl -fsS "${healthz_headers[@]}" "http://127.0.0.1:46110/healthz" >/dev/null && \
     curl -fsS "http://127.0.0.1:8080/health" >/dev/null && \
     curl -fsS "http://127.0.0.1:3000" >/dev/null; then
    break
  fi
  sleep 2
done
curl -fsS "http://127.0.0.1:46100/health" >/dev/null
curl -fsS "${healthz_headers[@]}" "http://127.0.0.1:46110/healthz" >/dev/null
curl -fsS "http://127.0.0.1:8080/health" >/dev/null
curl -fsS "http://127.0.0.1:3000" >/dev/null

log "Probing orchestrator gossip"
python3 "$ROOT/Network/tools/e2e_vps_probe.py" \
  --control-url "http://127.0.0.1:46100/gossip/publish" \
  --output /tmp/silicium-vps-backend-probe.json \
  --probe-id "vps-e2e-backend" \
  --retries 120 \
  --delay-s 2

log "Submitting tasks through web and RPC"
python3 "$ROOT/Network/tools/e2e_scenario.py" \
  --web-url "http://127.0.0.1:46110/tools" \
  --rpc-url "tcp://127.0.0.1:9770" \
  --auth-token "$SILICIUM_MCP_TOKEN" \
  --data-dir "$DATA_DIR" \
  --manifest "$MANIFEST_FILE" \
  --task-prefix "$TASK_PREFIX" \
  --expected-transport "vps-compose" \
  --timeout-s "$E2E_TIMEOUT_S" \
  --report /tmp/silicium-vps-validation.json

python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

validation = json.loads(Path("/tmp/silicium-vps-validation.json").read_text(encoding="utf-8"))
probe = json.loads(Path("/tmp/silicium-vps-backend-probe.json").read_text(encoding="utf-8"))
task_prefix = os.environ["E2E_TASK_PREFIX"]

assert probe["ok"] is True, probe
assert probe["resolved_addresses"], probe

task_ids = [
    "web-compute-a",
    "web-compute-b",
    "web-compute-c",
    "web-compute-d",
    "rpc-verify-a",
    "rpc-verify-b",
    "rpc-verify-c",
    "rpc-verify-d",
]
prefixed_task_ids = [f"{task_prefix}-{task_id}" for task_id in task_ids]

assert validation["ok"] is True, validation
assert sorted(validation["tasks"].keys()) == sorted(prefixed_task_ids), validation
worker_counts = validation.get("worker_counts", {})
assert worker_counts.get("compute", {}).get("worker-compute-a") == 2, worker_counts
assert worker_counts.get("compute", {}).get("worker-compute-b") == 2, worker_counts
assert worker_counts.get("verify", {}).get("worker-verify-a") == 2, worker_counts
assert worker_counts.get("verify", {}).get("worker-verify-b") == 2, worker_counts

for task_id, report in validation["tasks"].items():
    task = report["task"]
    result = report["result"]
    assert report["queue"]["status"] == "queued", report
    assert task["status"] == "completed", report
    assert task["handled_by"] == result["handled_by"], report
    assert result["success"] is True, report
    assert result["transport"] == "vps-compose", report
    assert str(task["handled_by"]).startswith("worker-"), report
PY

log "VPS e2e stack"
docker compose -f "$E2E_COMPOSE_FILE" ps

log "VPS e2e completed successfully"
