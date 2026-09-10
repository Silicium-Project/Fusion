#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
ENV_FILE="/etc/silicium/orchestrator.env"

[[ -d "$ROOT/Network" ]] || { echo "Missing Network runtime under: $ROOT" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing orchestrator environment: $ENV_FILE" >&2; exit 1; }

set -a
. "$ENV_FILE"
set +a

node_id="${SILICIUM_NODE_ID:-orchestrator-1}"
roles="${SILICIUM_NODE_ROLES:-resource,storage}"
port="${SILICIUM_NODE_PORT:-46100}"
export_dir="${SILICIUM_EXPORT_DIR:-/var/lib/silicium/network/orchestrator/export}"
state_dir="${SILICIUM_STATE_DIR:-/var/lib/silicium/network/orchestrator/state}"
mesh_key="${SILICIUM_MESH_KEY:-}"
advertise_host="${SILICIUM_NODE_ADVERTISE_HOST:-}"

# ORCHESTRATOR_PUBLIC_IP is intentionally a placeholder in the checked-in
# example. Resolve it at runtime when an operator has not supplied a public
# address, so the peer book never advertises the placeholder literally.
if [[ -z "$advertise_host" || "$advertise_host" == "ORCHESTRATOR_PUBLIC_IP" ]]; then
  advertise_host="$(curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
fi
if [[ -z "$advertise_host" ]]; then
  advertise_host="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [[ -z "$advertise_host" ]]; then
  echo "Could not determine the orchestrator advertised host; set SILICIUM_NODE_ADVERTISE_HOST in $ENV_FILE." >&2
  exit 1
fi

advertise_url="${SILICIUM_NODE_ADVERTISE_URL:-}"
if [[ -z "$advertise_url" ]]; then
  advertise_url="http://${advertise_host}:${port}"
fi

mkdir -p "$export_dir" "$state_dir"
cd "$ROOT/Network"

node_args=(
  --export-dir "$export_dir"
  --state-dir "$state_dir"
  --node-id "$node_id"
  --roles "$roles"
  --app-version "${SILICIUM_APP_VERSION:-unknown}"
  --release-channel "${SILICIUM_RELEASE_CHANNEL:-dev}"
  --release-build "${SILICIUM_RELEASE_BUILD:-}"
  --gossip-enable
  --gossip-bind 0.0.0.0
  --gossip-port "$port"
  --peer-http-bind 0.0.0.0
  --peer-http-port "$port"
  --peer-advertise-url "$advertise_url"
  --peer-advertise-host "$advertise_host"
  --peer-advertise-port "$port"
  --gossip-advertise-host "$advertise_host"
  --gossip-advertise-port "$port"
  --mesh-key "$mesh_key"
  --peer-sync-interval-s "${SILICIUM_PEER_SYNC_INTERVAL_S:-15}"
  --peer-stale-after-s "${SILICIUM_PEER_STALE_AFTER_S:-45}"
  --relay-enable
  --remote-dispatch-enable
  --remote-dispatch-limit "${SILICIUM_REMOTE_DISPATCH_LIMIT:-3}"
  --nat-punch-enable
  --p2p-direct-transport-backend "${SILICIUM_P2P_DIRECT_TRANSPORT_BACKEND:-auto}"
  --reputation-score "${SILICIUM_REPUTATION_SCORE:-100}"
)

if [[ -n "${SILICIUM_P2P_STUN_SERVER:-}" ]]; then
  node_args+=(--p2p-stun-server "$SILICIUM_P2P_STUN_SERVER")
fi
if [[ -n "${SILICIUM_P2P_TURN_SERVER:-}" ]]; then
  node_args+=(--p2p-turn-server "$SILICIUM_P2P_TURN_SERVER")
fi
if [[ -n "${SILICIUM_P2P_TURN_USERNAME:-}" ]]; then
  node_args+=(--p2p-turn-username "$SILICIUM_P2P_TURN_USERNAME")
fi
if [[ -n "${SILICIUM_P2P_TURN_PASSWORD:-}" ]]; then
  node_args+=(--p2p-turn-password "$SILICIUM_P2P_TURN_PASSWORD")
fi
if [[ -n "${SILICIUM_DISCOVERY_SEEDS:-}" ]]; then
  node_args+=(--discovery-seeds "$SILICIUM_DISCOVERY_SEEDS")
fi

exec /usr/bin/python3 -m tools.network_node "${node_args[@]}"
