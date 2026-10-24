#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium-dev}"
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
CHANNEL_TOOL="$ROOT/deploy/release/channel.py"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/prepare-dev-config.sh $ROOT" >&2
  exit 1
fi
[[ "$RELEASE_CHANNEL" == "dev" ]] || {
  echo "This bootstrap script is intentionally restricted to the dev channel." >&2
  exit 1
}
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null

channel_field() { python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field "$1"; }
CONFIG_DIR="$(channel_field config_dir)"
DATA_ROOT="$(channel_field data_dir)"
PUBLIC_BASE_URL="$(channel_field public_base_url)"
ORCHESTRATOR_PORT="$(channel_field orchestrator_port)"
BACKEND_HTTP_PORT="$(channel_field backend_http_port)"
BACKEND_P2P_PORT="$(channel_field backend_p2p_port)"
FRONTEND_HTTP_PORT="$(channel_field frontend_http_port)"
REPUTATION_HTTP_PORT="$(channel_field reputation_http_port)"
TURN_PORT="$(channel_field turn_port)"
TURN_TLS_PORT="$(channel_field turn_tls_port)"
TURN_RELAY_MIN_PORT="$(channel_field turn_relay_min_port)"
TURN_RELAY_MAX_PORT="$(channel_field turn_relay_max_port)"
VPN_INTERFACE="$(channel_field vpn_interface)"
VPN_NETWORK="$(channel_field vpn_network)"
VPN_SERVER_ADDRESS="$(channel_field vpn_server_address)"
VPN_LISTEN_PORT="$(channel_field vpn_listen_port)"
VPN_ENDPOINT="$(channel_field vpn_endpoint)"
VPN_PROXY_BIND_ADDRESS="$(channel_field vpn_proxy_bind_address)"

# Provision the private dev ingress before Compose is configured to bind to its
# VPN address. The script is idempotent and refuses to claim an unmanaged
# WireGuard interface or overwrite an unrelated configuration.
if [[ "${SILICIUM_SKIP_VPN_BOOTSTRAP:-0}" != "1" ]]; then
  bash "$ROOT/deploy/vpn/install-server.sh" "$ROOT"
fi

release_version="${SILICIUM_RELEASE_VERSION:-$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$ROOT/apps/silicium-node/package.json")}"
release_build="${SILICIUM_RELEASE_BUILD:-$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf local)}"

mkdir -p "$CONFIG_DIR" "$DATA_ROOT"/site/jobs "$DATA_ROOT"/site/runtime \
  "$DATA_ROOT"/network "$DATA_ROOT"/solana "$DATA_ROOT"/downloads \
  "$DATA_ROOT"/coturn "$DATA_ROOT"/tls/live/vps-910c1dbc.vps.ovh.net

copy_if_missing() {
  local target="$1"
  local example="$2"
  if [[ ! -f "$target" ]]; then
    cp "$ROOT/$example" "$target"
  fi
}

set_env_value() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  if grep -q -E "^${key}=" "$env_file"; then
    sed -i -E "s#^${key}=.*#${key}=${value}#" "$env_file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
  fi
}

copy_if_missing "$CONFIG_DIR/backend.env" deploy/env/backend.example.env
copy_if_missing "$CONFIG_DIR/frontend.env" deploy/env/frontend.example.env
copy_if_missing "$CONFIG_DIR/orchestrator.env" deploy/env/orchestrator.example.env
copy_if_missing "$CONFIG_DIR/compose.env" deploy/env/compose.example.env
copy_if_missing "$CONFIG_DIR/update-channels.env" deploy/env/update-channels.example.env
copy_if_missing "$CONFIG_DIR/miniworkers.env" deploy/env/dev-miniworkers.env.example

compose_env="$CONFIG_DIR/compose.env"
backend_env="$CONFIG_DIR/backend.env"
frontend_env="$CONFIG_DIR/frontend.env"
orchestrator_env="$CONFIG_DIR/orchestrator.env"
updates_env="$CONFIG_DIR/update-channels.env"
miniworkers_env="$CONFIG_DIR/miniworkers.env"

