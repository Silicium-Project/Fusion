#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/compose/dev-miniworkers.yml"
ENV_FILE="${SILICIUM_DEV_MINIWORKERS_ENV:-${SILICIUM_CONFIG_DIR:-/etc/silicium-dev}/miniworkers.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run prepare-dev-config.sh to create the persistent worker configuration." >&2
  exit 2
fi
ORCHESTRATOR_ENV="${SILICIUM_ORCHESTRATOR_ENV:-${SILICIUM_CONFIG_DIR:-/etc/silicium-dev}/orchestrator.env}"
worker_version="${SILICIUM_DEV_MINIWORKERS_APP_VERSION:-${SILICIUM_APP_VERSION:-}}"
if [[ -z "$worker_version" && -f "$ORCHESTRATOR_ENV" ]]; then
  worker_version="$(sed -n 's/^SILICIUM_APP_VERSION=//p' "$ORCHESTRATOR_ENV" | head -n 1)"
fi
export SILICIUM_DEV_MINIWORKERS_APP_VERSION="${worker_version:-dev}"
worker_build="${SILICIUM_DEV_MINIWORKERS_RELEASE_BUILD:-$(git -C "$ROOT_DIR/Network" rev-parse --short=12 HEAD 2>/dev/null || true)}"
export SILICIUM_DEV_MINIWORKERS_RELEASE_BUILD="${worker_build:-local}"
COUNT_IN_FILE="$(sed -n 's/^SILICIUM_DEV_MINIWORKERS=//p' "$ENV_FILE" | head -n 1)"
COUNT="${SILICIUM_DEV_MINIWORKERS:-${COUNT_IN_FILE:-20}}"
if [[ ! "$COUNT" =~ ^[0-9]+$ ]] || (( COUNT < 20 || COUNT > 24 )); then
  echo "SILICIUM_DEV_MINIWORKERS must be between 20 and 24." >&2
  exit 2
fi

SILICIUM_DEV_BOOTSTRAP_PEER="$(sed -n 's/^SILICIUM_DEV_BOOTSTRAP_PEER=//p' "$ENV_FILE" | head -n 1)"
BACKEND_NETWORK="${SILICIUM_DEV_BACKEND_NETWORK:-$(sed -n 's/^SILICIUM_DEV_BACKEND_NETWORK=//p' "$ENV_FILE" | head -n 1)}"
PAIRING_DIR="${SILICIUM_DEV_MINIWORKERS_PAIRING_DIR:-$(sed -n 's/^SILICIUM_DEV_MINIWORKERS_PAIRING_DIR=//p' "$ENV_FILE" | head -n 1)}"
PAIRING_DIR="${PAIRING_DIR:-${SILICIUM_DATA_ROOT:-/var/lib/silicium-dev}/miniworker-pairing}"
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

ensure_pairing_mounts() {
	local backend_identity backend_uid backend_gid
	backend_uid="${SILICIUM_BACKEND_UID:-}"
	backend_gid="${SILICIUM_BACKEND_GID:-}"
	if [[ -z "$backend_uid" || -z "$backend_gid" ]]; then
		backend_identity="$(sudo docker run --rm --entrypoint sh silicium-backend:latest -c 'printf "%s:%s" "$(id -u)" "$(id -g)"')"
		backend_uid="${backend_identity%%:*}"
		backend_gid="${backend_identity##*:}"
	fi
	if [[ ! "$backend_uid" =~ ^[0-9]+$ || ! "$backend_gid" =~ ^[0-9]+$ ]]; then
		echo "Could not resolve the backend's numeric UID/GID for secure miniworker pairing mounts." >&2
		return 2
	fi
	sudo install -d -o "$backend_uid" -g "$backend_gid" -m 0711 "$PAIRING_DIR"
	for ((index = 1; index <= 24; index += 1)); do
		local worker_id worker_gid
		worker_id="miniworker-$(printf '%02d' "$index")"
		worker_gid=$((20000 + index))
		sudo install -d -o "$backend_uid" -g "$worker_gid" -m 2750 "$PAIRING_DIR/$worker_id"
  done
}

