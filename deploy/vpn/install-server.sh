#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium-dev}"
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-dev}"
CHANNEL_TOOL="$ROOT/deploy/release/channel.py"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/vpn/install-server.sh $ROOT" >&2
  exit 1
fi
[[ "$RELEASE_CHANNEL" == "dev" ]] || { echo "The Silicium VPN bootstrap is restricted to the dev channel." >&2; exit 1; }
[[ -f "$CHANNEL_TOOL" ]] || { echo "Missing channel contract: $CHANNEL_TOOL" >&2; exit 1; }
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
channel_field() { python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field "$1"; }

VPN_INTERFACE="${SILICIUM_VPN_INTERFACE:-$(channel_field vpn_interface)}"
VPN_NETWORK="${SILICIUM_VPN_NETWORK:-$(channel_field vpn_network)}"
VPN_SERVER_ADDRESS="${SILICIUM_VPN_SERVER_ADDRESS:-$(channel_field vpn_server_address)}"
VPN_LISTEN_PORT="${SILICIUM_VPN_LISTEN_PORT:-$(channel_field vpn_listen_port)}"
VPN_ENDPOINT="${SILICIUM_VPN_ENDPOINT:-$(channel_field vpn_endpoint)}"
VPN_PROXY_BIND_ADDRESS="${SILICIUM_VPN_PROXY_BIND_ADDRESS:-$(channel_field vpn_proxy_bind_address)}"
VPN_PROXY_HTTP_PORT="${SILICIUM_VPN_PROXY_HTTP_PORT:-$(channel_field proxy_http_port)}"
VPN_PROXY_HTTPS_PORT="${SILICIUM_VPN_PROXY_HTTPS_PORT:-$(channel_field proxy_https_port)}"
VPN_ORCHESTRATOR_PORT="${SILICIUM_VPN_ORCHESTRATOR_PORT:-$(channel_field orchestrator_port)}"
VPN_BACKEND_P2P_PORT="${SILICIUM_VPN_BACKEND_P2P_PORT:-$(channel_field backend_p2p_port)}"
VPN_TURN_PORT="${SILICIUM_VPN_TURN_PORT:-$(channel_field turn_port)}"
VPN_TURN_TLS_PORT="${SILICIUM_VPN_TURN_TLS_PORT:-$(channel_field turn_tls_port)}"
VPN_TURN_RELAY_MIN_PORT="${SILICIUM_VPN_TURN_RELAY_MIN_PORT:-$(channel_field turn_relay_min_port)}"
VPN_TURN_RELAY_MAX_PORT="${SILICIUM_VPN_TURN_RELAY_MAX_PORT:-$(channel_field turn_relay_max_port)}"

