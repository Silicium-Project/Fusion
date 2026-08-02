#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/ci/docker-compose.e2e.yml"
E2E_EXPORT_DIR="$(mktemp -d -t silicium-e2e-XXXXXX)"

cd "$ROOT"

export E2E_EXPORT_DIR

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
  --expected-transport "docker-e2e" \
  --report "$E2E_EXPORT_DIR/validation.json"

log "Waiting for task results"
python3 - <<'PY'
from __future__ import annotations

import json
import os
import time
from pathlib import Path

export_dir = Path(os.environ["E2E_EXPORT_DIR"])
expectations = {
    "web-compute-a": "worker-compute-a",
    "web-compute-b": "worker-compute-b",
    "rpc-verify-a": "worker-verify-a",
    "rpc-verify-b": "worker-verify-b",
}

deadline = time.monotonic() + 180.0
for task_id in expectations:
    result_path = export_dir / "mcp" / f"result.{task_id}.json"
    while not result_path.exists():
        if time.monotonic() > deadline:
            raise SystemExit(f"missing result for {task_id}: {result_path}")
        time.sleep(0.25)

reports: dict[str, dict[str, object]] = {}
for task_id, worker_id in expectations.items():
    result_path = export_dir / "mcp" / f"result.{task_id}.json"
    task_path = export_dir / "mcp" / "tasks" / f"{task_id}.json"
    report = json.loads(result_path.read_text(encoding="utf-8"))
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert report["success"] is True, report
    assert report["handled_by"] == worker_id, report
    assert report["worker_role"] in {"compute", "verify"}, report
    assert task["status"] == "completed", task
    assert task["handled_by"] == worker_id, task
    reports[task_id] = {
        "result": report,
        "task": task,
    }

backend_probe = json.loads((export_dir / "backend-probe.json").read_text(encoding="utf-8"))
assert backend_probe["ok"] is True, backend_probe
assert backend_probe["resolved_addresses"], backend_probe

validation = json.loads((export_dir / "validation.json").read_text(encoding="utf-8"))
assert validation["ok"] is True, validation
assert sorted(validation["tasks"].keys()) == sorted(expectations.keys()), validation

print(json.dumps(reports, indent=2, sort_keys=True))
print(json.dumps({"backend_probe": backend_probe}, indent=2, sort_keys=True))
print(json.dumps({"validation": validation}, indent=2, sort_keys=True))
PY

log "E2E compose stack"
docker compose -f "$COMPOSE_FILE" ps

log "E2E completed successfully"
