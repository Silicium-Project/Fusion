#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"
ENV_FILE="${INFRA_DIR}/.env"

# shellcheck source=infra/bin/i18n.sh
. "$SCRIPT_DIR/i18n.sh"

[[ -f "$COMPOSE_FILE" ]] || { sil_i18n_echo "infra.proxy.compose_not_found" "$COMPOSE_FILE" >&2; exit 1; }

usage() {
  sil_i18n_echo "infra.proxy.usage"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v docker >/dev/null 2>&1 || { sil_i18n_echo "infra.proxy.docker_missing" >&2; exit 1; }

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
if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
  [[ "$CERT_PATH_CONTAINER" == /* ]] && CERT_PATH_CONTAINER="/$CERT_PATH_CONTAINER"
  [[ "$KEY_PATH_CONTAINER" == /* ]] && KEY_PATH_CONTAINER="/$KEY_PATH_CONTAINER"
fi
SITE_ADDRESS="${PROXY_SITE_ADDRESS:-:443}"
HOST_HTTPS_PORT="${PROXY_HTTPS_PORT:-9443}"
HOST_HTTP_PORT="${PROXY_HTTP_PORT:-9080}"
TEST_URL="${PROXY_TEST_URL:-https://localhost:${HOST_HTTPS_PORT}/healthz}"
TEST_RESOLVE="${PROXY_TEST_RESOLVE:-}"
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
  command -v openssl >/dev/null 2>&1 || { sil_i18n_echo "infra.proxy.openssl_missing" >&2; exit 1; }
  sil_i18n_echo "infra.proxy.gen_self_signed" "$SELF_SIGN_CN" "$SELF_SIGN_DAYS"
  mkdir -p "$(dirname "$CERT_PATH_HOST")"
  old_umask="$(umask)"
  umask 077
  # Prevent MSYS/Git Bash from rewriting the OpenSSL subject as a Windows path.
  cert_dir="$(dirname "$CERT_PATH_HOST")" # i18n:ignore
  key_name="$(basename "$KEY_PATH_HOST")" # i18n:ignore
  cert_name="$(basename "$CERT_PATH_HOST")" # i18n:ignore
  (
    cd "$cert_dir"
    MSYS_NO_PATHCONV=1 openssl req -x509 -nodes -newkey rsa:2048 \
      -days "$SELF_SIGN_DAYS" \
      -keyout "$key_name" \
      -out "$cert_name" \
      -subj "/CN=$SELF_SIGN_CN"
  )
  umask "$old_umask"
  chmod 600 "$KEY_PATH_HOST" 2>/dev/null || true
}

ensure_self_signed

sil_i18n_echo "infra.proxy.start_service" "$SERVICE" "${PROFILE_ARGS[*]}"
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

sil_i18n_echo "infra.proxy.wait_health" "$TEST_URL"
probe() {
  if [[ "$TEST_MODE" == "container" ]]; then
    docker run --rm --network "$TEST_NETWORK" "$TEST_IMAGE" \
      -sk --max-time 2 "$TEST_URL" >/dev/null
  else
    if [[ -n "$TEST_RESOLVE" ]]; then
      curl -sk --max-time 2 --resolve "$TEST_RESOLVE" "$TEST_URL" >/dev/null
    else
      curl -sk --max-time 2 "$TEST_URL" >/dev/null
    fi
  fi
}
for _ in $(seq 1 30); do
  if probe; then
    sil_i18n_echo "infra.proxy.up" "$TEST_URL"
    exit 0
  fi
  sleep 2
done

sil_i18n_echo "infra.proxy.not_ready" >&2
if [[ "$TEST_MODE" != "container" ]]; then
  docker compose "${COMPOSE_GLOBAL_ARGS[@]}" "${PROFILE_ARGS[@]}" ps >&2 || true
  if [[ -n "$TEST_RESOLVE" ]]; then
    curl -vk --max-time 5 --resolve "$TEST_RESOLVE" "$TEST_URL" >&2 || true
  else
    curl -vk --max-time 5 "$TEST_URL" >&2 || true
  fi
fi
exit 1
