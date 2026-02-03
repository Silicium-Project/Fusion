#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_DIR="${ROOT_DIR}/infra"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"
ENV_FILE="${INFRA_DIR}/.env"
SMOKE_HTTP_PORT="${SMOKE_HTTP_PORT:-19080}"
SMOKE_HTTPS_PORT="${SMOKE_HTTPS_PORT:-19443}"
SMOKE_HOST="${SMOKE_HOST:-localhost}"
SMOKE_MODE="${SMOKE_MODE:-host}"  # host|container
PROFILE_ARGS=(--profile proxy --profile smoke)
COMPOSE_ARGS=()
[[ -f "$ENV_FILE" ]] && COMPOSE_ARGS+=(--env-file "$ENV_FILE")
COMPOSE_ARGS+=(-f "$COMPOSE_FILE")
PROXY_TEST_URL_DEFAULT="https://${SMOKE_HOST}:${SMOKE_HTTPS_PORT}/healthz"
if [[ "$SMOKE_MODE" == "container" ]]; then
  PROXY_TEST_URL_DEFAULT=""
fi

cleanup() {
  docker compose "${COMPOSE_ARGS[@]}" "${PROFILE_ARGS[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

PROXY_COMPOSE_PROFILES=proxy,smoke \
PROXY_UPSTREAM_HOST=proxy-smoke-target \
PROXY_HTTPS_PORT="$SMOKE_HTTPS_PORT" \
PROXY_HTTP_PORT="$SMOKE_HTTP_PORT" \
PROXY_TEST_MODE="${PROXY_TEST_MODE:-$SMOKE_MODE}" \
PROXY_TEST_NETWORK="${PROXY_TEST_NETWORK:-}" \
PROXY_TEST_URL="${PROXY_TEST_URL:-$PROXY_TEST_URL_DEFAULT}" \
"${INFRA_DIR}/bin/run-with-proxy.sh" proxy-smoke-target

if [[ "$SMOKE_MODE" == "host" ]]; then
  curl -sk --max-time 5 "https://${SMOKE_HOST}:${SMOKE_HTTPS_PORT}/healthz" | grep -q 'ok'
fi
