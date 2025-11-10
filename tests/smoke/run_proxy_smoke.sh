#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_DIR="${ROOT_DIR}/infra"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"
ENV_FILE="${INFRA_DIR}/.env"
SMOKE_HTTP_PORT="${SMOKE_HTTP_PORT:-19080}"
SMOKE_HTTPS_PORT="${SMOKE_HTTPS_PORT:-19443}"
PROFILE_ARGS=(--profile proxy --profile smoke)
COMPOSE_ARGS=()
[[ -f "$ENV_FILE" ]] && COMPOSE_ARGS+=(--env-file "$ENV_FILE")
COMPOSE_ARGS+=(-f "$COMPOSE_FILE")

cleanup() {
  docker compose "${COMPOSE_ARGS[@]}" "${PROFILE_ARGS[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

PROXY_COMPOSE_PROFILES=proxy,smoke \
PROXY_UPSTREAM_HOST=proxy-smoke-target \
PROXY_HTTPS_PORT="$SMOKE_HTTPS_PORT" \
PROXY_HTTP_PORT="$SMOKE_HTTP_PORT" \
PROXY_TEST_URL="https://localhost:${SMOKE_HTTPS_PORT}/healthz" \
"${INFRA_DIR}/bin/run-with-proxy.sh" proxy-smoke-target

curl -sk --max-time 5 "https://localhost:${SMOKE_HTTPS_PORT}/healthz" | grep -q 'ok'
