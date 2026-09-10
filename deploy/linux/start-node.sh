#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: deploy/linux/start-node.sh <node-id> <roles> <port> <seed-url> [advertise-host] [mesh-key] [reputation-score] [extra node args...]" >&2
  exit 2
fi

NODE_ID="$1"
ROLES="$2"
PORT="$3"
SEED_URL="$4"
ADVERTISE_HOST="${5:-127.0.0.1}"
MESH_KEY="${6:-demo-mesh}"
REPUTATION="${7:-50}"
EXTRA_ARGS=("${@:8}")
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/Network"

python3 silicium node start \
  --node-id "$NODE_ID" \
  --roles "$ROLES" \
  --export-dir ".silicium/networked/$NODE_ID/export" \
  --state-dir ".silicium/networked/$NODE_ID/state" \
  --peer-http-bind 0.0.0.0 \
  --peer-http-port "$PORT" \
  --gossip-enable \
  --gossip-bind 0.0.0.0 \
  --gossip-port "$PORT" \
  --peer-advertise-host "$ADVERTISE_HOST" \
  --peer-advertise-port "$PORT" \
  --gossip-advertise-host "$ADVERTISE_HOST" \
  --gossip-advertise-port "$PORT" \
  --seed-peers "$SEED_URL" \
  --mesh-key "$MESH_KEY" \
  --reputation-score "$REPUTATION" \
  --peer-sync-interval-s "${SILICIUM_PEER_SYNC_INTERVAL_S:-5}" \
  --peer-stale-after-s "${SILICIUM_PEER_STALE_AFTER_S:-15}" \
  --pull-tasks-enable \
  --nat-punch-enable \
  --p2p-direct-transport-backend auto \
  "${EXTRA_ARGS[@]}"
