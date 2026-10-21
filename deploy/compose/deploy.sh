#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-prod}"
CHANNEL_TOOL="$ROOT/deploy/release/channel.py"
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
export SILICIUM_RELEASE_CHANNEL="$RELEASE_CHANNEL"
channel_config_dir="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field config_dir)"
channel_data_root="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field data_dir)"
channel_compose_project="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field compose_project)"
channel_service_suffix="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field service_suffix)"
channel_runtime_root="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field deployment_root)"
backend_http_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field backend_http_port)"
backend_p2p_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field backend_p2p_port)"
frontend_http_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field frontend_http_port)"
reputation_http_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field reputation_http_port)"
orchestrator_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field orchestrator_port)"
turn_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field turn_port)"
turn_tls_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field turn_tls_port)"
turn_relay_min_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field turn_relay_min_port)"
turn_relay_max_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field turn_relay_max_port)"
proxy_bind_address="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field proxy_bind_address)"
proxy_http_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field proxy_http_port)"
proxy_https_port="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field proxy_https_port)"
backend_network_name="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field backend_network_name)"
frontend_network_name="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field frontend_network_name)"
channel_tls_root="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field tls_root)"
public_base_url="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field public_base_url)"
vpn_interface=""
vpn_server_address=""
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  vpn_interface="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field vpn_interface)"
  vpn_server_address="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field vpn_server_address)"
fi
COMPOSE_FILE="$ROOT/deploy/compose/docker-compose.yml"
APP_PACKAGE_JSON="$ROOT/apps/silicium-node/package.json"
initial_config_dir="${SILICIUM_CONFIG_DIR:-$channel_config_dir}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/compose/deploy.sh $ROOT" >&2
  exit 1
fi

[[ -f "$COMPOSE_FILE" ]] || { echo "Missing compose file: $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$APP_PACKAGE_JSON" ]] || { echo "Missing app package: $APP_PACKAGE_JSON" >&2; exit 1; }

COMPOSE_ENV="${SILICIUM_COMPOSE_ENV:-$initial_config_dir/compose.env}"
[[ -f "$COMPOSE_ENV" ]] || { echo "Missing compose env: $COMPOSE_ENV" >&2; exit 1; }

# Read operator settings first, then replace only the production example
# defaults when this is the dev channel. This lets dev and prod share one VPS
# without sharing ports, Docker networks, TLS roots or persistent data.
set -a
# shellcheck disable=SC1090
. "$COMPOSE_ENV"
orchestrator_env_dir="${SILICIUM_CONFIG_DIR:-$initial_config_dir}"
if [[ -f "$orchestrator_env_dir/orchestrator.env" ]]; then
  # Keep the BackEnd's Rust control client on the same bearer token as the
  # host-side p2p_node service.
  # shellcheck disable=SC1090
  . "$orchestrator_env_dir/orchestrator.env"
fi
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  SILICIUM_DEV_MINIWORKERS_ENV="${SILICIUM_DEV_MINIWORKERS_ENV:-$orchestrator_env_dir/miniworkers.env}"
  if [[ -f "$SILICIUM_DEV_MINIWORKERS_ENV" ]]; then
    # shellcheck disable=SC1090
    . "$SILICIUM_DEV_MINIWORKERS_ENV"
  fi
  export SILICIUM_DEV_MINIWORKERS_ENV
fi
set +a

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

