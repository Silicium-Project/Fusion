#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"
ENV_FILE="${INFRA_DIR}/.env"

[[ -f "$COMPOSE_FILE" ]] || { echo "Compose file not found at $COMPOSE_FILE" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: infra/bin/run-with-proxy.sh [service-name]

Starts the requested Silicium service together with the TLS proxy, auto-generates
a self-signed certificate when PROXY_TLS_MODE=local (default), and waits until the
proxy health endpoint answers.

Environment variables:
  PROXY_COMPOSE_PROFILES  Comma-separated list of compose profiles to enable
                          (defaults to "proxy").
  PROXY_UPSTREAM_HOST     Target service host (defaults to the service name).
  PROXY_UPSTREAM_PORT     Target RPC port (default 8899).
  PROXY_TLS_MODE          local | acme | internal (default local).
  PROXY_TLS_EMAIL         Email required for ACME mode.
  PROXY_TLS_CERT_PATH     Path to TLS certificate inside the proxy container
                          (default /etc/caddy/certs/tls.crt).
  PROXY_TLS_KEY_PATH      Path to TLS key inside the proxy container
                          (default /etc/caddy/certs/tls.key).
  PROXY_TLS_CERT_PATH_HOST  Host path for generated TLS certificate (local mode).
  PROXY_TLS_KEY_PATH_HOST   Host path for generated TLS key (local mode).
  PROXY_SITE_ADDRESS      Address served by Caddy (default :443).
  PROXY_HTTP_PORT         Host port mapped to the proxy's port 80 (default 9080).
  PROXY_HTTPS_PORT        Host port mapped to the proxy's port 443 (default 9443).
  PROXY_TEST_URL          URL used to probe the proxy (default https://localhost:9443/healthz, tied to PROXY_HTTPS_PORT).
  PROXY_SELF_SIGN_CN      Common Name for self-signed certs (default rpc.local.silicium).
  PROXY_SELF_SIGN_DAYS    Validity in days for generated certs (default 30).
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v docker >/dev/null 2>&1 || { echo "docker CLI not found." >&2; exit 1; }

COMPOSE_GLOBAL_ARGS=()
if [[ -f "$ENV_FILE" ]]; then
  COMPOSE_GLOBAL_ARGS+=(--env-file "$ENV_FILE")
fi
COMPOSE_GLOBAL_ARGS+=(-f "$COMPOSE_FILE")

SERVICE="${1:-silicium-localnet}"
UPSTREAM_PORT="${PROXY_UPSTREAM_PORT:-8899}"
UPSTREAM_HOST="${PROXY_UPSTREAM_HOST:-$SERVICE}"
TLS_MODE="${PROXY_TLS_MODE:-local}"
TLS_EMAIL="${PROXY_TLS_EMAIL:-}"
CERT_ROOT="${INFRA_DIR}/docker/reverse-proxy/certs"
CERT_PATH_HOST="${PROXY_TLS_CERT_PATH_HOST:-$CERT_ROOT/tls.crt}"
KEY_PATH_HOST="${PROXY_TLS_KEY_PATH_HOST:-$CERT_ROOT/tls.key}"
CERT_PATH_CONTAINER="${PROXY_TLS_CERT_PATH:-/etc/caddy/certs/tls.crt}"
KEY_PATH_CONTAINER="${PROXY_TLS_KEY_PATH:-/etc/caddy/certs/tls.key}"
SITE_ADDRESS="${PROXY_SITE_ADDRESS:-:443}"
HOST_HTTPS_PORT="${PROXY_HTTPS_PORT:-9443}"
HOST_HTTP_PORT="${PROXY_HTTP_PORT:-9080}"
TEST_URL="${PROXY_TEST_URL:-https://localhost:${HOST_HTTPS_PORT}/healthz}"
TEST_MODE="${PROXY_TEST_MODE:-host}"
TEST_IMAGE="${PROXY_TEST_IMAGE:-curlimages/curl:8.6.0}"
TEST_NETWORK="${PROXY_TEST_NETWORK:-}"
SELF_SIGN_CN="${PROXY_SELF_SIGN_CN:-rpc.local.silicium}"
SELF_SIGN_DAYS="${PROXY_SELF_SIGN_DAYS:-30}"
if [[ "$TEST_MODE" == "container" ]]; then
  if [[ -z "$PROXY_TEST_URL" ]]; then
    TEST_URL="https://silicium-proxy/healthz"
  fi
  if [[ -z "$TEST_NETWORK" ]]; then
    PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$INFRA_DIR")}"
    TEST_NETWORK="${PROJECT_NAME}_default"
  fi
fi

IFS=',' read -r -a PROFILE_LIST <<<"${PROXY_COMPOSE_PROFILES:-proxy}"
PROFILE_ARGS=()
for raw in "${PROFILE_LIST[@]}"; do
  profile="$(echo "$raw" | xargs)"
  [[ -n "$profile" ]] && PROFILE_ARGS+=(--profile "$profile")
done
[[ ${#PROFILE_ARGS[@]} -eq 0 ]] && PROFILE_ARGS+=(--profile proxy)

ensure_self_signed() {
  [[ "$TLS_MODE" != "local" ]] && return 0
  if [[ -f "$CERT_PATH_HOST" && -f "$KEY_PATH_HOST" ]]; then
    return 0
  fi
  command -v openssl >/dev/null 2>&1 || { echo "openssl CLI not found (required for local TLS mode)." >&2; exit 1; }
  echo "Generating self-signed certificate for $SELF_SIGN_CN ($SELF_SIGN_DAYS days)"
  mkdir -p "$(dirname "$CERT_PATH_HOST")"
  old_umask="$(umask)"
  umask 077
  openssl req -x509 -nodes -newkey rsa:2048 \
    -days "$SELF_SIGN_DAYS" \
    -keyout "$KEY_PATH_HOST" \
    -out "$CERT_PATH_HOST" \
    -subj "/CN=$SELF_SIGN_CN"
  umask "$old_umask"
  chmod 600 "$KEY_PATH_HOST" 2>/dev/null || true
}

ensure_self_signed

echo "Starting $SERVICE with proxy (profiles: ${PROFILE_ARGS[*]})"
PROXY_UPSTREAM_HOST="$UPSTREAM_HOST" \
PROXY_UPSTREAM_PORT="$UPSTREAM_PORT" \
PROXY_TLS_MODE="$TLS_MODE" \
PROXY_TLS_EMAIL="$TLS_EMAIL" \
PROXY_TLS_CERT_PATH="$CERT_PATH_CONTAINER" \
PROXY_TLS_KEY_PATH="$KEY_PATH_CONTAINER" \
PROXY_SITE_ADDRESS="$SITE_ADDRESS" \
PROXY_HTTPS_PORT="$HOST_HTTPS_PORT" \
PROXY_HTTP_PORT="$HOST_HTTP_PORT" \
docker compose "${COMPOSE_GLOBAL_ARGS[@]}" "${PROFILE_ARGS[@]}" up -d "$SERVICE" silicium-proxy

echo "Waiting for proxy health at $TEST_URL ..."
probe() {
  if [[ "$TEST_MODE" == "container" ]]; then
    docker run --rm --network "$TEST_NETWORK" "$TEST_IMAGE" \
      -sk --max-time 2 "$TEST_URL" >/dev/null
  else
    curl -sk --max-time 2 "$TEST_URL" >/dev/null
  fi
}
for _ in $(seq 1 30); do
  if probe; then
    echo "Proxy is up: $TEST_URL"
    exit 0
  fi
  sleep 2
done

echo "Proxy did not become ready in time. Check docker compose logs." >&2
exit 1
