"""Defaults shared by the network node (`tools/network_node.py`) and the CLI
(`silicium node start`): world-mesh mode, peer synchronisation, NAT traversal.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import socket

WORLD_DEFAULT_GOSSIP_PORT = 46000
WORLD_DEFAULT_PEER_HTTP_PORT = 46001
WORLD_DEFAULT_PEER_SYNC_INTERVAL_S = 10
WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S = 15
DEFAULT_PEER_SYNC_INTERVAL_S = 5
DEFAULT_PEER_STALE_AFTER_S = 15
DEFAULT_PUBLIC_STUN_SERVER = "stun.l.google.com:19302"


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def merge_csv(*values: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in split_csv(value):
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return ",".join(merged)


def guess_world_advertise_host() -> str:
    for env_name in ("SILICIUM_WORLD_ADVERTISE_HOST", "TAILSCALE_IP", "TS_IP"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate:
            return candidate
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if family != socket.AF_INET:
                continue
            host = str(sockaddr[0]).strip()
            if host and not host.startswith("127."):
                return host
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            host = str(sock.getsockname()[0]).strip()
            if host and not host.startswith("127."):
                return host
    except OSError:
        pass
    return "127.0.0.1"


def derive_world_mesh_key(world_name: str) -> str:
    normalized = str(world_name or "").strip().lower()
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"world:{normalized}:{digest}"


def apply_nat_traversal_defaults(args: argparse.Namespace) -> argparse.Namespace:
    backend = str(getattr(args, "p2p_direct_transport_backend", "auto") or "auto").strip().lower()
    stun_server = str(getattr(args, "p2p_stun_server", "") or "").strip()
    if bool(getattr(args, "nat_punch_enable", False)) and backend not in {"native", "native-light", "native_light"} and not stun_server:
        args.p2p_stun_server = DEFAULT_PUBLIC_STUN_SERVER
    return args
