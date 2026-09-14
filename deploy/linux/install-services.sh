#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-prod}"
CHANNEL_TOOL="$ROOT/deploy/release/channel.py"
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
channel_config_dir="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field config_dir)"
channel_data_root="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field data_dir)"
service_suffix="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field service_suffix)"
orchestrator_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field orchestrator_port)"
experiment_api_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field experiment_api_port)"
experiment_rpc_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field experiment_rpc_port)"
experiment_events_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field experiment_events_port)"
public_base_url="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field public_base_url)"
orchestrator_node_id_default="orchestrator-1"
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  orchestrator_node_id_default="orchestrator-dev-1"
fi
CONFIG_DIR="${SILICIUM_CONFIG_DIR:-$channel_config_dir}"
DATA_ROOT="${SILICIUM_DATA_ROOT:-$channel_data_root}"

orchestrator_unit="silicium-orchestrator${service_suffix}.service"
update_manifest_unit="silicium-update-manifest${service_suffix}.service"
update_manifest_timer="silicium-update-manifest${service_suffix}.timer"
experiment_api_unit="silicium-experiment-api${service_suffix}.service"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/install-services.sh $ROOT" >&2
  exit 1
fi

[[ -d "$ROOT/deploy/systemd" ]] || { echo "Missing deployment files under: $ROOT" >&2; exit 1; }
cd "$ROOT"

if ! python3 - <<'PY'
import importlib.util
import sys

missing = [
    name for name in ("zmq", "google.protobuf")
    if importlib.util.find_spec(name) is None
]
sys.exit(0 if not missing else 1)
PY
then
  apt-get update
  apt-get install -y --no-install-recommends python3-cryptography python3-protobuf python3-zmq
fi

if ! python3 -c 'import cryptography' >/dev/null 2>&1; then
  apt-get update
  apt-get install -y --no-install-recommends python3-cryptography
fi

mkdir -p "$CONFIG_DIR" "$DATA_ROOT/site" "$DATA_ROOT/network" "$DATA_ROOT/solana" "$DATA_ROOT/downloads"

ORCHESTRATOR_ENV="$CONFIG_DIR/orchestrator.env"
if [[ ! -f "$ORCHESTRATOR_ENV" ]]; then
  echo "Missing $ORCHESTRATOR_ENV; copy deploy/env/orchestrator.example.env and configure it before installing services." >&2
  exit 1
fi

# A channel-specific config directory can start from the checked-in examples.
# Migrate only the legacy default roots so a dev install cannot accidentally
# write its scheduler state into the production data tree.
migrate_default_paths() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  sed -i \
    -e "s#/var/lib/silicium/#${DATA_ROOT}/#g" \
    -e "s#=/var/lib/silicium\$#=${DATA_ROOT}#g" \
    -e "s#/etc/silicium/#${CONFIG_DIR}/#g" \
    -e "s#=/etc/silicium\$#=${CONFIG_DIR}#g" \
    "$env_file"
}

migrate_default_paths "$ORCHESTRATOR_ENV"

ensure_env_default() {
  local key="$1"
  local value="$2"
  if ! grep -q -E "^${key}=" "$ORCHESTRATOR_ENV"; then
    printf '%s=%s\n' "$key" "$value" >> "$ORCHESTRATOR_ENV"
  fi
}

set_env_value_file() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  if [[ ! "$value" =~ ^[A-Za-z0-9._+:/@-]+$ ]]; then
    echo "Invalid value for $key: $value" >&2
    exit 1
  fi
  if grep -q -E "^${key}=" "$env_file"; then
    sed -i -E "s#^${key}=.*#${key}=${value}#" "$env_file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
  fi
}

# Development config files are commonly bootstrapped from the production
# examples. Replace only those known example defaults; preserve operator
# overrides on subsequent upgrades.
ensure_env_channel_default() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  shift 3
  local current
  current="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true)"
  if [[ -z "$current" ]]; then
    set_env_value_file "$env_file" "$key" "$value"
    return
  fi
  for legacy in "$@"; do
    if [[ "$current" == "$legacy" ]]; then
      set_env_value_file "$env_file" "$key" "$value"
      return
    fi
  done
}

ensure_env_text_channel_default() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  shift 3
  local current
  current="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true)"
  if [[ -z "$current" ]]; then
    if grep -q -E "^${key}=" "$env_file"; then
      sed -i -E "s#^${key}=.*#${key}=${value}#" "$env_file"
    else
      printf '%s=%s\n' "$key" "$value" >> "$env_file"
    fi
    return
  fi
  for legacy in "$@"; do
    if [[ "$current" == "$legacy" ]]; then
      sed -i -E "s#^${key}=.*#${key}=${value}#" "$env_file"
      return
    fi
  done
}

set_env_value() {
  local key="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[A-Za-z0-9._+-]+$ ]]; then
    echo "Invalid value for $key: $value" >&2
    exit 1
  fi
  if grep -q -E "^${key}=" "$ORCHESTRATOR_ENV"; then
    sed -i -E "s#^${key}=.*#${key}=${value}#" "$ORCHESTRATOR_ENV"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ORCHESTRATOR_ENV"
  fi
}