# Never keep the example control token on a network-facing node API. Preserve
# an operator-provided token, but replace missing and known placeholder values
# with a fresh 256-bit random token during dev bootstrap.
control_token="$(grep -E '^SILICIUM_NODE_CONTROL_TOKEN=' "$orchestrator_env" | tail -n 1 | cut -d= -f2- || true)"
if [[ -z "$control_token" || "$control_token" == GENERATE_* || "$control_token" == change-me-* ]]; then
  set_env_value "$orchestrator_env" SILICIUM_NODE_CONTROL_TOKEN "$(openssl rand -hex 32)"
fi
control_token="$(grep -E '^SILICIUM_NODE_CONTROL_TOKEN=' "$orchestrator_env" | tail -n 1 | cut -d= -f2- || true)"
[[ -n "$control_token" ]] || { echo "Could not provision the node control token." >&2; exit 1; }
# Keep manual Compose invocations aligned with the host orchestrator. The
# deploy script also sources orchestrator.env, which remains canonical.
set_env_value "$compose_env" SILICIUM_NODE_CONTROL_TOKEN "$control_token"

# Payment submission must remain closed until the Devnet program has been
# upgraded and its worker-payout instruction is verified. Preserve an
# operator's explicit opt-in, otherwise default every component to disabled.
payments_enabled="${SILICIUM_SOLANA_PAYMENTS_ENABLED:-$(grep -E '^SILICIUM_SOLANA_PAYMENTS_ENABLED=' "$compose_env" | tail -n 1 | cut -d= -f2- || true)}"
case "${payments_enabled,,}" in
  1|true|yes|on) payments_enabled=1 ;;
  *) payments_enabled=0 ;;
esac

set_env_value "$miniworkers_env" SILICIUM_SOLANA_RPC https://solana-devnet.api.onfinality.io/public
set_env_value "$miniworkers_env" SILICIUM_VERIFICATIONS_REQUIRED 2
set_env_value "$miniworkers_env" SILICIUM_SIL_MINT F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP
set_env_value "$miniworkers_env" SILICIUM_SOLANA_PROGRAM_ID 64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG
set_env_value "$miniworkers_env" SILICIUM_SOLANA_PAYMENTS_ENABLED "$payments_enabled"

db_password="$(grep -E '^POSTGRES_PASSWORD=' "$compose_env" | tail -n 1 | cut -d= -f2- || true)"
if [[ -z "$db_password" || "$db_password" == GENERATE_* || "$db_password" == CHANGE_* ]]; then
  db_password="$(openssl rand -hex 32)"
fi
jwt_secret="$(grep -E '^JWT_SECRET_KEY=' "$backend_env" | tail -n 1 | cut -d= -f2- || true)"
if [[ -z "$jwt_secret" || "$jwt_secret" == GENERATE_* || "$jwt_secret" == CHANGE_* ]]; then
  jwt_secret="$(openssl rand -hex 32)"
fi

