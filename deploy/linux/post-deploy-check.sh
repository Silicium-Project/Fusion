#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.yml"
COMPOSE_ENV="/etc/silicium/compose.env"
EXPERIMENT_API_ENV="/etc/silicium/experiment-api.env"
UPDATE_CHANNELS_ENV="/etc/silicium/update-channels.env"
ORCHESTRATOR_ENV="/etc/silicium/orchestrator.env"
RELEASE_MARKER="/var/lib/silicium/releases/current.env"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/post-deploy-check.sh $ROOT" >&2
  exit 1
fi

[[ -f "$COMPOSE_FILE" ]] || { echo "Missing compose file: $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$COMPOSE_ENV" ]] || { echo "Missing compose env: $COMPOSE_ENV" >&2; exit 1; }
[[ -f "$EXPERIMENT_API_ENV" ]] || { echo "Missing experiment API env: $EXPERIMENT_API_ENV" >&2; exit 1; }
[[ -f "$ORCHESTRATOR_ENV" ]] || { echo "Missing orchestrator env: $ORCHESTRATOR_ENV" >&2; exit 1; }
[[ -s "$RELEASE_MARKER" ]] || { echo "Missing release marker: $RELEASE_MARKER" >&2; exit 1; }

set -a
. "$ORCHESTRATOR_ENV"
set +a

set -a
. "$RELEASE_MARKER"
set +a
for release_key in SILICIUM_RELEASE_VERSION SILICIUM_RELEASE_CHANNEL SILICIUM_RELEASE_BUILD; do
  if [[ -z "${!release_key:-}" ]]; then
    echo "Missing $release_key in $RELEASE_MARKER" >&2
    exit 1
  fi
done

if [[ -f "$UPDATE_CHANNELS_ENV" ]]; then
  set -a
  . "$UPDATE_CHANNELS_ENV"
  set +a
fi

set -a
. "$EXPERIMENT_API_ENV"
set +a
if [[ -z "${SILICIUM_MCP_TOKEN:-}" ]]; then
  echo "Missing SILICIUM_MCP_TOKEN in $EXPERIMENT_API_ENV" >&2
  exit 1
fi

healthz_headers=(-H "Authorization: Bearer ${SILICIUM_MCP_TOKEN}")

echo "Checking Docker Compose services..."
docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" ps

