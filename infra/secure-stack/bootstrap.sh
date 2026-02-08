#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="docker compose -f ${STACK_DIR}/docker-compose.yaml"

ROOT="$(cd "${STACK_DIR}/../.." && pwd)"
# shellcheck source=infra/bin/i18n.sh
. "$ROOT/infra/bin/i18n.sh"

sil_i18n_echo "infra.secure.check_wireguard"
if ! lsmod | grep -q "^wireguard"; then
  if command -v modprobe >/dev/null 2>&1; then
    uid="${EUID:-$(id -u)}"
    if [[ "$uid" -eq 0 ]]; then
      modprobe wireguard
    elif command -v sudo >/dev/null 2>&1; then
      sudo modprobe wireguard
    else
      sil_i18n_echo "infra.secure.warn_no_sudo" >&2
    fi
  else
    sil_i18n_echo "infra.secure.warn_no_modprobe" >&2
  fi
fi

sil_i18n_echo "infra.secure.pull_images"
${COMPOSE} pull

sil_i18n_echo "infra.secure.start_stack"
${COMPOSE} up -d

sil_i18n_echo "infra.secure.active_services"
${COMPOSE} ps

echo
sil_i18n_echo "infra.secure.peer_files"
find "${STACK_DIR}/wireguard/config" -maxdepth 1 -type d -name "peer-*" -print | while read -r dir; do
  conf="${dir}/peer.conf"
  [[ -f "$conf" ]] && echo "  - ${conf}"
done

sil_i18n_echo "infra.secure.notes"