[[ "$VPN_INTERFACE" =~ ^[A-Za-z0-9_.-]{1,15}$ ]] || { echo "Invalid WireGuard interface name: $VPN_INTERFACE" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required." >&2; exit 1; }
command -v ip >/dev/null || { echo "iproute2 (ip) is required." >&2; exit 1; }

python3 - "$VPN_NETWORK" "$VPN_SERVER_ADDRESS" "$VPN_LISTEN_PORT" "$VPN_PROXY_BIND_ADDRESS" <<'PY'
from ipaddress import IPv4Address, IPv4Network
import sys

network = IPv4Network(sys.argv[1], strict=True)
server = IPv4Address(sys.argv[2])
if server not in network:
    raise SystemExit("VPN server address is outside the VPN network")
port = int(sys.argv[3])
if not 1 <= port <= 65535:
    raise SystemExit("VPN listen port is outside the valid range")
if sys.argv[4] != str(server):
    raise SystemExit("VPN proxy bind address must equal the VPN server address")
PY

if ! command -v wg >/dev/null || ! command -v wg-quick >/dev/null; then
  command -v apt-get >/dev/null || { echo "wireguard-tools is missing and this host has no apt-get." >&2; exit 1; }
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends wireguard-tools
fi
command -v wg >/dev/null || { echo "wireguard-tools installation failed." >&2; exit 1; }
command -v wg-quick >/dev/null || { echo "wg-quick is unavailable." >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required for the managed VPN service." >&2; exit 1; }

WG_DIR=/etc/wireguard
CONFIG_FILE="$WG_DIR/${VPN_INTERFACE}.conf"
SERVER_KEY_FILE="$WG_DIR/${VPN_INTERFACE}-server.key"
MANAGED_MARKER="# Managed by Silicium dev VPN"
install -d -m 0700 "$WG_DIR"

if [[ -e "$CONFIG_FILE" ]] && ! grep -Fqx "$MANAGED_MARKER" "$CONFIG_FILE"; then
  echo "Refusing to overwrite unmanaged WireGuard configuration: $CONFIG_FILE" >&2
  exit 1
fi
if ip link show "$VPN_INTERFACE" >/dev/null 2>&1 && [[ ! -s "$CONFIG_FILE" ]]; then
  echo "Refusing to claim existing unmanaged WireGuard interface: $VPN_INTERFACE" >&2
  exit 1
fi

if [[ ! -s "$CONFIG_FILE" ]]; then
  umask 077
  wg genkey > "$SERVER_KEY_FILE"
  chmod 0600 "$SERVER_KEY_FILE"
  server_private_key="$(tr -d '\r\n' < "$SERVER_KEY_FILE")"
  config_tmp="$(mktemp "$WG_DIR/.${VPN_INTERFACE}.conf.XXXXXX")"
  trap 'rm -f "$config_tmp"' EXIT
  {
    printf '%s\n' "$MANAGED_MARKER"
    printf '[Interface]\n'
    printf 'Address = %s/24\n' "$VPN_SERVER_ADDRESS"
    printf 'ListenPort = %s\n' "$VPN_LISTEN_PORT"
    printf 'PrivateKey = %s\n' "$server_private_key"
    printf '\n'
  } > "$config_tmp"
  install -o root -g root -m 0600 "$config_tmp" "$CONFIG_FILE"
  rm -f "$config_tmp"
  trap - EXIT
else
  grep -Eq "^Address[[:space:]]*=[[:space:]]*${VPN_SERVER_ADDRESS}/" "$CONFIG_FILE" || { echo "Managed WireGuard config has an unexpected server address: $CONFIG_FILE" >&2; exit 1; }
  grep -Eq "^ListenPort[[:space:]]*=[[:space:]]*${VPN_LISTEN_PORT}[[:space:]]*$" "$CONFIG_FILE" || { echo "Managed WireGuard config has an unexpected listen port: $CONFIG_FILE" >&2; exit 1; }
fi
chmod 0600 "$CONFIG_FILE"

wg-quick strip "$CONFIG_FILE" >/dev/null
systemctl enable --now "wg-quick@${VPN_INTERFACE}.service"
if ! ip -4 addr show dev "$VPN_INTERFACE" | grep -Eq "inet[[:space:]]+${VPN_SERVER_ADDRESS}/"; then
  echo "WireGuard interface $VPN_INTERFACE is missing $VPN_SERVER_ADDRESS." >&2
  systemctl status --no-pager -l "wg-quick@${VPN_INTERFACE}.service" >&2 || true
  exit 1
fi

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  ufw allow "${VPN_LISTEN_PORT}/udp" comment "Silicium dev WireGuard" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_PROXY_HTTP_PORT" proto tcp comment "Silicium dev VPN HTTP ingress" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_PROXY_HTTPS_PORT" proto tcp comment "Silicium dev VPN HTTPS ingress" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_ORCHESTRATOR_PORT" proto tcp comment "Silicium dev VPN orchestrator HTTP" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_ORCHESTRATOR_PORT" proto udp comment "Silicium dev VPN orchestrator gossip" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_BACKEND_P2P_PORT" proto tcp comment "Silicium dev VPN backend P2P TCP" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_BACKEND_P2P_PORT" proto udp comment "Silicium dev VPN backend P2P UDP" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_TURN_PORT" proto tcp comment "Silicium dev VPN TURN TCP" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_TURN_PORT" proto udp comment "Silicium dev VPN TURN UDP" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_TURN_TLS_PORT" proto tcp comment "Silicium dev VPN TURN TLS" >/dev/null
  ufw allow from "$VPN_NETWORK" to "$VPN_SERVER_ADDRESS" port "$VPN_TURN_RELAY_MIN_PORT:$VPN_TURN_RELAY_MAX_PORT" proto udp comment "Silicium dev VPN TURN relay" >/dev/null
fi

server_public_key="$(wg show "$VPN_INTERFACE" public-key)"
echo "Silicium dev WireGuard is active."
echo "  interface: $VPN_INTERFACE"
echo "  server address: $VPN_SERVER_ADDRESS"
echo "  network: $VPN_NETWORK"
echo "  endpoint: $VPN_ENDPOINT"
echo "  server public key: $server_public_key"
echo "  peer manager: $ROOT/deploy/vpn/manage-peer.sh"