set_env_value "$compose_env" POSTGRES_DB silicium_dev
set_env_value "$compose_env" POSTGRES_USER silicium_dev
set_env_value "$compose_env" POSTGRES_PASSWORD "$db_password"
set_env_value "$compose_env" SILICIUM_RELEASE_CHANNEL dev
set_env_value "$compose_env" SILICIUM_SIL_MINT F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP
set_env_value "$compose_env" SILICIUM_SOLANA_RPC https://solana-devnet.api.onfinality.io/public
set_env_value "$compose_env" SILICIUM_SOLANA_CLUSTER devnet
set_env_value "$compose_env" SILICIUM_SIL_POOL_ID 66Un5iGRBuzE4kcVQkDkKrtZUVnTiXnxpUHoFL3mEsdS
set_env_value "$compose_env" SILICIUM_SOLANA_PROGRAM_ID 64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG
set_env_value "$compose_env" SILICIUM_SOLANA_PAYMENTS_ENABLED "$payments_enabled"
set_env_value "$compose_env" SILICIUM_RELEASE_VERSION "$release_version"
set_env_value "$compose_env" SILICIUM_RELEASE_BUILD "$release_build"
set_env_value "$compose_env" SILICIUM_COMPOSE_PROJECT_NAME silicium-dev
set_env_value "$compose_env" SILICIUM_RUNTIME_ROOT "$ROOT"
set_env_value "$compose_env" SILICIUM_DATA_ROOT "$DATA_ROOT"
set_env_value "$compose_env" SILICIUM_CONFIG_DIR "$CONFIG_DIR"
set_env_value "$compose_env" SILICIUM_BACKEND_HTTP_PORT "$BACKEND_HTTP_PORT"
set_env_value "$compose_env" SILICIUM_BACKEND_P2P_PORT "$BACKEND_P2P_PORT"
set_env_value "$compose_env" SILICIUM_FRONTEND_HTTP_PORT "$FRONTEND_HTTP_PORT"
set_env_value "$compose_env" SILICIUM_REPUTATION_HTTP_PORT "$REPUTATION_HTTP_PORT"
set_env_value "$compose_env" SILICIUM_ORCHESTRATOR_PORT "$ORCHESTRATOR_PORT"
set_env_value "$compose_env" SILICIUM_TURN_PORT "$TURN_PORT"
set_env_value "$compose_env" SILICIUM_TURN_TLS_PORT "$TURN_TLS_PORT"
set_env_value "$compose_env" SILICIUM_TURN_RELAY_MIN_PORT "$TURN_RELAY_MIN_PORT"
set_env_value "$compose_env" SILICIUM_TURN_RELAY_MAX_PORT "$TURN_RELAY_MAX_PORT"
set_env_value "$compose_env" SILICIUM_VPN_INTERFACE "$VPN_INTERFACE"
set_env_value "$compose_env" SILICIUM_VPN_NETWORK "$VPN_NETWORK"
set_env_value "$compose_env" SILICIUM_VPN_SERVER_ADDRESS "$VPN_SERVER_ADDRESS"
set_env_value "$compose_env" SILICIUM_VPN_LISTEN_PORT "$VPN_LISTEN_PORT"
set_env_value "$compose_env" SILICIUM_VPN_ENDPOINT "$VPN_ENDPOINT"
set_env_value "$compose_env" SILICIUM_PROXY_BIND_ADDRESS "$VPN_PROXY_BIND_ADDRESS"
set_env_value "$compose_env" SILICIUM_PROXY_HTTP_PORT 8081
set_env_value "$compose_env" SILICIUM_PROXY_HTTPS_PORT 8443
set_env_value "$compose_env" SILICIUM_BACKEND_NETWORK_NAME silicium-dev-backend
set_env_value "$compose_env" SILICIUM_FRONTEND_NETWORK_NAME silicium-dev-frontend
set_env_value "$compose_env" SILICIUM_TLS_ROOT "$DATA_ROOT/tls"
set_env_value "$miniworkers_env" SILICIUM_DEV_MINIWORKERS_PAIRING_DIR "$DATA_ROOT/miniworker-pairing"
set_env_value "$compose_env" SILICIUM_TURN_EXTERNAL_IP "$VPN_SERVER_ADDRESS"
set_env_value "$compose_env" SILICIUM_PUBLIC_ORCHESTRATOR_URL "$PUBLIC_BASE_URL/orchestrator"
set_env_value "$compose_env" SILICIUM_CORS_ALLOWED_ORIGINS "$PUBLIC_BASE_URL"

set_env_value "$backend_env" HOST 0.0.0.0
set_env_value "$backend_env" PORT 8080
set_env_value "$backend_env" CORS_ALLOWED_ORIGINS "$PUBLIC_BASE_URL"
set_env_value "$backend_env" SILICIUM_RELEASE_CHANNEL dev
set_env_value "$backend_env" SILICIUM_RELEASE_VERSION "$release_version"
set_env_value "$backend_env" SILICIUM_RELEASE_BUILD "$release_build"
set_env_value "$backend_env" DATABASE_URL "postgres://silicium_dev:${db_password}@127.0.0.1:5432/silicium_dev?sslmode=disable"
set_env_value "$backend_env" JWT_SECRET_KEY "$jwt_secret"
set_env_value "$backend_env" SILICIUM_NETWORK_ROOT /opt/silicium/Network
set_env_value "$backend_env" SILICIUM_ORCHESTRATOR_EXPORT_DIR /var/lib/silicium/network/orchestrator/export
set_env_value "$backend_env" SILICIUM_ORCHESTRATOR_NODE_ID orchestrator-dev-1
set_env_value "$backend_env" SILICIUM_SITE_STORAGE_DIR /var/lib/silicium/site/jobs
set_env_value "$backend_env" SILICIUM_WORKLOAD_STORAGE_DIR /var/lib/silicium/site/runtime
set_env_value "$backend_env" SILICIUM_ORCHESTRATOR_HOST "$VPN_SERVER_ADDRESS"
set_env_value "$backend_env" SILICIUM_SOLANA_WALLET /var/lib/silicium/solana/id.json
set_env_value "$backend_env" SILICIUM_DEVNET_TRACE 0
set_env_value "$backend_env" SILICIUM_DEVNET_TRACE_MODE devnet
set_env_value "$backend_env" SILICIUM_SOLANA_RPC https://solana-devnet.api.onfinality.io/public
set_env_value "$backend_env" SILICIUM_SOLANA_PROGRAM_ID 64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG
set_env_value "$backend_env" SILICIUM_SIL_MINT F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP
set_env_value "$backend_env" SILICIUM_SOLANA_PAYMENTS_ENABLED "$payments_enabled"