export SILICIUM_RUNTIME_ROOT="$(channel_or_legacy_default "${SILICIUM_RUNTIME_ROOT:-}" "$channel_runtime_root" /opt/silicium)"
export SILICIUM_DATA_ROOT="$(channel_or_legacy_default "${SILICIUM_DATA_ROOT:-}" "$channel_data_root" /var/lib/silicium)"
export SILICIUM_CONFIG_DIR="$(channel_or_legacy_default "${SILICIUM_CONFIG_DIR:-}" "$channel_config_dir" /etc/silicium)"
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  export SILICIUM_DEV_MINIWORKERS_PAIRING_DIR="$SILICIUM_DATA_ROOT/miniworker-pairing"
  if [[ -f "$SILICIUM_DEV_MINIWORKERS_ENV" ]]; then
    if grep -q '^SILICIUM_DEV_MINIWORKERS_PAIRING_DIR=' "$SILICIUM_DEV_MINIWORKERS_ENV"; then
      sed -i "s#^SILICIUM_DEV_MINIWORKERS_PAIRING_DIR=.*#SILICIUM_DEV_MINIWORKERS_PAIRING_DIR=$SILICIUM_DEV_MINIWORKERS_PAIRING_DIR#" "$SILICIUM_DEV_MINIWORKERS_ENV"
    else
      printf 'SILICIUM_DEV_MINIWORKERS_PAIRING_DIR=%s\n' "$SILICIUM_DEV_MINIWORKERS_PAIRING_DIR" >> "$SILICIUM_DEV_MINIWORKERS_ENV"
    fi
  fi
fi
export SILICIUM_RELEASE_CHANNEL="$RELEASE_CHANNEL"
export SILICIUM_COMPOSE_PROJECT_NAME="$(channel_or_legacy_default "${SILICIUM_COMPOSE_PROJECT_NAME:-}" "$channel_compose_project" silicium)"
export SILICIUM_BACKEND_HTTP_PORT="$(channel_or_legacy_default "${SILICIUM_BACKEND_HTTP_PORT:-}" "$backend_http_port" 8080)"
export SILICIUM_BACKEND_P2P_PORT="$(channel_or_legacy_default "${SILICIUM_BACKEND_P2P_PORT:-}" "$backend_p2p_port" 46102)"
export SILICIUM_FRONTEND_HTTP_PORT="$(channel_or_legacy_default "${SILICIUM_FRONTEND_HTTP_PORT:-}" "$frontend_http_port" 3000)"
export SILICIUM_REPUTATION_HTTP_PORT="$(channel_or_legacy_default "${SILICIUM_REPUTATION_HTTP_PORT:-}" "$reputation_http_port" 9091)"
export SILICIUM_ORCHESTRATOR_PORT="$(channel_or_legacy_default "${SILICIUM_ORCHESTRATOR_PORT:-}" "$orchestrator_port" 46100)"
export SILICIUM_TURN_PORT="$(channel_or_legacy_default "${SILICIUM_TURN_PORT:-}" "$turn_port" 3478)"
export SILICIUM_TURN_TLS_PORT="$(channel_or_legacy_default "${SILICIUM_TURN_TLS_PORT:-}" "$turn_tls_port" 5349)"
export SILICIUM_TURN_RELAY_MIN_PORT="$(channel_or_legacy_default "${SILICIUM_TURN_RELAY_MIN_PORT:-}" "$turn_relay_min_port" 49160)"
export SILICIUM_TURN_RELAY_MAX_PORT="$(channel_or_legacy_default "${SILICIUM_TURN_RELAY_MAX_PORT:-}" "$turn_relay_max_port" 49200)"
export SILICIUM_PROXY_BIND_ADDRESS="$(channel_or_legacy_default "${SILICIUM_PROXY_BIND_ADDRESS:-}" "$proxy_bind_address" 0.0.0.0)"
export SILICIUM_PROXY_HTTP_PORT="$(channel_or_legacy_default "${SILICIUM_PROXY_HTTP_PORT:-}" "$proxy_http_port" 80)"
export SILICIUM_PROXY_HTTPS_PORT="$(channel_or_legacy_default "${SILICIUM_PROXY_HTTPS_PORT:-}" "$proxy_https_port" 443)"
export SILICIUM_BACKEND_NETWORK_NAME="$(channel_or_legacy_default "${SILICIUM_BACKEND_NETWORK_NAME:-}" "$backend_network_name" silicium-backend)"
export SILICIUM_FRONTEND_NETWORK_NAME="$(channel_or_legacy_default "${SILICIUM_FRONTEND_NETWORK_NAME:-}" "$frontend_network_name" silicium-frontend)"
export SILICIUM_TLS_ROOT="$(channel_or_legacy_default "${SILICIUM_TLS_ROOT:-}" "$channel_tls_root" /etc/letsencrypt)"
export SILICIUM_PUBLIC_ORCHESTRATOR_URL="${SILICIUM_PUBLIC_ORCHESTRATOR_URL:-$public_base_url/orchestrator}"
export SILICIUM_PUBLIC_API_BASE="${SILICIUM_PUBLIC_API_BASE:-/api}"
export SILICIUM_CORS_ALLOWED_ORIGINS="${SILICIUM_CORS_ALLOWED_ORIGINS:-$public_base_url}"
export SILICIUM_NGINX_CONFIG="$SILICIUM_CONFIG_DIR/nginx.conf"
unset -f channel_or_legacy_default

