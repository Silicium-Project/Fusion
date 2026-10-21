#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/compose/dev-miniworkers.yml"
ENV_FILE="${SILICIUM_DEV_MINIWORKERS_ENV:-$ROOT_DIR/deploy/env/dev-miniworkers.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Copy deploy/env/dev-miniworkers.env.example and set the bootstrap address." >&2
  exit 2
fi
COUNT_IN_FILE="$(sed -n 's/^SILICIUM_DEV_MINIWORKERS=//p' "$ENV_FILE" | head -n 1)"
COUNT="${SILICIUM_DEV_MINIWORKERS:-${COUNT_IN_FILE:-20}}"
if [[ ! "$COUNT" =~ ^[0-9]+$ ]] || (( COUNT < 20 || COUNT > 24 )); then
  echo "SILICIUM_DEV_MINIWORKERS must be between 20 and 24." >&2
  exit 2
fi

SILICIUM_DEV_BOOTSTRAP_PEER="$(sed -n 's/^SILICIUM_DEV_BOOTSTRAP_PEER=//p' "$ENV_FILE" | head -n 1)"
if [[ -z "$SILICIUM_DEV_BOOTSTRAP_PEER" ]]; then
  echo "SILICIUM_DEV_BOOTSTRAP_PEER is empty in $ENV_FILE." >&2
  exit 2
fi

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
active_services=()
inactive_services=()
for ((index = 1; index <= 24; index += 1)); do
  service="miniworker-$(printf '%02d' "$index")"
  if (( index <= COUNT )); then
    active_services+=("$service")
  else
    inactive_services+=("$service")
  fi
done
case "${1:-status}" in
  up)
    sudo "${compose[@]}" rm --stop --force "${inactive_services[@]}" >/dev/null 2>&1 || true
    sudo "${compose[@]}" up -d --build --remove-orphans "${active_services[@]}"
    ;;
  down)
    sudo "${compose[@]}" down
    ;;
  status)
    sudo "${compose[@]}" ps
    ;;
  logs)
    sudo "${compose[@]}" logs --tail=80 -f "${active_services[@]}"
    ;;
  scale)
    sudo "${compose[@]}" rm --stop --force "${inactive_services[@]}" >/dev/null 2>&1 || true
    sudo "${compose[@]}" up -d --remove-orphans "${active_services[@]}"
    ;;
  *)
    echo "Usage: $0 {up|down|status|logs|scale}" >&2
    exit 2
    ;;
esac