set_env_value "$frontend_env" HOST 0.0.0.0
set_env_value "$frontend_env" PORT 3000
set_env_value "$frontend_env" NUXT_PUBLIC_RELEASE_CHANNEL dev
set_env_value "$frontend_env" NUXT_PUBLIC_RELEASE_VERSION "$release_version"
set_env_value "$frontend_env" NUXT_PUBLIC_RELEASE_BUILD "$release_build"
set_env_value "$frontend_env" NUXT_PUBLIC_API_BASE /api
set_env_value "$frontend_env" NUXT_PUBLIC_SOLANA_RPC https://solana-devnet.api.onfinality.io/public
set_env_value "$frontend_env" NUXT_PUBLIC_SOLANA_CLUSTER devnet
set_env_value "$frontend_env" NUXT_PUBLIC_SIL_MINT F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP
set_env_value "$frontend_env" NUXT_PUBLIC_SIL_POOL_ID 66Un5iGRBuzE4kcVQkDkKrtZUVnTiXnxpUHoFL3mEsdS
set_env_value "$frontend_env" NUXT_PUBLIC_SOLANA_PAYMENTS_ENABLED "$payments_enabled"
set_env_value "$frontend_env" NUXT_PUBLIC_UPDATE_MANIFEST_URL /downloads/update-manifest.json
set_env_value "$frontend_env" NUXT_PUBLIC_ORCHESTRATOR_URL "$PUBLIC_BASE_URL/orchestrator"
set_env_value "$frontend_env" NUXT_PUBLIC_NODE_APP_WINDOWS_URL "$PUBLIC_BASE_URL/downloads/silicium-node-windows.exe"
set_env_value "$frontend_env" NUXT_PUBLIC_NODE_APP_WINDOWS_DEV_URL "$PUBLIC_BASE_URL/downloads/silicium-node-windows-dev.exe"
set_env_value "$frontend_env" NUXT_PUBLIC_NODE_APP_LINUX_DEV_URL "$PUBLIC_BASE_URL/downloads/silicium-node-linux-dev.AppImage"
set_env_value "$frontend_env" NUXT_PUBLIC_NODE_APP_LINUX_DEV_DEB_URL "$PUBLIC_BASE_URL/downloads/silicium-node-linux-dev.deb"
set_env_value "$frontend_env" NUXT_PUBLIC_NODE_APP_LINUX_DEV_RPM_URL "$PUBLIC_BASE_URL/downloads/silicium-node-linux-dev.rpm"

set_env_value "$orchestrator_env" SILICIUM_NODE_ID orchestrator-dev-1
set_env_value "$orchestrator_env" SILICIUM_NODE_ROLES resource,storage
set_env_value "$orchestrator_env" SILICIUM_ENABLE_MDNS 0
set_env_value "$orchestrator_env" SILICIUM_SOLANA_PAYMENTS_ENABLED "$payments_enabled"
set_env_value "$orchestrator_env" SILICIUM_VERIFICATIONS_REQUIRED 2
set_env_value "$orchestrator_env" SILICIUM_NODE_PORT "$ORCHESTRATOR_PORT"
set_env_value "$orchestrator_env" SILICIUM_P2P_PORT "$((ORCHESTRATOR_PORT + 1))"
set_env_value "$orchestrator_env" SILICIUM_RELEASE_CHANNEL dev
set_env_value "$orchestrator_env" SILICIUM_APP_VERSION "$release_version"
set_env_value "$orchestrator_env" SILICIUM_RELEASE_BUILD "$release_build"
set_env_value "$orchestrator_env" SILICIUM_NODE_ADVERTISE_URL "$PUBLIC_BASE_URL/orchestrator"
set_env_value "$orchestrator_env" SILICIUM_EXPORT_DIR "$DATA_ROOT/network/orchestrator/export"
set_env_value "$orchestrator_env" SILICIUM_STATE_DIR "$DATA_ROOT/network/orchestrator/state"


