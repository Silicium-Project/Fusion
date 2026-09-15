#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-prod}"
CHANNEL_TOOL="$ROOT/deploy/release/channel.py"
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
channel_field() { python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field "$1"; }
channel_config_dir="$(channel_field config_dir)"
channel_data_root="$(channel_field data_dir)"
channel_service_suffix="$(channel_field service_suffix)"
channel_orchestrator_port="$(channel_field orchestrator_port)"
channel_experiment_api_port="$(channel_field experiment_api_port)"
channel_backend_http_port="$(channel_field backend_http_port)"
channel_frontend_http_port="$(channel_field frontend_http_port)"
channel_reputation_http_port="$(channel_field reputation_http_port)"
channel_proxy_http_port="$(channel_field proxy_http_port)"
channel_public_base_url="$(channel_field public_base_url)"
channel_vpn_interface=""
channel_vpn_network=""
channel_vpn_server_address=""
channel_vpn_listen_port=""
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  channel_vpn_interface="$(channel_field vpn_interface)"
  channel_vpn_network="$(channel_field vpn_network)"
  channel_vpn_server_address="$(channel_field vpn_server_address)"
  channel_vpn_listen_port="$(channel_field vpn_listen_port)"
fi
CONFIG_DIR="${SILICIUM_CONFIG_DIR:-$channel_config_dir}"
DATA_ROOT="${SILICIUM_DATA_ROOT:-$channel_data_root}"
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.yml"
COMPOSE_ENV="${SILICIUM_COMPOSE_ENV:-$CONFIG_DIR/compose.env}"
EXPERIMENT_API_ENV="$CONFIG_DIR/experiment-api.env"
UPDATE_CHANNELS_ENV="$CONFIG_DIR/update-channels.env"
ORCHESTRATOR_ENV="$CONFIG_DIR/orchestrator.env"
RELEASE_MARKER="${SILICIUM_RELEASE_MARKER:-$DATA_ROOT/releases/current.env}"
ORCHESTRATOR_UNIT="silicium-orchestrator${channel_service_suffix}.service"
EXPERIMENT_API_UNIT="silicium-experiment-api${channel_service_suffix}.service"

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
if [[ "${SILICIUM_RELEASE_CHANNEL:-}" != "$RELEASE_CHANNEL" ]]; then
  echo "Release marker channel mismatch: expected $RELEASE_CHANNEL, got ${SILICIUM_RELEASE_CHANNEL:-<empty>}" >&2
  exit 1
fi
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
. "$COMPOSE_ENV"
# The checked-in compose example contains production defaults. The deployment
# scripts export the channel-specific values before invoking this check.
. "$RELEASE_MARKER"
set +a
if [[ -z "${SILICIUM_MCP_TOKEN:-}" ]]; then
  echo "Missing SILICIUM_MCP_TOKEN in $EXPERIMENT_API_ENV" >&2
  exit 1
fi

healthz_headers=(-H "Authorization: Bearer ${SILICIUM_MCP_TOKEN}")

channel_or_legacy_default() {
  local current="$1"
  local value="$2"
  local legacy="$3"
  if [[ -z "$current" || "$current" == "$legacy" ]]; then
    printf '%s' "$value"
  else
    printf '%s' "$current"
  fi
}
backend_port="$(channel_or_legacy_default "${SILICIUM_BACKEND_HTTP_PORT:-}" "$channel_backend_http_port" 8080)"
frontend_port="$(channel_or_legacy_default "${SILICIUM_FRONTEND_HTTP_PORT:-}" "$channel_frontend_http_port" 3000)"
reputation_port="$(channel_or_legacy_default "${SILICIUM_REPUTATION_HTTP_PORT:-}" "$channel_reputation_http_port" 9091)"
orchestrator_port="${SILICIUM_NODE_PORT:-$channel_orchestrator_port}"
experiment_api_port="${SILICIUM_EXPERIMENT_API_PORT:-$channel_experiment_api_port}"
export SILICIUM_RELEASE_CHANNEL="$RELEASE_CHANNEL"
export SILICIUM_CONFIG_DIR="$CONFIG_DIR"
export SILICIUM_DATA_ROOT="$DATA_ROOT"
export SILICIUM_BACKEND_HTTP_PORT="$backend_port"
export SILICIUM_FRONTEND_HTTP_PORT="$frontend_port"
export SILICIUM_REPUTATION_HTTP_PORT="$reputation_port"
export SILICIUM_ORCHESTRATOR_PORT="$orchestrator_port"

