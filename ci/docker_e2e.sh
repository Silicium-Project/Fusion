#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/ci/docker-compose.e2e.yml"
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
MANIFEST_FILE="$ROOT/ci/e2e-manifest.json"
E2E_EXPORT_DIR=""
E2E_TIMEOUT_S="${E2E_TIMEOUT_S:-2400}"
E2E_WAIT_S="${E2E_WAIT_S:-1200}"
DOCKER_CLIENT_TIMEOUT="${DOCKER_CLIENT_TIMEOUT:-1200}"
COMPOSE_HTTP_TIMEOUT="${COMPOSE_HTTP_TIMEOUT:-1200}"
PYTHON_BIN="${pythonLocation:-}"
if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN/bin/python" ]; then
  PYTHON_BIN="$PYTHON_BIN/bin/python"
  export LD_LIBRARY_PATH="${pythonLocation}/lib:${LD_LIBRARY_PATH:-}"
else
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    PYTHON_BIN="python"
  fi
fi

if command -v docker >/dev/null 2>&1; then
  DOCKER_BIN="$(command -v docker)"
elif command -v docker.exe >/dev/null 2>&1; then
  DOCKER_BIN="$(command -v docker.exe)"
else
  DOCKER_BIN="docker"
fi

cd "$ROOT"

export E2E_EXPORT_DIR
export DOCKER_CLIENT_TIMEOUT
export COMPOSE_HTTP_TIMEOUT

log() {
  printf '==> %s\n' "$*"
}

pick_free_ports() {
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command '$ports = for ($i = 0; $i -lt 4; $i++) { $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); $listener.Start(); $port = $listener.LocalEndpoint.Port; $listener.Stop(); $port }; $ports -join " "' | tr -d '\r'
  else
    "$PYTHON_BIN" -c 'import socket,sys; ports=[]; 
for _ in range(4):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    ports.append(str(sock.getsockname()[1]))
    sock.close()
sys.stdout.write(" ".join(ports))'
  fi
}

cleanup() {
  local status=$?
  set +e
  if [ -f "$COMPOSE_FILE" ]; then
    if [ "$status" -ne 0 ]; then
      echo "---- docker compose ps"
      "$DOCKER_BIN" compose "${COMPOSE_ARGS[@]}" ps || true
      echo "---- docker compose logs (tail 200)"
      "$DOCKER_BIN" compose "${COMPOSE_ARGS[@]}" logs --no-color --timestamps --tail 200 || true
    fi
    "$DOCKER_BIN" compose "${COMPOSE_ARGS[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  if [ -n "${E2E_EXPORT_DIR:-}" ]; then
    rm -rf "$E2E_EXPORT_DIR" >/dev/null 2>&1 || true
  fi
  exit "$status"
}

trap cleanup EXIT

if [ "${SILICIUM_E2E_DOCKER_GROUP_REEXEC:-0}" = "1" ]; then
  log "Using Docker wrapper prepared by CI"
elif ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  if [ "${SILICIUM_E2E_DOCKER_GROUP_REEXEC:-0}" != "1" ] && command -v sg >/dev/null 2>&1; then
    current_user="$(id -un)"
    docker_members="$(getent group docker 2>/dev/null | awk -F: '{print $4}' | tr ',' '\n' || true)"
    if printf '%s\n' "$docker_members" | grep -Fxq "$current_user"; then
      exec sg docker -c "SILICIUM_E2E_DOCKER_GROUP_REEXEC=1 bash '$ROOT/ci/docker_e2e.sh'"
    fi
  fi
  echo "Docker is not available on this runner." >&2
  exit 1
fi

log "Preparing E2E export directory"
E2E_EXPORT_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/silicium-e2e-XXXXXX")"
mkdir -p "$E2E_EXPORT_DIR"
log "E2E export directory: $E2E_EXPORT_DIR"
TASK_PREFIX="docker-$(date -u +%Y%m%d%H%M%S)-$$"
export E2E_TASK_PREFIX="$TASK_PREFIX"
export COMPOSE_PROJECT_NAME="silicium-e2e-${TASK_PREFIX}"
export E2E_COMPOSE_NETWORK="silicium-e2e-${TASK_PREFIX}"