if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  command -v wg >/dev/null || { echo "WireGuard is not installed; run prepare-dev-config.sh first." >&2; exit 1; }
  command -v ip >/dev/null || { echo "iproute2 is required for the dev VPN ingress." >&2; exit 1; }
  if ! ip -4 addr show dev "$vpn_interface" | grep -Eq "inet[[:space:]]+${vpn_server_address}/"; then
    echo "The dev VPN address ${vpn_server_address} is not active on ${vpn_interface}." >&2
    exit 1
  fi
  # A dev deployment must never silently fall back to a loopback or public
  # bind. The WireGuard bootstrap creates the address before Compose starts.
  export SILICIUM_VPN_INTERFACE="$vpn_interface"
  export SILICIUM_VPN_SERVER_ADDRESS="$vpn_server_address"
  export SILICIUM_PROXY_BIND_ADDRESS="$vpn_server_address"
  export SILICIUM_TURN_EXTERNAL_IP="${SILICIUM_TURN_EXTERNAL_IP:-$vpn_server_address}"
fi

install -d -m 0750 "$SILICIUM_CONFIG_DIR"
sed \
  -e "s#__SILICIUM_ORCHESTRATOR_PORT__#$SILICIUM_ORCHESTRATOR_PORT#g" \
  "$ROOT/deploy/compose/nginx.conf" > "$SILICIUM_NGINX_CONFIG"

# The orchestrator participates in peer telemetry even though it is not a
# desktop binary. Prefer the CI/CD release version when provided, otherwise
# derive from the canonical desktop package.
if [[ -z "${SILICIUM_APP_VERSION:-}" ]] && [[ -n "${SILICIUM_RELEASE_VERSION:-}" ]]; then
  SILICIUM_APP_VERSION="$SILICIUM_RELEASE_VERSION"
fi
if [[ -z "${SILICIUM_APP_VERSION:-}" ]]; then
  SILICIUM_APP_VERSION="$(sed -nE 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$APP_PACKAGE_JSON" | head -n 1)"
fi
[[ -n "$SILICIUM_APP_VERSION" ]] || { echo "Could not derive SILICIUM_APP_VERSION" >&2; exit 1; }
export SILICIUM_APP_VERSION
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-$(git -C "$ROOT" rev-parse --short=12 HEAD)}"

