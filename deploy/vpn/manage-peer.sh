#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  manage-peer.sh [ROOT] add <name>
  manage-peer.sh [ROOT] revoke <name>
  manage-peer.sh [ROOT] rotate <name>
  manage-peer.sh [ROOT] list

The generated client configuration is root-only under /etc/wireguard.
Copy it securely to the client before removing any server-side copy.
USAGE
}

ROOT=/opt/silicium-dev
if [[ "${1:-}" =~ ^(add|revoke|rotate|list)$ ]]; then
  ACTION="$1"
  NAME="${2:-}"
else
  ROOT="${1:-$ROOT}"
  ACTION="${2:-}"
  NAME="${3:-}"
fi
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
CHANNEL_TOOL="$ROOT/deploy/release/channel.py"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/vpn/manage-peer.sh $ROOT ..." >&2
  exit 1
fi
[[ "$RELEASE_CHANNEL" == "dev" ]] || { echo "The Silicium VPN peer manager is restricted to the dev channel." >&2; exit 1; }
[[ -f "$CHANNEL_TOOL" ]] || { echo "Missing channel contract: $CHANNEL_TOOL" >&2; exit 1; }
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
channel_field() { python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field "$1"; }

VPN_INTERFACE="${SILICIUM_VPN_INTERFACE:-$(channel_field vpn_interface)}"
VPN_NETWORK="${SILICIUM_VPN_NETWORK:-$(channel_field vpn_network)}"
VPN_ENDPOINT="${SILICIUM_VPN_ENDPOINT:-$(channel_field vpn_endpoint)}"
WG_DIR=/etc/wireguard
CONFIG_FILE="$WG_DIR/${VPN_INTERFACE}.conf"
PEER_DIR="$WG_DIR/silicium-dev-peers"
REVOKED_DIR="$WG_DIR/silicium-dev-revoked"
LOCK_FILE="$WG_DIR/.silicium-dev.lock"