log "Picking E2E host ports"
E2E_HOST_PORTS="$(pick_free_ports)"
read -r E2E_ORCHESTRATOR_HOST_PORT E2E_MCP_HOST_PORT E2E_RPC_HOST_PORT E2E_RPC_EVENTS_HOST_PORT <<<"$E2E_HOST_PORTS"
export E2E_ORCHESTRATOR_HOST_PORT
export E2E_MCP_HOST_PORT
export E2E_RPC_HOST_PORT
export E2E_RPC_EVENTS_HOST_PORT

E2E_ENV_FILE="$E2E_EXPORT_DIR/compose.env"
{
  printf 'COMPOSE_PROJECT_NAME=%s\n' "$COMPOSE_PROJECT_NAME"
  printf 'E2E_COMPOSE_NETWORK=%s\n' "$E2E_COMPOSE_NETWORK"
  printf 'E2E_EXPORT_DIR=%s\n' "$E2E_EXPORT_DIR"
  printf 'E2E_TASK_PREFIX=%s\n' "$E2E_TASK_PREFIX"
  printf 'E2E_ORCHESTRATOR_HOST_PORT=%s\n' "$E2E_ORCHESTRATOR_HOST_PORT"
  printf 'E2E_MCP_HOST_PORT=%s\n' "$E2E_MCP_HOST_PORT"
  printf 'E2E_RPC_HOST_PORT=%s\n' "$E2E_RPC_HOST_PORT"
  printf 'E2E_RPC_EVENTS_HOST_PORT=%s\n' "$E2E_RPC_EVENTS_HOST_PORT"
} >"$E2E_ENV_FILE"
COMPOSE_ARGS=(--env-file "$E2E_ENV_FILE" -f "$COMPOSE_FILE")

log "Using compose project ${COMPOSE_PROJECT_NAME}"
log "Using compose network ${E2E_COMPOSE_NETWORK}"
log "Host ports: orchestrator=${E2E_ORCHESTRATOR_HOST_PORT}, mcp=${E2E_MCP_HOST_PORT}, rpc=${E2E_RPC_HOST_PORT}, rpc-events=${E2E_RPC_EVENTS_HOST_PORT}"

log "Starting E2E compose stack"
if ! "$DOCKER_BIN" compose "${COMPOSE_ARGS[@]}" up -d --build --remove-orphans; then
  log "E2E compose config"
  "$DOCKER_BIN" compose "${COMPOSE_ARGS[@]}" config || true
  exit 1
fi

log "Waiting for orchestrator health"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${E2E_ORCHESTRATOR_HOST_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${E2E_ORCHESTRATOR_HOST_PORT}/health" >/dev/null 2>&1

log "Waiting for MCP health"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${E2E_MCP_HOST_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${E2E_MCP_HOST_PORT}/healthz" >/dev/null 2>&1

log "Checking python3 in runtime containers"
for service in orchestrator backend mcp worker-compute-a worker-compute-b worker-verify-a worker-verify-b; do
  "$DOCKER_BIN" compose "${COMPOSE_ARGS[@]}" exec -T "$service" python3 --version >/dev/null
done

log "Submitting tasks through web and RPC"
"$PYTHON_BIN" "$ROOT/tools/dev/e2e/e2e_scenario.py" \
  --web-url "http://127.0.0.1:${E2E_MCP_HOST_PORT}/tools" \
  --rpc-url "tcp://127.0.0.1:${E2E_RPC_HOST_PORT}" \
  --data-dir "$E2E_EXPORT_DIR/mcp" \
  --manifest "$MANIFEST_FILE" \
  --task-prefix "$TASK_PREFIX" \
  --expected-transport "docker-e2e" \
  --timeout-s "$E2E_TIMEOUT_S" \
  --report "$E2E_EXPORT_DIR/validation.json"

log "Waiting for task results"
"$PYTHON_BIN" - <<'PY'
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
"$DOCKER_BIN" compose "${COMPOSE_ARGS[@]}" ps

log "E2E completed successfully"