mapfile -t expected_services < <(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" config --services)
mapfile -t running_services < <(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" ps --services --filter status=running)

for service in "${expected_services[@]}"; do
  found=0
  for running in "${running_services[@]}"; do
    if [[ "$running" == "$service" ]]; then
      found=1
      break
    fi
  done
  if [[ "$found" -ne 1 ]]; then
    echo "Service is not running: $service" >&2
    exit 1
  fi
done

echo "Checking local HTTP health endpoints..."
curl -fsS --max-time 8 http://127.0.0.1:8080/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:3000 >/dev/null
orchestrator_port="${SILICIUM_NODE_PORT:-46100}"
orchestrator_health=""
for _ in $(seq 1 30); do
  if orchestrator_health="$(curl -fsS --max-time 3 "http://127.0.0.1:${orchestrator_port}/healthz" 2>/dev/null)"; then
    break
  fi
  sleep 2
done
if [[ -z "$orchestrator_health" ]]; then
  echo "The integrated network node did not become reachable on 127.0.0.1:${orchestrator_port}." >&2
  systemctl status --no-pager -l silicium-orchestrator.service >&2 || true
  journalctl -u silicium-orchestrator.service --no-pager -n 100 >&2 || true
  exit 1
fi
if [[ "$orchestrator_health" != *'"service":"network_node"'* ]]; then
  echo "The integrated network node is not serving the orchestrator port: $orchestrator_health" >&2
  exit 1
fi
export_dir="${SILICIUM_EXPORT_DIR:-/var/lib/silicium/network/orchestrator/export}"
heartbeat_file="$export_dir/node.$(printf '%s' "${SILICIUM_NODE_ID:-orchestrator-1}" | tr -c 'A-Za-z0-9_.-' '_').heartbeat.json"
if [[ ! -s "$heartbeat_file" ]]; then
  echo "Missing live orchestrator heartbeat: $heartbeat_file" >&2
  exit 1
fi
if ! python3 - "$heartbeat_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as heartbeat_stream:
    heartbeat = json.load(heartbeat_stream)
roles = {str(role).strip().lower() for role in heartbeat.get("roles", [])}
raise SystemExit(0 if roles == {"resource", "storage"} else 1)
PY
then
  echo "The orchestrator heartbeat advertises workload roles; expected only resource,storage: $heartbeat_file" >&2
  exit 1
fi
if ! python3 - "$heartbeat_file" "$SILICIUM_RELEASE_VERSION" "$SILICIUM_RELEASE_CHANNEL" "$SILICIUM_RELEASE_BUILD" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as heartbeat_stream:
    heartbeat = json.load(heartbeat_stream)

expected = {
    "app_version": sys.argv[2],
    "release_channel": sys.argv[3],
    "release_build": sys.argv[4],
}
mismatches = [
    f"{key}={heartbeat.get(key)!r} (expected {value!r})"
    for key, value in expected.items()
    if str(heartbeat.get(key, "")) != value
]
if mismatches:
    print("Orchestrator heartbeat release mismatch: " + ", ".join(mismatches), file=sys.stderr)
    raise SystemExit(1)
PY
then
  echo "The orchestrator service is not running the marked release: $heartbeat_file" >&2
  exit 1
fi
if systemctl cat silicium-experiment-api.service >/dev/null 2>&1; then
  if ! systemctl is-active --quiet silicium-experiment-api.service; then
    echo "silicium-experiment-api.service is installed but not active." >&2
    systemctl status --no-pager -l silicium-experiment-api.service >&2 || true
    journalctl -u silicium-experiment-api.service --no-pager -n 100 >&2 || true
    exit 1
  fi
else
  echo "Skipping silicium-experiment-api.service check: unit file is not installed on this host."
fi

echo "Waiting for experiment API on 46110..."
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 "${healthz_headers[@]}" http://127.0.0.1:46110/healthz >/dev/null; then
    break
  fi
  sleep 2
done
if ! curl -fsS --max-time 8 "${healthz_headers[@]}" http://127.0.0.1:46110/healthz >/dev/null; then
  echo "Experiment API is not reachable on 127.0.0.1:46110 after waiting." >&2
  systemctl status --no-pager -l silicium-experiment-api.service >&2 || true
  journalctl -u silicium-experiment-api.service --no-pager -n 100 >&2 || true
  exit 1
fi
curl -fsS --max-time 8 http://127.0.0.1:9091/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1/downloads/update-manifest.json >/dev/null

downloads_dir="${SILICIUM_DOWNLOADS_DIR:-/var/lib/silicium/downloads}"
download_base_url="${SILICIUM_DOWNLOAD_BASE_URL:-https://vps-910c1dbc.vps.ovh.net/downloads}"
for artifact in \
  silicium-node-windows.exe \
  silicium-node-windows-dev.exe \
  silicium-node-linux-dev.deb \
  silicium-node-linux-dev.AppImage \
  silicium-node-linux-dev.rpm; do
  if [[ ! -s "$downloads_dir/$artifact" ]]; then
    echo "Missing published node artifact: $downloads_dir/$artifact" >&2
    exit 1
  fi
  curl -fsSIL --max-time 8 "$download_base_url/$artifact" >/dev/null
done

echo "Checking node service state..."
if systemctl list-unit-files --type service --all 2>/dev/null | awk '{print $1}' | grep -qx 'silicium-node.service'; then
  systemctl is-active --quiet silicium-node.service
else
  echo "Skipping silicium-node.service check: service is not installed on this host."
fi

public_orchestrator_url="${SILICIUM_NODE_ADVERTISE_URL:-https://vps-910c1dbc.vps.ovh.net/orchestrator}"
echo "Checking public orchestrator route: ${public_orchestrator_url%/}/healthz"
case "$public_orchestrator_url" in
  https://*) public_route_port=443 ;;
  http://*) public_route_port=80 ;;
  *)
    echo "Unsupported orchestrator URL scheme: $public_orchestrator_url" >&2
    exit 1
    ;;
esac
public_route_authority="${public_orchestrator_url#*://}"
public_route_authority="${public_route_authority%%/*}"
public_route_host="${public_route_authority%%:*}"
public_route_args=(--resolve "${public_route_host}:${public_route_port}:127.0.0.1")
public_health="$(curl -fsS --max-time 12 "${public_route_args[@]}" "${public_orchestrator_url%/}/healthz")"
if [[ "$public_health" != *'"service":"network_node"'* ]]; then
  echo "The public route does not reach the integrated network node: $public_health" >&2
  exit 1
fi

echo "Post-deploy checks passed."