public_route_target=127.0.0.1
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  command -v wg >/dev/null || { echo "WireGuard is missing on the dev VPS." >&2; exit 1; }
  command -v ip >/dev/null || { echo "iproute2 is missing on the dev VPS." >&2; exit 1; }
  systemctl is-active --quiet "wg-quick@${channel_vpn_interface}.service" || {
    echo "The dev WireGuard service is not active." >&2
    systemctl status --no-pager -l "wg-quick@${channel_vpn_interface}.service" >&2 || true
    exit 1
  }
  ip -4 addr show dev "$channel_vpn_interface" | grep -Eq "inet[[:space:]]+${channel_vpn_server_address}/" || {
    echo "The dev VPN address ${channel_vpn_server_address} is not active on ${channel_vpn_interface}." >&2
    exit 1
  }
  [[ "$(wg show "$channel_vpn_interface" listen-port)" == "$channel_vpn_listen_port" ]] || {
    echo "The dev WireGuard listen port is not ${channel_vpn_listen_port}." >&2
    exit 1
  }
  public_route_target="$channel_vpn_server_address"
fi

echo "Checking Docker Compose services for channel $RELEASE_CHANNEL..."
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
curl -fsS --max-time 8 "http://127.0.0.1:${backend_port}/health" >/dev/null
curl -fsS --max-time 8 "http://127.0.0.1:${frontend_port}" >/dev/null
orchestrator_health=""
for _ in $(seq 1 30); do
  if orchestrator_health="$(curl -fsS --max-time 3 "http://127.0.0.1:${orchestrator_port}/healthz" 2>/dev/null)"; then
    break
  fi
  sleep 2
done
if [[ -z "$orchestrator_health" ]]; then
  echo "The integrated network node did not become reachable on 127.0.0.1:${orchestrator_port}." >&2
  systemctl status --no-pager -l "$ORCHESTRATOR_UNIT" >&2 || true
  journalctl -u "$ORCHESTRATOR_UNIT" --no-pager -n 100 >&2 || true
  exit 1
fi
if [[ "$orchestrator_health" != *'"service":"network_node"'* ]]; then
  echo "The integrated network node is not serving the orchestrator port: $orchestrator_health" >&2
  exit 1
fi
export_dir="${SILICIUM_EXPORT_DIR:-$DATA_ROOT/network/orchestrator/export}"
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
if systemctl cat "$EXPERIMENT_API_UNIT" >/dev/null 2>&1; then
  if ! systemctl is-active --quiet "$EXPERIMENT_API_UNIT"; then
    echo "$EXPERIMENT_API_UNIT is installed but not active." >&2
    systemctl status --no-pager -l "$EXPERIMENT_API_UNIT" >&2 || true
    journalctl -u "$EXPERIMENT_API_UNIT" --no-pager -n 100 >&2 || true
    exit 1
  fi
else
  echo "Skipping $EXPERIMENT_API_UNIT check: unit file is not installed on this host."
fi

echo "Waiting for experiment API on ${experiment_api_port}..."
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 "${healthz_headers[@]}" "http://127.0.0.1:${experiment_api_port}/healthz" >/dev/null; then
    break
  fi
  sleep 2
done
if ! curl -fsS --max-time 8 "${healthz_headers[@]}" "http://127.0.0.1:${experiment_api_port}/healthz" >/dev/null; then
  echo "Experiment API is not reachable on 127.0.0.1:${experiment_api_port} after waiting." >&2
  systemctl status --no-pager -l "$EXPERIMENT_API_UNIT" >&2 || true
  journalctl -u "$EXPERIMENT_API_UNIT" --no-pager -n 100 >&2 || true
  exit 1
fi
curl -fsS --max-time 8 "http://127.0.0.1:${reputation_port}/health" >/dev/null

downloads_dir="${SILICIUM_DOWNLOADS_DIR:-$DATA_ROOT/downloads}"
download_base_url="${SILICIUM_DOWNLOAD_BASE_URL:-$channel_public_base_url/downloads}"
download_tls_args=()
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  # The dev channel is exposed through the private WireGuard endpoint and its
  # local CA is intentionally not installed in every caller's trust store.
  # The route is still authenticated by the private network; do not let a
  # CA trust-store difference make a healthy deployment fail its postcheck.
  download_tls_args=(-k)
