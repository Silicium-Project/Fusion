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

# Keep direct Linux launches aligned with the desktop supervisor. The runtime
# manifest stores paths relative to the runtime root because the AppImage and
# the per-user managed copy live in different locations.
RAYTRACER_ENV_FILE="$ROOT/.silicium/env/raytracer.env"
if [[ -f "$RAYTRACER_ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    case "$key" in
      SILICIUM_RAYTRACER_BIN|SILICIUM_RAYTRACER_ASSETS_DIR)
        if [[ "$value" != /* ]]; then
          value="$ROOT/$value"
        fi
        export "$key=$value"
        ;;
    esac
  done < "$RAYTRACER_ENV_FILE"
fi

# AppImage's linuxdeploy environment can put an incomplete bundled Python
# ahead of the host interpreter and export PYTHONHOME/PYTHONPATH for it. The
# Network runtime is shipped as Python sources plus site-packages, so launch it
# with the host Python and a clean interpreter environment. Debian/RPM already
# declare python3 as a dependency; AppImage follows the same host requirement.
PYTHON_BIN="${SILICIUM_PYTHON3:-}"
if [[ -z "$PYTHON_BIN" && -x /usr/bin/python3 ]]; then
  PYTHON_BIN="/usr/bin/python3"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "Python 3 is required to run the Silicium Network runtime." >&2
  exit 127
fi

unset PYTHONHOME PYTHONPATH
RUNTIME_SITE_PACKAGES="$ROOT/tools/python/site-packages"
if [[ -d "$RUNTIME_SITE_PACKAGES" ]]; then
  export PYTHONPATH="$RUNTIME_SITE_PACKAGES"
fi

cd "$ROOT/Network"

exec "$PYTHON_BIN" silicium node start \
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
  --peer-sync-fanout "${SILICIUM_PEER_SYNC_FANOUT:-8}" \
  --peer-stale-after-s "${SILICIUM_PEER_STALE_AFTER_S:-15}" \
  --peer-http-max-workers "${SILICIUM_PEER_HTTP_MAX_WORKERS:-16}" \
  --pull-tasks-enable \
  --pull-tasks-interval-s "${SILICIUM_PULL_TASKS_INTERVAL_S:-0.25}" \
  --pull-tasks-batch-size "${SILICIUM_PULL_TASKS_BATCH_SIZE:-4}" \
  --nat-punch-enable \
  --p2p-direct-transport-backend auto \
  "${EXTRA_ARGS[@]}"