# The public URL is the stable HTTPS rendezvous used by desktop nodes.  Keep
# operator-provided values intact while making upgrades converge old env files
# that predate the integrated peer daemon.
ensure_env_default SILICIUM_NODE_ADVERTISE_URL "https://vps-910c1dbc.vps.ovh.net/orchestrator"
ensure_env_default SILICIUM_PEER_SYNC_INTERVAL_S "5"
ensure_env_default SILICIUM_PEER_SYNC_FANOUT "8"
ensure_env_default SILICIUM_PEER_HTTP_MAX_WORKERS "32"
ensure_env_default SILICIUM_PEER_STALE_AFTER_S "15"
# The VPS is the durable scheduler and storage rendezvous, not a workload
# worker. Older operator files may still advertise compute/verify, causing the
# scheduler to run verification with its Python fallback against tiles rendered
# by the desktop Rust runtime. Those implementations do not currently guarantee
# byte-identical pixels, so converge upgrades to the supported control-plane roles.
if grep -q -E '^SILICIUM_NODE_ROLES=' "$ORCHESTRATOR_ENV"; then
  sed -i -E 's/^SILICIUM_NODE_ROLES=.*/SILICIUM_NODE_ROLES=resource,storage/' "$ORCHESTRATOR_ENV"
else
  printf '%s\n' 'SILICIUM_NODE_ROLES=resource,storage' >> "$ORCHESTRATOR_ENV"
fi
# Migrate the value shipped by the previous integrated-node release. Keep any
# operator-selected value intact while preventing a stale 45-second default
# from surviving upgrades and masking worker disconnects.
if [[ "$(grep -E '^SILICIUM_PEER_STALE_AFTER_S=' "$ORCHESTRATOR_ENV" | tail -n 1 | cut -d= -f2-)" == "45" ]]; then
  sed -i -E 's/^SILICIUM_PEER_STALE_AFTER_S=45$/SILICIUM_PEER_STALE_AFTER_S=15/' "$ORCHESTRATOR_ENV"
fi
ensure_env_channel_default "$ORCHESTRATOR_ENV" SILICIUM_NODE_PORT "$orchestrator_port" 46100
ensure_env_channel_default "$ORCHESTRATOR_ENV" SILICIUM_NODE_ID "$orchestrator_node_id_default" orchestrator-1
ensure_env_text_channel_default "$ORCHESTRATOR_ENV" SILICIUM_NODE_ADVERTISE_URL "$public_base_url/orchestrator" "https://vps-910c1dbc.vps.ovh.net/orchestrator"

# Systemd does not inherit the release variables supplied to this installer.
# Persist them in the service environment so node heartbeats identify the
# exact deployed application version and source revision.
release_version="${SILICIUM_RELEASE_VERSION:-}"
if [[ -z "$release_version" ]]; then
  release_metadata="$ROOT/apps/silicium-node/package.json"
  if [[ "$RELEASE_CHANNEL" == "prod" && -f "$ROOT/apps/silicium-node/src-tauri/tauri.prod.conf.json" ]]; then
    release_metadata="$ROOT/apps/silicium-node/src-tauri/tauri.prod.conf.json"
  fi
  release_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$release_metadata")"
fi
release_channel="${SILICIUM_RELEASE_CHANNEL:-prod}"
release_build="${SILICIUM_RELEASE_BUILD:-}"
if [[ -z "$release_build" ]]; then
  release_build="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
fi
release_build="${release_build:-local}"
set_env_value SILICIUM_APP_VERSION "$release_version"
set_env_value SILICIUM_RELEASE_CHANNEL "$release_channel"
set_env_value SILICIUM_RELEASE_BUILD "$release_build"

sed \
  -e "s#__SILICIUM_ROOT__#$ROOT#g" \
  -e "s#__SILICIUM_CONFIG_DIR__#$CONFIG_DIR#g" \
  -e "s#__SILICIUM_DATA_ROOT__#$DATA_ROOT#g" \
  -e "s#__SILICIUM_RELEASE_CHANNEL__#$RELEASE_CHANNEL#g" \
  -e "s#__SILICIUM_UPDATE_MANIFEST_UNIT__#$update_manifest_unit#g" \
  deploy/systemd/silicium-update-manifest.service > /etc/systemd/system/"$update_manifest_unit"
sed \
  -e "s#__SILICIUM_ROOT__#$ROOT#g" \
  -e "s#__SILICIUM_CONFIG_DIR__#$CONFIG_DIR#g" \
  -e "s#__SILICIUM_DATA_ROOT__#$DATA_ROOT#g" \
  -e "s#__SILICIUM_RELEASE_CHANNEL__#$RELEASE_CHANNEL#g" \
  -e "s#__SILICIUM_ORCHESTRATOR_UNIT__#$orchestrator_unit#g" \
  -e "s#__SILICIUM_EXPERIMENT_RPC_PORT__#$experiment_rpc_port#g" \
  -e "s#__SILICIUM_EXPERIMENT_EVENTS_PORT__#$experiment_events_port#g" \
  deploy/systemd/silicium-experiment-api.service > /etc/systemd/system/"$experiment_api_unit"