case "$ACTION" in
  list) ;;
  add|revoke|rotate)
    [[ "$NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$ ]] || { usage; exit 2; }
    ;;
  *) usage; exit 2 ;;
esac

[[ -s "$CONFIG_FILE" ]] || { echo "Missing WireGuard config: $CONFIG_FILE" >&2; exit 1; }
command -v wg >/dev/null || { echo "wireguard-tools is required." >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required." >&2; exit 1; }
install -d -m 0700 "$PEER_DIR" "$REVOKED_DIR"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  flock -x 9
fi

peer_file="$PEER_DIR/${NAME}.conf"
peer_value() {
  local key="$1"
  local file="$2"
  awk -F '=' -v wanted="$key" '
    $1 ~ "^[[:space:]]*" wanted "[[:space:]]*$" {
      value=$2
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      print value
      exit
    }
  ' "$file"
}

server_public_key_for_peer() {
  local peer_name="$1"
  awk -v marker="# silicium-peer: $peer_name" '
    $0 == marker { in_peer=1; next }
    in_peer && /^PublicKey[[:space:]]*=/ { print $3; exit }
    in_peer && /^# silicium-peer:/ { exit }
  ' "$CONFIG_FILE"
}

allocate_address() {
  local subnet_base candidate address
  subnet_base="$(python3 - "$VPN_NETWORK" <<'PY'
from ipaddress import IPv4Network
import sys
print(str(IPv4Network(sys.argv[1], strict=True).network_address).rsplit('.', 1)[0])
PY
)"
  for candidate in $(seq 10 254); do
    address="${subnet_base}.${candidate}"
    if ! grep -RhsE "^[[:space:]]*Address[[:space:]]*=[[:space:]]*${address}/32([[:space:]]|$)" "$PEER_DIR"/*.conf 2>/dev/null; then
      printf '%s\n' "$address"
      return 0
    fi
  done
  echo "No free WireGuard client address remains in $VPN_NETWORK." >&2
  return 1
}

add_peer() {
  [[ ! -e "$peer_file" ]] || { echo "Peer already exists: $NAME" >&2; exit 1; }
  local server_public_key client_private_key client_public_key client_address endpoint
  local client_tmp server_tmp backup
  server_public_key="$(wg show "$VPN_INTERFACE" public-key)"
  client_private_key="$(wg genkey | tr -d '\r\n')"
  client_public_key="$(printf '%s' "$client_private_key" | wg pubkey)"
  client_address="$(allocate_address)"
  endpoint="${SILICIUM_VPN_ENDPOINT:-$VPN_ENDPOINT}"
  client_tmp="$(mktemp "$PEER_DIR/.${NAME}.client.XXXXXX")"
  server_tmp="$(mktemp "$WG_DIR/.${VPN_INTERFACE}.conf.XXXXXX")"
  backup="$(mktemp "$WG_DIR/.${VPN_INTERFACE}.backup.XXXXXX")"
  trap 'rm -f "$client_tmp" "$server_tmp" "$backup"' EXIT
  cp -p "$CONFIG_FILE" "$backup"
  cp "$CONFIG_FILE" "$server_tmp"
  printf '\n# silicium-peer: %s\n[Peer]\nPublicKey = %s\nAllowedIPs = %s/32\n' "$NAME" "$client_public_key" "$client_address" >> "$server_tmp"
  chmod 0600 "$server_tmp"
  cat > "$client_tmp" <<EOF
[Interface]
PrivateKey = $client_private_key
Address = $client_address/32

[Peer]
PublicKey = $server_public_key
Endpoint = $endpoint
AllowedIPs = $VPN_NETWORK
PersistentKeepalive = 25
EOF
  chmod 0600 "$client_tmp"

  wg set "$VPN_INTERFACE" peer "$client_public_key" allowed-ips "$client_address/32"
  if ! install -o root -g root -m 0600 "$server_tmp" "$CONFIG_FILE"; then
    wg set "$VPN_INTERFACE" peer "$client_public_key" remove || true
    exit 1
  fi
  if ! install -o root -g root -m 0600 "$client_tmp" "$peer_file"; then
    install -o root -g root -m 0600 "$backup" "$CONFIG_FILE"
    wg set "$VPN_INTERFACE" peer "$client_public_key" remove || true
    exit 1
  fi
  trap - EXIT
  rm -f "$client_tmp" "$server_tmp" "$backup"
  echo "Peer $NAME created."
  echo "  client configuration: $peer_file"
  echo "  address: $client_address"
  echo "  public key: $client_public_key"
}

revoke_peer() {
  [[ -s "$peer_file" ]] || { echo "Unknown peer: $NAME" >&2; exit 1; }
  local client_public_key client_address server_tmp backup stamp revoked_record
  client_public_key="$(server_public_key_for_peer "$NAME")"
  client_address="$(peer_value Address "$peer_file" | cut -d/ -f1)"
  [[ -n "$client_public_key" && -n "$client_address" ]] || { echo "Peer metadata is incomplete: $peer_file" >&2; exit 1; }
  server_tmp="$(mktemp "$WG_DIR/.${VPN_INTERFACE}.conf.XXXXXX")"
  backup="$(mktemp "$WG_DIR/.${VPN_INTERFACE}.backup.XXXXXX")"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  revoked_record="$REVOKED_DIR/${NAME}-${stamp}.txt"
  trap 'rm -f "$server_tmp" "$backup"' EXIT
  cp -p "$CONFIG_FILE" "$backup"
  awk -v marker="# silicium-peer: $NAME" '
    $0 == marker { in_peer=1; next }
    in_peer && /^# silicium-peer:/ { in_peer=0 }
    !in_peer { print }
  ' "$CONFIG_FILE" > "$server_tmp"
  chmod 0600 "$server_tmp"
  wg set "$VPN_INTERFACE" peer "$client_public_key" remove
  if ! install -o root -g root -m 0600 "$server_tmp" "$CONFIG_FILE"; then
    install -o root -g root -m 0600 "$backup" "$CONFIG_FILE"
    wg set "$VPN_INTERFACE" peer "$client_public_key" allowed-ips "$client_address/32" || true
    exit 1
  fi
  printf 'name=%s\npublic_key=%s\naddress=%s\nrevoked_at=%s\n' "$NAME" "$client_public_key" "$client_address" "$stamp" > "$revoked_record"
  chmod 0600 "$revoked_record"
  rm -f "$peer_file"
  trap - EXIT
  rm -f "$server_tmp" "$backup"
  echo "Peer $NAME revoked; the server-side client configuration was removed."
}

list_peers() {
  shopt -s nullglob
  local file peer public address active
  local files=("$PEER_DIR"/*.conf)
  if [[ "${#files[@]}" -eq 0 ]]; then
    echo "No Silicium dev peers are configured."
    return 0
  fi
  printf 'NAME\tADDRESS\tSTATUS\tPUBLIC_KEY\n'
  for file in "${files[@]}"; do
    peer="${file##*/}"
    peer="${peer%.conf}"
    address="$(peer_value Address "$file")"
    public="$(server_public_key_for_peer "$peer")"
    active=inactive
    if wg show "$VPN_INTERFACE" peers | grep -Fxq "$public"; then
      active=active
    fi
    printf '%s\t%s\t%s\t%s\n' "$peer" "$address" "$active" "$public"
  done
}

case "$ACTION" in
  add) add_peer ;;
  revoke) revoke_peer ;;
  rotate) revoke_peer; add_peer ;;
  list) list_peers ;;
esac
