#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-prod}"
CHANNEL_TOOL="$ROOT/infra/release/channel.py"
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
channel_config_dir="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field config_dir)"
channel_data_root="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field data_dir)"
CONFIG_DIR="${SILICIUM_CONFIG_DIR:-$channel_config_dir}"
ENV_FILE="${SILICIUM_ORCHESTRATOR_ENV:-$CONFIG_DIR/orchestrator.env}"

[[ -d "$ROOT/network" ]] || { echo "Missing Network runtime under: $ROOT" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing orchestrator environment: $ENV_FILE" >&2; exit 1; }

node_binary=""
for candidate in \
  "$ROOT/network/target/node-alpine/release/p2p_node" \
  "$ROOT/network/target/release/p2p_node" \
  "$ROOT/network/bin/p2p_node"; do
  if [[ -x "$candidate" ]]; then
    node_binary="$candidate"
    break
  fi
done
[[ -n "$node_binary" ]] || { echo "Missing Rust p2p_node binary under $ROOT/network" >&2; exit 1; }

set -a
# Configuration provisionnée sur le serveur, absente du dépôt.
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a

node_id="${SILICIUM_NODE_ID:-orchestrator-1}"
roles="${SILICIUM_NODE_ROLES:-resource,storage}"
port="${SILICIUM_NODE_PORT:-46100}"
data_root="${SILICIUM_DATA_ROOT:-$channel_data_root}"
export_dir="${SILICIUM_EXPORT_DIR:-$data_root/network/orchestrator/export}"
state_dir="${SILICIUM_STATE_DIR:-$data_root/network/orchestrator/state}"
mkdir -p "$export_dir" "$state_dir"
cd "$ROOT/network"

control_token="${SILICIUM_NODE_CONTROL_TOKEN:-}"
[[ -n "$control_token" ]] || { echo "SILICIUM_NODE_CONTROL_TOKEN is required for the Rust API" >&2; exit 1; }

# The Rust node exposes the BackEnd control API on NODE_PORT and keeps the
# libp2p transport on the adjacent fixed port. The latter is the dev-channel
# bootstrap address used by desktop nodes.
export SILICIUM_NODE_ID="$node_id"
export SILICIUM_NODE_ROLES="$roles"
export SILICIUM_APP_VERSION="${SILICIUM_APP_VERSION:-unknown}"
export SILICIUM_RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-prod}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-local}"
export SILICIUM_DATA_DIR="${SILICIUM_DATA_DIR:-$state_dir}"
export SILICIUM_COMPUTE_ROOT="${SILICIUM_COMPUTE_ROOT:-$data_root/network/orchestrator/work}"
export SILICIUM_WORKLOAD_STORAGE_DIR="${SILICIUM_WORKLOAD_STORAGE_DIR:-$data_root/site/runtime}"
export SILICIUM_EXPORT_DIR="$export_dir"
export SILICIUM_API_BIND="${SILICIUM_API_BIND:-0.0.0.0}"
export API_PORT="$port"
export SILICIUM_P2P_BIND="${SILICIUM_P2P_BIND:-0.0.0.0}"
export SILICIUM_P2P_PORT="${SILICIUM_P2P_PORT:-$((port + 1))}"
export SILICIUM_NODE_CONTROL_TOKEN="$control_token"
export SILICIUM_WORK_OWN_TASKS="${SILICIUM_WORK_OWN_TASKS:-0}"

exec "$node_binary"