set_env_value "$updates_env" SILICIUM_DOWNLOADS_DIR "$DATA_ROOT/downloads"
set_env_value "$updates_env" SILICIUM_DOWNLOAD_BASE_URL "$PUBLIC_BASE_URL/downloads"
set_env_value "$updates_env" SILICIUM_DEV_VERSION "$release_version"
set_env_value "$updates_env" SILICIUM_UPDATE_SIGNING_KEY "$CONFIG_DIR/update-signing-key.pem"

if [[ ! -s "$CONFIG_DIR/update-signing-key.pem" ]]; then
  openssl genpkey -algorithm Ed25519 -out "$CONFIG_DIR/update-signing-key.pem" >/dev/null 2>&1
fi
chmod 0600 "$CONFIG_DIR/update-signing-key.pem"

tls_ca_key="$CONFIG_DIR/dev-ca.key.pem"
tls_ca_cert="$DATA_ROOT/tls/dev-ca.crt.pem"
tls_cert="$DATA_ROOT/tls/live/vps-910c1dbc.vps.ovh.net/fullchain.pem"
tls_key="$DATA_ROOT/tls/live/vps-910c1dbc.vps.ovh.net/privkey.pem"
if [[ ! -s "$tls_ca_key" || ! -s "$tls_ca_cert" ]]; then
  umask 077
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$tls_ca_key" >/dev/null 2>&1
  openssl req -x509 -new -sha256 -days 3650 \
    -key "$tls_ca_key" -out "$tls_ca_cert" \
    -subj "/CN=Silicium Development CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" >/dev/null 2>&1
fi
chmod 0600 "$tls_ca_key"
chmod 0644 "$tls_ca_cert"

server_cert_needs_refresh=0
if [[ ! -s "$tls_cert" || ! -s "$tls_key" ]]; then
  server_cert_needs_refresh=1
elif ! openssl x509 -in "$tls_cert" -noout -text 2>/dev/null | grep -q "IP Address:${VPN_SERVER_ADDRESS}"; then
  server_cert_needs_refresh=1
fi
if [[ "$server_cert_needs_refresh" -eq 1 ]]; then
  csr_file="$(mktemp)"
  ext_file="$(mktemp)"
  serial_file="${tls_ca_cert%.*}.srl"
  trap 'rm -f "$csr_file" "$ext_file" "$serial_file"' EXIT
  umask 077
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$tls_key" >/dev/null 2>&1
  openssl req -new -sha256 -key "$tls_key" -out "$csr_file" \
    -subj "/CN=$VPN_SERVER_ADDRESS" >/dev/null 2>&1
  printf '%s\n' \
    "basicConstraints=critical,CA:FALSE" \
    "keyUsage=critical,digitalSignature,keyEncipherment" \
    "extendedKeyUsage=serverAuth" \
    "subjectAltName=IP:${VPN_SERVER_ADDRESS},DNS:vps-910c1dbc.vps.ovh.net" > "$ext_file"
  openssl x509 -req -sha256 -days 825 \
    -in "$csr_file" -CA "$tls_ca_cert" -CAkey "$tls_ca_key" \
    -CAcreateserial -CAserial "$serial_file" -out "$tls_cert" \
    -extfile "$ext_file" >/dev/null 2>&1
  rm -f "$csr_file" "$ext_file" "$serial_file"
  trap - EXIT
fi
chmod 0600 "$tls_key"
chmod 0644 "$tls_cert"
install -D -m 0644 "$tls_cert" "$DATA_ROOT/coturn/fullchain.pem"
install -D -m 0600 "$tls_key" "$DATA_ROOT/coturn/privkey.pem"

chmod 0750 "$CONFIG_DIR"
chmod 0640 "$CONFIG_DIR"/*.env
chmod 0600 "$CONFIG_DIR/miniworkers.env"
echo "Development configuration prepared in $CONFIG_DIR with isolated data under $DATA_ROOT."
