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
for service in orchestrator backend mcp worker-compute worker-verify; do
  docker compose -f "$COMPOSE_FILE" exec -T "$service" python3 --version >/dev/null
done

log "Submitting tasks through web and RPC"
python3 - <<'PY'
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from tools.rpc_client import RpcClient

web_url = "http://127.0.0.1:9765/tools"
rpc_url = "tcp://127.0.0.1:9770"
export_dir = Path(os.environ["E2E_EXPORT_DIR"])


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


web_task_id = "web-e2e-task"
web_response = post_json(
    web_url,
    {
        "name": "tools.silicium.submit_task",
        "args": {
            "task_id": web_task_id,
            "task": {
                "kind": "compute",
                "payload": "from-web",
                "transport": "web",
            },
            "required_roles": ["compute"],
            "priority": "normal",
        },
    },
)
assert web_response["ok"] is True, web_response
assert web_response["result"]["status"] == "queued", web_response

rpc_task_id = "rpc-e2e-task"
rpc_response = RpcClient(rpc_url, "", timeout_ms=3000).call(
    "task.dispatch",
    {
        "task_id": rpc_task_id,
        "required_roles": ["verify"],
        "priority": "normal",
        "task": {
            "kind": "verify",
            "payload": "from-rpc",
            "transport": "rpc",
        },
    },
)
assert rpc_response["status"] == "dispatched", rpc_response

summary = {
    "web_task_id": web_task_id,
    "rpc_task_id": rpc_task_id,
    "export_dir": str(export_dir),
}
Path(export_dir / "submission-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"web": web_response, "rpc": rpc_response}, indent=2, sort_keys=True))
PY

log "Waiting for task results"
python3 - <<'PY'
from __future__ import annotations

import json
import os
import time
from pathlib import Path

export_dir = Path(os.environ["E2E_EXPORT_DIR"])
expectations = {
    "web-e2e-task": "worker-compute",
    "rpc-e2e-task": "worker-verify",
}

deadline = time.monotonic() + 120.0
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

print(json.dumps(reports, indent=2, sort_keys=True))
print(json.dumps({"backend_probe": backend_probe}, indent=2, sort_keys=True))
PY

log "E2E compose stack"
docker compose -f "$COMPOSE_FILE" ps

log "E2E completed successfully"