fi
[[ -s "$downloads_dir/update-manifest.json" ]] || {
  echo "Missing update manifest: $downloads_dir/update-manifest.json" >&2
  exit 1
}
if [[ "$RELEASE_CHANNEL" == "prod" ]]; then
  required_artifacts=(
    silicium-node-windows.exe
    silicium-node-linux.AppImage
    silicium-node-linux.deb
    silicium-node-linux.rpm
  )
else
  required_artifacts=(
    silicium-node-linux-dev.AppImage
    silicium-node-linux-dev.deb
    silicium-node-linux-dev.rpm
  )
fi
for artifact in "${required_artifacts[@]}"; do
    if [[ ! -s "$downloads_dir/$artifact" ]]; then
      echo "Missing published node artifact: $downloads_dir/$artifact" >&2
      exit 1
    fi
    curl -fsSIL --max-time 8 "${download_tls_args[@]}" "$download_base_url/$artifact" >/dev/null
done
package_suite=stable
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  package_suite=dev
fi
for repository_metadata in \
  "apt/dists/${package_suite}/InRelease" \
  "rpm/repodata/repomd.xml"; do
  curl -fsSIL --max-time 8 "${download_tls_args[@]}" "$download_base_url/$repository_metadata" >/dev/null || {
    echo "Missing published package repository metadata: $download_base_url/$repository_metadata" >&2
    exit 1
  }
done

if [[ "$RELEASE_CHANNEL" == "prod" ]]; then
  echo "Checking node service state..."
  if systemctl list-unit-files --type service --all 2>/dev/null | awk '{print $1}' | grep -qx 'silicium-node.service'; then
    systemctl is-active --quiet silicium-node.service
  else
    echo "Skipping silicium-node.service check: service is not installed on this host."
  fi
fi

public_orchestrator_url="${SILICIUM_NODE_ADVERTISE_URL:-https://vps-910c1dbc.vps.ovh.net/orchestrator}"
echo "Checking public orchestrator route: ${public_orchestrator_url%/}/healthz"
read -r public_route_host public_route_port <<EOF
$(python3 - "$public_orchestrator_url" <<'PY'
import sys
from urllib.parse import urlsplit

parsed = urlsplit(sys.argv[1])
if parsed.scheme not in {"http", "https"} or not parsed.hostname:
    raise SystemExit("unsupported public orchestrator URL")
print(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
PY
)
EOF
public_route_args=(--resolve "${public_route_host}:${public_route_port}:${public_route_target}")
public_tls_args=()
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  public_tls_args=(-k)
fi
if ! public_health="$(curl -fsS --max-time 12 "${public_tls_args[@]}" "${public_route_args[@]}" "${public_orchestrator_url%/}/healthz" 2>&1)"; then
  echo "Public orchestrator route probe failed: $public_health" >&2
  echo "Docker backend network gateway:" >&2
  backend_network_gateway="$(docker network inspect --format '{{(index .IPAM.Config 0).Gateway}}' \
    "${SILICIUM_BACKEND_NETWORK_NAME:-silicium-backend}" 2>/dev/null || true)"
  printf '%s\n' "${backend_network_gateway:-<unavailable>}" >&2
  echo "Host listener and gateway probe:" >&2
  ss -ltnp 2>/dev/null | grep -E ":(${orchestrator_port}|${public_route_port})[[:space:]]" >&2 || true
  if [[ -n "$backend_network_gateway" ]]; then
    curl -v --max-time 5 "http://${backend_network_gateway}:${orchestrator_port}/healthz" >&2 || true
  fi
  echo "Firewall summary:" >&2
  if command -v ufw >/dev/null 2>&1; then
    ufw status verbose >&2 || true
  fi
  if command -v nft >/dev/null 2>&1; then
    nft list ruleset 2>/dev/null | grep -E "docker|${orchestrator_port}|drop|reject|policy" >&2 || true
  fi
  proxy_container="$(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" ps -q proxy 2>/dev/null || true)"
  if [[ -n "$proxy_container" ]]; then
    echo "Proxy host mapping and direct orchestrator probe:" >&2
    docker exec "$proxy_container" getent hosts host.docker.internal >&2 || true
    docker exec "$proxy_container" busybox wget -S -O - -T 5 \
      "http://host.docker.internal:${orchestrator_port}/healthz" >&2 || true
    echo "Proxy error log:" >&2
    docker logs --tail 100 "$proxy_container" >&2 || true
  fi
  exit 28
fi
if [[ "$public_health" != *'"service":"network_node"'* ]]; then
  echo "The public route does not reach the integrated network node: $public_health" >&2
  exit 1
fi

echo "Post-deploy checks passed."