compose=(docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE")

# Create the channel's backend bridge before starting containers so the host
# gateway can be resolved from its actual user-defined subnet. Docker's
# `host-gateway` placeholder otherwise points at the default bridge on some
# VPS installations, where the host-side orchestrator is not reachable from
# the dev proxy/backend containers.
"${compose[@]}" up -d postgres
host_gateway="$(docker network inspect --format '{{(index .IPAM.Config 0).Gateway}}' "$SILICIUM_BACKEND_NETWORK_NAME" 2>/dev/null || true)"
if [[ -z "$host_gateway" || "$host_gateway" == "<no value>" ]]; then
  echo "Could not resolve the gateway for Docker network $SILICIUM_BACKEND_NETWORK_NAME" >&2
  exit 1
fi
backend_network_subnet="$(docker network inspect --format '{{(index .IPAM.Config 0).Subnet}}' "$SILICIUM_BACKEND_NETWORK_NAME" 2>/dev/null || true)"
if [[ -z "$backend_network_subnet" || "$backend_network_subnet" == "<no value>" ]]; then
  echo "Could not resolve the subnet for Docker network $SILICIUM_BACKEND_NETWORK_NAME" >&2
  exit 1
fi
export SILICIUM_HOST_GATEWAY="$host_gateway"
sed -i -e "s#host.docker.internal#$SILICIUM_HOST_GATEWAY#g" "$SILICIUM_NGINX_CONFIG"

# UFW commonly denies traffic arriving from Docker bridges even when the host
# itself can reach the service. Permit only this channel's bridge to reach the
# host-side orchestrator API required by the backend/proxy. The
# precise source subnet and gateway keep the rule isolated from other Docker
# projects and make repeated deployments converge without opening the ports
# publicly.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  ufw allow from "$backend_network_subnet" to "$host_gateway" port "$SILICIUM_ORCHESTRATOR_PORT" proto tcp \
    comment "Silicium ${RELEASE_CHANNEL} container control plane" >/dev/null
  if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
    p2p_port="${SILICIUM_P2P_PORT:-$((SILICIUM_ORCHESTRATOR_PORT + 1))}"
    for protocol in tcp udp; do
      ufw allow from "${SILICIUM_VPN_NETWORK:-10.77.0.0/24}" to "$SILICIUM_VPN_SERVER_ADDRESS" \
        port "$p2p_port" proto "$protocol" comment "Silicium dev Rust P2P" >/dev/null
      ufw allow from "${SILICIUM_DEV_MINIWORKER_SUBNET:-172.23.0.0/24}" \
        to "${SILICIUM_DEV_MINIWORKER_GATEWAY:-172.23.0.1}" \
        port "$p2p_port" proto "$protocol" comment "Silicium dev miniworker P2P" >/dev/null
    done
  fi
fi

# The backend image deliberately runs as an unprivileged user while the
# persistent bind mount is created by root on the host. Resolve the image's
# effective UID/GID after building it and give only the jobs directory to that
# user. Without this step, CreateJob cannot create <job-id>/input and returns
# "Could not create job input directory".
"${compose[@]}" build backend
# `docker compose images -q` reports the image attached to an existing
# container. During a rolling deploy that container can retain a deleted
# digest even after the fresh build succeeds. Inspect the explicit image tag
# produced by this compose file instead.
backend_image="silicium-backend:latest"
backend_image_id="$(docker image inspect --format '{{.Id}}' "$backend_image")"
[[ -n "$backend_image_id" ]] || { echo "Could not resolve the built backend image." >&2; exit 1; }
backend_identity="$(docker run --rm --entrypoint sh "$backend_image_id" -c 'printf "%s:%s" "$(id -u)" "$(id -g)"')"
[[ "$backend_identity" =~ ^[0-9]+:[0-9]+$ ]] || {
  echo "Could not resolve backend UID/GID: $backend_identity" >&2
  exit 1
}
backend_uid="${backend_identity%%:*}"
backend_gid="${backend_identity##*:}"
install -d -m 0750 -o "$backend_uid" -g "$backend_gid" "$SILICIUM_DATA_ROOT/site/jobs" "$SILICIUM_DATA_ROOT/site/runtime"

# Blockchain trace of jobs (BackEnd internal/chainproof): one Solana Memo
# transaction per finished job, signed by the channel's wallet. The dev
# channel creates its wallet; another channel is traced only once an
# operator has put a wallet in its data root. Both settings are rewritten on
# every deployment so an old value never lingers.
backend_env="$SILICIUM_CONFIG_DIR/backend.env"
solana_dir="$SILICIUM_DATA_ROOT/solana"
solana_wallet="$solana_dir/id.json"
if [[ "$RELEASE_CHANNEL" == "dev" && ! -s "$solana_wallet" ]]; then
  install -d -m 0750 "$solana_dir"
  python3 "$ROOT/deploy/release/solana_wallet.py" ensure "$solana_wallet" >/dev/null
fi
devnet_trace=0
if [[ -s "$solana_wallet" ]]; then
  chown "$backend_uid:$backend_gid" "$solana_dir" "$solana_wallet"
  chmod 0750 "$solana_dir"
  chmod 0400 "$solana_wallet"
  devnet_trace=1
  echo "Blockchain trace enabled; Solana wallet $(python3 "$ROOT/deploy/release/solana_wallet.py" address "$solana_wallet") (fund it on devnet: https://faucet.solana.com)."
fi
sed -i -E '/^SILICIUM_(DEVNET_TRACE(_MODE)?|SOLANA_WALLET)=/d' "$backend_env"
printf '%s\n' \
  "SILICIUM_DEVNET_TRACE=$devnet_trace" \
  'SILICIUM_DEVNET_TRACE_MODE=devnet' \
  'SILICIUM_SOLANA_WALLET=/var/lib/silicium/solana/id.json' >> "$backend_env"

# Releases before the Rust orchestrator built a tile pipeline for the Python
# job runner and pointed the backend at it; nothing reads it any more.
sed -i -E '/^SILICIUM_PIPELINE_BIN=/d' "$backend_env"

# Build the Rust control/peer node in the same portable musl target used by
# the host systemd service. The BackEnd container talks to its HTTP API on the
# host.
node_target="$SILICIUM_RUNTIME_ROOT/Network/target/node-alpine"
if ! docker run --rm \
  -v "$SILICIUM_RUNTIME_ROOT/Network:/src" \
  -v silicium-cargo-registry:/usr/local/cargo/registry \
  -w /src \
  rust:1-alpine \
  sh -c 'apk add --no-cache musl-dev >/dev/null && cargo build --release --locked -p p2p_node -p compute_daemon --target-dir /src/target/node-alpine' \
  || [[ ! -x "$node_target/release/p2p_node" ]]; then
  echo "Rust p2p node build failed; refusing to deploy." >&2
  exit 1
fi

orchestrator_unit="silicium-orchestrator${channel_service_suffix}.service"
if command -v systemctl >/dev/null 2>&1 && systemctl cat "$orchestrator_unit" >/dev/null 2>&1; then
  systemctl restart "$orchestrator_unit"
fi

# The host-side orchestrator (root) writes the files read by the BackEnd
# (heartbeat, peers) under its export directory; keep it reachable by the
# unprivileged API container user.
install -d -m 0770 -o "$backend_uid" -g "$backend_gid" "$SILICIUM_DATA_ROOT/network/orchestrator/export"

# Older production installations ran these processes as host systemd
# services. They may only be stopped during a production deployment; a dev
# deployment must leave the production units untouched.
if [[ "$RELEASE_CHANNEL" == "prod" ]]; then
  for legacy_unit in \
    silicium-backend.service \
    silicium-frontend.service \
    silicium-dashboard.service; do
    systemctl disable --now "$legacy_unit" 2>/dev/null || true
  done
fi

"${compose[@]}" up -d --build --remove-orphans
# Nginx resolves Compose service names at startup; recreate it after app
# containers so its upstream IPs cannot remain stale after a deployment.
"${compose[@]}" up -d --force-recreate proxy
"${compose[@]}" ps
if [[ "$RELEASE_CHANNEL" == "dev" ]]; then
  [[ -f "$SILICIUM_DEV_MINIWORKERS_ENV" ]] || {
    echo "Missing persistent miniworker configuration: $SILICIUM_DEV_MINIWORKERS_ENV" >&2
    exit 1
  }
  SILICIUM_CONFIG_DIR="$SILICIUM_CONFIG_DIR" \
    SILICIUM_DEV_MINIWORKERS_ENV="$SILICIUM_DEV_MINIWORKERS_ENV" \
    bash "$ROOT/deploy/linux/manage-dev-miniworkers.sh" up
fi
"$ROOT/deploy/linux/publish-update-manifest.sh"
if [[ -f "$ROOT/deploy/linux/publish-package-repositories.sh" ]]; then
  bash "$ROOT/deploy/linux/publish-package-repositories.sh" "$ROOT"
fi