sed -e "s#__SILICIUM_UPDATE_MANIFEST_UNIT__#$update_manifest_unit#g" \
  deploy/systemd/silicium-update-manifest.timer > /etc/systemd/system/"$update_manifest_timer"

# The orchestrator template has no channel-dependent unit references, but its
# output name must still be channel-specific so a dev install cannot restart
# the production scheduler.
sed -e "s#__SILICIUM_ROOT__#$ROOT#g" \
  -e "s#__SILICIUM_CONFIG_DIR__#$CONFIG_DIR#g" \
  -e "s#__SILICIUM_DATA_ROOT__#$DATA_ROOT#g" \
  -e "s#__SILICIUM_RELEASE_CHANNEL__#$RELEASE_CHANNEL#g" \
  deploy/systemd/silicium-orchestrator.service > /etc/systemd/system/"$orchestrator_unit"

if [[ ! -f "$CONFIG_DIR/update-channels.env" ]]; then
  cp deploy/env/update-channels.example.env "$CONFIG_DIR/update-channels.env"
fi
migrate_default_paths "$CONFIG_DIR/update-channels.env"
ensure_env_text_channel_default "$CONFIG_DIR/update-channels.env" SILICIUM_DOWNLOAD_BASE_URL "$public_base_url/downloads" "https://vps-910c1dbc.vps.ovh.net/downloads"
ensure_env_text_channel_default "$CONFIG_DIR/update-channels.env" SILICIUM_UPDATE_GOSSIP_URL "http://127.0.0.1:${orchestrator_port}/gossip/publish" "http://127.0.0.1:46100/gossip/publish"
# Release identifiers are source-controlled and must follow the artifacts built
# by CI. Preserve operator-specific URLs, keys and cache paths in the existing
# file while refreshing only the channel cadence/version fields.
dev_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$ROOT/apps/silicium-node/package.json")"
prod_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$ROOT/apps/silicium-node/src-tauri/tauri.prod.conf.json")"
for release_key in \
  SILICIUM_DEV_VERSION \
  SILICIUM_PROD_VERSION \
  SILICIUM_DEV_CHECK_INTERVAL_SECONDS \
  SILICIUM_PROD_CHECK_INTERVAL_SECONDS \
  SILICIUM_UPDATE_GOSSIP_REQUIRED; do
  case "$release_key" in
    SILICIUM_DEV_VERSION) release_line="SILICIUM_DEV_VERSION=${dev_version}" ;;
    SILICIUM_PROD_VERSION) release_line="SILICIUM_PROD_VERSION=${prod_version}" ;;
    *) release_line="$(grep -E "^${release_key}=" deploy/env/update-channels.example.env | tail -n 1)" ;;
  esac
  [[ -n "$release_line" ]] || continue
  if grep -q -E "^${release_key}=" "$CONFIG_DIR/update-channels.env"; then
    sed -i -E "s#^${release_key}=.*#${release_line}#" "$CONFIG_DIR/update-channels.env"
  else
    printf '%s\n' "$release_line" >> "$CONFIG_DIR/update-channels.env"
  fi
done
if [[ ! -f "$CONFIG_DIR/experiment-api.env" ]]; then
  cp deploy/env/experiment-api.example.env "$CONFIG_DIR/experiment-api.env"
fi
migrate_default_paths "$CONFIG_DIR/experiment-api.env"
ensure_env_channel_default "$CONFIG_DIR/experiment-api.env" SILICIUM_EXPERIMENT_API_PORT "$experiment_api_port" 46110
unset -f ensure_env_default set_env_value set_env_value_file ensure_env_channel_default ensure_env_text_channel_default
chmod 0755 "$ROOT/deploy/linux/publish-update-manifest.sh"
if [[ -f "$ROOT/deploy/linux/publish-package-repositories.sh" ]]; then
  chmod 0755 "$ROOT/deploy/linux/publish-package-repositories.sh"
fi
if [[ -f "$ROOT/deploy/linux/cleanup-vps.sh" ]]; then
  chmod 0755 "$ROOT/deploy/linux/cleanup-vps.sh"
fi
chmod 0755 "$ROOT/deploy/linux/start-orchestrator.sh"

systemctl daemon-reload
systemctl enable --now "$update_manifest_timer"
# The unit can already be active from a previous release. Enabling an active
# unit does not reload its changed ExecStart, so explicitly restart it to
# replace the legacy bootstrap server with the integrated node.
systemctl enable "$orchestrator_unit"
systemctl restart "$orchestrator_unit"
# The authenticated experiment/MCP API is a host-side control plane service.
# Keep it enabled so deploy-time health checks and e2e validation can hit the
# real HTTP and RPC endpoints on 46110/9770.
systemctl enable --now "$experiment_api_unit"

echo "Systemd services installed:"
echo "  $orchestrator_unit"
echo "  $update_manifest_timer"
echo "  $experiment_api_unit (installed, host-side systemd service)"
echo "Web/API/dashboard services are owned by deploy/compose/deploy.sh."
