"""`node start --world`: one-command wide-area mesh defaults.

Binds public interfaces, advertises the guessed public host, derives the mesh
key from the world name, merges the world discovery seeds and enables the
mesh features. The underlying helpers are shared with the Python node in
`tools/node_defaults.py`.
"""

from __future__ import annotations

import argparse
import os

from tools.cli.constants import LOCAL_STATE_DIR
from tools.node_defaults import (
    WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S,
    WORLD_DEFAULT_GOSSIP_PORT,
    WORLD_DEFAULT_PEER_HTTP_PORT,
    WORLD_DEFAULT_PEER_SYNC_INTERVAL_S,
)
from tools.node_defaults import derive_world_mesh_key as _derive_world_mesh_key
from tools.node_defaults import guess_world_advertise_host as _guess_world_advertise_host
from tools.node_defaults import merge_csv as _merge_csv


def _apply_world_mode_defaults(args: argparse.Namespace, *, node_id: str) -> argparse.Namespace:
    """Fill the wide-area mesh defaults when `--world` is set (no-op otherwise).

    Explicit values win: only empty, loopback or zero settings are replaced.
    The mesh roles (gossip, relay, remote dispatch, NAT punch, on-chain
    reputation) are always switched on, and sync intervals are raised to at
    least the world minimums.
    """
    if not bool(getattr(args, "world", False)):
        return args
    advertise_host = _guess_world_advertise_host()
    if not str(getattr(args, "gossip_bind", "") or "").strip() or str(args.gossip_bind).strip() == "127.0.0.1":
        args.gossip_bind = "0.0.0.0"
    if not str(getattr(args, "peer_http_bind", "") or "").strip() or str(args.peer_http_bind).strip() == "127.0.0.1":
        args.peer_http_bind = "0.0.0.0"
    if int(getattr(args, "gossip_port", 0) or 0) <= 0:
        args.gossip_port = WORLD_DEFAULT_GOSSIP_PORT
    if int(getattr(args, "peer_http_port", 0) or 0) <= 0:
        args.peer_http_port = WORLD_DEFAULT_PEER_HTTP_PORT
    if not str(getattr(args, "peer_advertise_host", "") or "").strip():
        args.peer_advertise_host = advertise_host
    if not str(getattr(args, "gossip_advertise_host", "") or "").strip():
        args.gossip_advertise_host = advertise_host
    if int(getattr(args, "peer_advertise_port", 0) or 0) <= 0:
        args.peer_advertise_port = int(args.peer_http_port)
    if int(getattr(args, "gossip_advertise_port", 0) or 0) <= 0:
        args.gossip_advertise_port = int(args.gossip_port)
    if not str(getattr(args, "mesh_key", "") or "").strip():
        args.mesh_key = _derive_world_mesh_key(str(getattr(args, "world_name", "")))
    args.discovery_seeds = _merge_csv(
        str(getattr(args, "discovery_seeds", "") or ""),
        str(getattr(args, "world_seeds", "") or ""),
        os.environ.get("SILICIUM_WORLD_SEEDS", ""),
    )
    args.gossip_enable = True
    args.relay_enable = True
    args.remote_dispatch_enable = True
    args.nat_punch_enable = True
    args.solana_reputation_enable = True
    args.peer_sync_interval_s = max(int(getattr(args, "peer_sync_interval_s", 0) or 0), WORLD_DEFAULT_PEER_SYNC_INTERVAL_S)
    args.discovery_sync_interval_s = max(
        int(getattr(args, "discovery_sync_interval_s", 0) or 0),
        WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S,
    )
    if not str(getattr(args, "identity_key_path", "") or "").strip():
        safe_node_id = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(node_id)) or "node"
        args.identity_key_path = (LOCAL_STATE_DIR / "world-identities" / safe_node_id / "ed25519.pem").as_posix()
    return args
