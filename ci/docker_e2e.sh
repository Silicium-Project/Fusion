#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/ci/docker-compose.e2e.yml"
MANIFEST_FILE="$ROOT/ci/e2e-manifest.json"
E2E_EXPORT_DIR="$(mktemp -d -t silicium-e2e-XXXXXX)"
E2E_TIMEOUT_S="${E2E_TIMEOUT_S:-2400}"
E2E_WAIT_S="${E2E_WAIT_S:-1200}"
DOCKER_CLIENT_TIMEOUT="${DOCKER_CLIENT_TIMEOUT:-1200}"
COMPOSE_HTTP_TIMEOUT="${COMPOSE_HTTP_TIMEOUT:-1200}"

cd "$ROOT"

export E2E_EXPORT_DIR
export DOCKER_CLIENT_TIMEOUT
export COMPOSE_HTTP_TIMEOUT

log() {
  printf '==> %s\n' "$*"
}

cleanup() {
  local status=$?
  set +e
  if [ -f "$COMPOSE_FILE" ]; then
    if [ "$status" -ne 0 ]; then
      echo "---- docker compose ps"
      docker compose -f "$COMPOSE_FILE" ps || true
      echo "---- docker compose logs (tail 200)"
      docker compose -f "$COMPOSE_FILE" logs --no-color --timestamps --tail 200 || true
    fi
    docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -rf "$E2E_EXPORT_DIR" >/dev/null 2>&1 || true
  exit "$status"
}

trap cleanup EXIT

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not available on this runner." >&2
  exit 1
fi

mkdir -p "$E2E_EXPORT_DIR"
TASK_PREFIX="docker-$(date -u +%Y%m%d%H%M%S)-$$"
export E2E_TASK_PREFIX="$TASK_PREFIX"

log "Starting E2E compose stack"
docker compose -f "$COMPOSE_FILE" up -d --build --remove-orphans

log "Waiting for orchestrator health"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:46100/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:46100/health" >/dev/null

log "Waiting for MCP health"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:9765/healthz" >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:9765/healthz" >/dev/null

log "Checking python3 in runtime containers"
for service in orchestrator backend mcp worker-compute-a worker-compute-b worker-verify-a worker-verify-b; do
  docker compose -f "$COMPOSE_FILE" exec -T "$service" python3 --version >/dev/null
done

log "Submitting tasks through web and RPC"
python3 "$ROOT/tools/e2e_scenario.py" \
  --web-url "http://127.0.0.1:9765/tools" \
  --rpc-url "tcp://127.0.0.1:9770" \
  --data-dir "$E2E_EXPORT_DIR/mcp" \
  --manifest "$MANIFEST_FILE" \
  --task-prefix "$TASK_PREFIX" \
  --expected-transport "docker-e2e" \
  --timeout-s "$E2E_TIMEOUT_S" \
  --report "$E2E_EXPORT_DIR/validation.json"

log "Waiting for task results"
python3 - <<'PY'
from __future__ import annotations

import json
import os
import time
from pathlib import Path

export_dir = Path(os.environ["E2E_EXPORT_DIR"])
task_prefix = os.environ["E2E_TASK_PREFIX"]
task_ids = [
    f"{task_prefix}-web-compute-a",
    f"{task_prefix}-web-compute-b",
    f"{task_prefix}-web-compute-c",
    f"{task_prefix}-web-compute-d",
    f"{task_prefix}-rpc-verify-a",
    f"{task_prefix}-rpc-verify-b",
    f"{task_prefix}-rpc-verify-c",
    f"{task_prefix}-rpc-verify-d",
]

deadline = time.monotonic() + float(os.environ.get("E2E_WAIT_S", "600"))
for task_id in task_ids:
    result_path = export_dir / "mcp" / f"result.{task_id}.json"
    while not result_path.exists():
        if time.monotonic() > deadline:
            raise SystemExit(f"missing result for {task_id}: {result_path}")
        time.sleep(0.25)

reports: dict[str, dict[str, object]] = {}
for task_id in task_ids:
    result_path = export_dir / "mcp" / f"result.{task_id}.json"
    task_path = export_dir / "mcp" / "tasks" / f"{task_id}.json"
    report = json.loads(result_path.read_text(encoding="utf-8"))
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert report["success"] is True, report
    assert str(report["handled_by"]).strip(), report
    assert report["worker_role"] in {"compute", "verify"}, report
    assert task["status"] == "completed", task
    assert task["handled_by"] == report["handled_by"], task
    reports[task_id] = {
        "result": report,
        "task": task,
    }

backend_probe = json.loads((export_dir / "backend-probe.json").read_text(encoding="utf-8"))
assert backend_probe["ok"] is True, backend_probe
assert backend_probe["resolved_addresses"], backend_probe

validation = json.loads((export_dir / "validation.json").read_text(encoding="utf-8"))
assert validation["ok"] is True, validation
assert sorted(validation["tasks"].keys()) == sorted(task_ids), validation
worker_counts = validation.get("worker_counts", {})
assert worker_counts.get("compute", {}).get("worker-compute-a") == 2, worker_counts
assert worker_counts.get("compute", {}).get("worker-compute-b") == 2, worker_counts
assert worker_counts.get("verify", {}).get("worker-verify-a") == 2, worker_counts
assert worker_counts.get("verify", {}).get("worker-verify-b") == 2, worker_counts

print(json.dumps(reports, indent=2, sort_keys=True))
print(json.dumps({"backend_probe": backend_probe}, indent=2, sort_keys=True))
print(json.dumps({"validation": validation}, indent=2, sort_keys=True))
PY

log "E2E compose stack"
docker compose -f "$COMPOSE_FILE" ps

log "E2E completed successfully"