read_pairing_codes() {
  local source="$1"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to validate the pairing file." >&2
    return 2
  fi
  python3 - "$source" "$COUNT" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone

path, count_text = sys.argv[1:]
count = int(count_text)
with open(path, "r", encoding="utf-8") as stream:
    payload = json.load(stream)
items = payload.get("items") if isinstance(payload, dict) else None
if not isinstance(items, list) or not 1 <= len(items) <= count:
    raise SystemExit("Pairing file must contain between 1 and the active worker count codes.")
seen = set()
for item in items:
    if not isinstance(item, dict):
        raise SystemExit("Invalid pairing entry.")
    node_id = item.get("nodeId", "")
    code = item.get("code", "")
    expires_at = item.get("expiresAt", "")
    match = re.fullmatch(r"miniworker-(\d{2})", node_id) if isinstance(node_id, str) else None
    if not match or not 1 <= int(match.group(1)) <= count:
        raise SystemExit("Pairing file contains a worker that is not active in this deployment.")
    if node_id in seen or not isinstance(code, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", code):
        raise SystemExit("Pairing file contains a duplicate worker or malformed code.")
    if not isinstance(expires_at, str) or not expires_at:
        raise SystemExit("Pairing file is missing code expiry information.")
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit("Pairing file has an invalid expiry timestamp.")
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise SystemExit("Pairing file has expired; generate fresh codes on the website.")
    seen.add(node_id)
    print(f"{node_id}\t{code}")
PY
}

pair_workers() {
  local pairing_file="$1"
  if [[ ! -f "$pairing_file" ]]; then
    echo "Pairing file not found: $pairing_file" >&2
    return 2
  fi
  if [[ -z "$BACKEND_NETWORK" ]]; then
    echo "SILICIUM_DEV_BACKEND_NETWORK is required." >&2
    return 2
  fi
  if ! sudo docker network inspect "$BACKEND_NETWORK" >/dev/null 2>&1; then
    echo "Docker network $BACKEND_NETWORK is missing. Start the dev website/backend first." >&2
    return 2
  fi
  local rows=()
  local code_rows
  if ! code_rows="$(read_pairing_codes "$pairing_file")"; then
    return 2
  fi
  mapfile -t rows <<< "$code_rows"
  unset code_rows
  if (( ${#rows[@]} == 0 )); then
    echo "No pairing codes were supplied." >&2
    return 2
  fi
  ensure_pairing_mounts
	local row node_id code path backend_identity backend_uid backend_gid worker_gid
	backend_identity="$(sudo docker run --rm --entrypoint sh silicium-backend:latest -c 'printf "%s:%s" "$(id -u)" "$(id -g)"')"
	backend_uid="${backend_identity%%:*}"
	backend_gid="${backend_identity##*:}"
  for row in "${rows[@]}"; do
    IFS=$'\t' read -r node_id code <<< "$row"
		worker_gid=$((20000 + 10#${node_id##*-}))
		path="$PAIRING_DIR/$node_id/device-pairing-code"
		printf '%s' "$code" | sudo tee "$path" >/dev/null
		sudo chown "$backend_uid:$worker_gid" "$path"
		sudo chmod 0640 "$path"
  done
  sudo "${compose[@]}" up -d --build --force-recreate "${active_services[@]}"
  local all_linked=0
  for attempt in $(seq 1 90); do
    all_linked=1
    for row in "${rows[@]}"; do
      IFS=$'\t' read -r node_id _ <<< "$row"
      if ! sudo docker exec "silicium-dev-$node_id" test -s /data/account-link-code.sha256 >/dev/null 2>&1; then
        all_linked=0
        break
      fi
    done
    if (( all_linked == 1 )); then break; fi
    sleep 1
  done
  if (( all_linked == 0 )); then
    echo "Some account links did not complete. Pairing codes remain protected for retry; inspect logs with: $0 logs" >&2
    return 1
  fi
  for row in "${rows[@]}"; do
    IFS=$'\t' read -r node_id _ <<< "$row"
		sudo rm -f "$PAIRING_DIR/$node_id/device-pairing-code"
  done
  echo "Linked ${#rows[@]} miniworkers to the signed-in account. Pairing codes cleared."
}

case "${1:-status}" in
  up)
    if [[ -n "$BACKEND_NETWORK" ]] && ! sudo docker network inspect "$BACKEND_NETWORK" >/dev/null 2>&1; then
      echo "Docker network $BACKEND_NETWORK is missing. Start the dev website/backend first." >&2
      exit 2
    fi
    ensure_pairing_mounts
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
    ensure_pairing_mounts
    sudo "${compose[@]}" rm --stop --force "${inactive_services[@]}" >/dev/null 2>&1 || true
    sudo "${compose[@]}" up -d --remove-orphans "${active_services[@]}"
    ;;
  pair)
    if [[ $# -ne 2 ]]; then
      echo "Usage: $0 pair <silicium-miniworker-pairing.json>" >&2
      exit 2
    fi
    pair_workers "$2"
    ;;
  *)
    echo "Usage: $0 {up|down|status|logs|scale|pair <pairing-json>}" >&2
    exit 2
    ;;
esac
