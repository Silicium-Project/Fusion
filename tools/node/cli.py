"""Command line entry point: argument parser, role parsing and node bootstrap."""

from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path
from typing import Any

from tools.node.config import NodeConfig
from tools.node.constants import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_PEER_HTTP_MAX_WORKERS,
    DEFAULT_PEER_SYNC_FANOUT,
    NETWORK_ROLES,
    TOOLS_DIR,
)
from tools.node.daemon import NetworkNode
from tools.node.util import safe_id, safe_path_id
from tools.node_defaults import (
    DEFAULT_PEER_STALE_AFTER_S,
    DEFAULT_PEER_SYNC_INTERVAL_S,
    WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S,
    WORLD_DEFAULT_GOSSIP_PORT,
    WORLD_DEFAULT_PEER_HTTP_PORT,
    WORLD_DEFAULT_PEER_SYNC_INTERVAL_S,
    apply_nat_traversal_defaults,
    derive_world_mesh_key,
    guess_world_advertise_host,
    merge_csv,
)


def parse_roles(raw: str) -> set[str]:
    """Parse a comma-separated role list (all roles when empty); reject unknown roles."""
    roles = {item.strip().lower() for item in raw.split(",") if item.strip()}
    if not roles:
        roles = {"compute", "verify", "storage", "audit", "resource"}
    invalid = roles - NETWORK_ROLES
    if invalid:
        raise ValueError("unsupported roles: " + ",".join(sorted(invalid)))
    return roles


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser; defaults come from SILICIUM_* environment variables."""
    parser = argparse.ArgumentParser(prog="network_node")
    # Option order is the --help order; keep these groups in this sequence.
    _add_node_arguments(parser)
    _add_solana_arguments(parser)
    _add_mesh_arguments(parser)
    _add_nat_traversal_arguments(parser)
    _add_scheduler_arguments(parser)
    return parser


def _add_node_arguments(parser: argparse.ArgumentParser) -> None:
    """Identity, roles, release, loop and storage options."""
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--world", action="store_true", default=os.environ.get("SILICIUM_WORLD_MODE", "0") == "1")
    parser.add_argument("--world-name", default=os.environ.get("SILICIUM_WORLD_NAME", ""))
    parser.add_argument("--world-seeds", default=os.environ.get("SILICIUM_WORLD_SEEDS", ""))
    parser.add_argument("--roles", default=os.environ.get("SILICIUM_NODE_ROLES", "compute,verify,storage,audit,resource"))
    parser.add_argument("--node-id", default=os.environ.get("SILICIUM_NODE_ID", "node-" + uuid.uuid4().hex[:8]))
    parser.add_argument("--app-version", default=os.environ.get("SILICIUM_APP_VERSION", "unknown"))
    parser.add_argument("--release-channel", default=os.environ.get("SILICIUM_RELEASE_CHANNEL", "dev"), choices=["dev", "prod"])
    parser.add_argument("--release-build", default=os.environ.get("SILICIUM_RELEASE_BUILD", ""))
    parser.add_argument("--idle-ms", type=int, default=int(os.environ.get("SILICIUM_NODE_IDLE_MS", "250")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-items", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_ITEMS", "0")))
    parser.add_argument("--p2p-gateway", default=os.environ.get("SILICIUM_P2P_GATEWAY", "http://127.0.0.1:5001"))
    parser.add_argument("--state-dir", default="")


def _add_solana_arguments(parser: argparse.ArgumentParser) -> None:
    """Solana bridge, retries and worker bootstrap options."""
    parser.add_argument("--solana-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_ENABLE", "0") == "1")
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument(
        "--solana-program-id",
        default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"),
    )
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.path.expanduser("~/.config/solana/id.json")))
    parser.add_argument("--solana-bridge", default=os.environ.get("SILICIUM_SOLANA_BRIDGE", str(TOOLS_DIR / "solana_layer_bridge.cjs")))
    parser.add_argument("--solana-timeout-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_TIMEOUT_S", "45")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_RETRIES", "2")))
    parser.add_argument("--bootstrap-worker", action="store_true", default=os.environ.get("SILICIUM_BOOTSTRAP_WORKER", "0") == "1")


def _add_mesh_arguments(parser: argparse.ArgumentParser) -> None:
    """Gossip, peer HTTP, sync, relay, identity, replication, dispatch and pull options."""
    parser.add_argument("--gossip-enable", action="store_true", default=os.environ.get("SILICIUM_GOSSIP_ENABLE", "0") == "1")
    parser.add_argument("--gossip-bind", default=os.environ.get("SILICIUM_GOSSIP_BIND", "127.0.0.1"))
    parser.add_argument("--gossip-port", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_PORT", "0")))
    parser.add_argument("--peer-http-bind", default=os.environ.get("SILICIUM_PEER_HTTP_BIND", "127.0.0.1"))
    parser.add_argument("--peer-http-port", type=int, default=int(os.environ.get("SILICIUM_PEER_HTTP_PORT", "0")))
    parser.add_argument(
        "--peer-http-max-workers",
        type=int,
        default=int(os.environ.get("SILICIUM_PEER_HTTP_MAX_WORKERS", str(DEFAULT_PEER_HTTP_MAX_WORKERS))),
        help="Maximum concurrent peer HTTP requests (default: 16).",
    )
    parser.add_argument("--peer-advertise-url", default=os.environ.get("SILICIUM_PEER_ADVERTISE_URL", ""))
    parser.add_argument("--peer-advertise-host", default=os.environ.get("SILICIUM_PEER_ADVERTISE_HOST", ""))
    parser.add_argument("--peer-advertise-port", type=int, default=int(os.environ.get("SILICIUM_PEER_ADVERTISE_PORT", "0")))
    parser.add_argument("--gossip-advertise-host", default=os.environ.get("SILICIUM_GOSSIP_ADVERTISE_HOST", ""))
    parser.add_argument("--gossip-advertise-port", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_ADVERTISE_PORT", "0")))
    parser.add_argument("--seed-peers", default=os.environ.get("SILICIUM_SEED_PEERS", ""))
    parser.add_argument("--mesh-key", default=os.environ.get("SILICIUM_MESH_KEY", ""))
    parser.add_argument("--peer-sync-interval-s", type=int, default=int(os.environ.get("SILICIUM_PEER_SYNC_INTERVAL_S", str(DEFAULT_PEER_SYNC_INTERVAL_S))))
    parser.add_argument(
        "--peer-sync-fanout",
        type=int,
        default=int(os.environ.get("SILICIUM_PEER_SYNC_FANOUT", str(DEFAULT_PEER_SYNC_FANOUT))),
        help="Additional peer HTTP anti-entropy targets per sync (0 means unlimited; default: 8).",
    )
    parser.add_argument("--peer-event-limit", type=int, default=int(os.environ.get("SILICIUM_PEER_EVENT_LIMIT", "128")))
    parser.add_argument("--gossip-max-hops", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_MAX_HOPS", "8")))
    parser.add_argument("--peer-stale-after-s", type=int, default=int(os.environ.get("SILICIUM_PEER_STALE_AFTER_S", str(DEFAULT_PEER_STALE_AFTER_S))))
    parser.add_argument("--relay-enable", action="store_true", default=os.environ.get("SILICIUM_RELAY_ENABLE", "0") == "1")
    parser.add_argument("--relay-hops", type=int, default=int(os.environ.get("SILICIUM_RELAY_HOPS", "2")))
    parser.add_argument("--identity-key-path", default=os.environ.get("SILICIUM_IDENTITY_KEY_PATH", ""))
    parser.add_argument(
        "--identity-dev-mesh-auth",
        action="store_true",
        default=os.environ.get("SILICIUM_IDENTITY_DEV_MESH_AUTH", "0") == "1",
        help="Allow bearer-only mesh-key HTTP auth for local development. Production peers must use signed identity headers.",
    )
    parser.add_argument("--reputation-score", type=float, default=float(os.environ.get("SILICIUM_REPUTATION_SCORE", "0")))
    parser.add_argument("--replication-factor", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_FACTOR", "0")))
    parser.add_argument("--replication-quorum", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_QUORUM", "0")))
    parser.add_argument("--discovery-seeds", default=os.environ.get("SILICIUM_DISCOVERY_SEEDS", ""))
    parser.add_argument("--discovery-sync-interval-s", type=int, default=int(os.environ.get("SILICIUM_DISCOVERY_SYNC_INTERVAL_S", "30")))
    parser.add_argument("--remote-dispatch-enable", action="store_true", default=os.environ.get("SILICIUM_REMOTE_DISPATCH_ENABLE", "0") == "1")
    parser.add_argument("--remote-dispatch-limit", type=int, default=int(os.environ.get("SILICIUM_REMOTE_DISPATCH_LIMIT", "3")))
    parser.add_argument("--pull-tasks-enable", action="store_true", default=os.environ.get("SILICIUM_PULL_TASKS_ENABLE", "0") == "1")
    parser.add_argument("--pull-tasks-interval-s", type=float, default=float(os.environ.get("SILICIUM_PULL_TASKS_INTERVAL_S", "0.25")))
    parser.add_argument("--pull-tasks-batch-size", type=int, default=int(os.environ.get("SILICIUM_PULL_TASKS_BATCH_SIZE", "1")))


def _add_nat_traversal_arguments(parser: argparse.ArgumentParser) -> None:
    """NAT punching, candidate/session timers and STUN/TURN options."""
    parser.add_argument("--nat-punch-enable", action="store_true", default=os.environ.get("SILICIUM_NAT_PUNCH_ENABLE", "0") == "1")
    parser.add_argument("--p2p-candidate-ttl-s", type=int, default=int(os.environ.get("SILICIUM_P2P_CANDIDATE_TTL_S", "60")))
    parser.add_argument("--p2p-candidate-refresh-s", type=int, default=int(os.environ.get("SILICIUM_P2P_CANDIDATE_REFRESH_S", "20")))
    parser.add_argument("--p2p-session-ttl-s", type=int, default=int(os.environ.get("SILICIUM_P2P_SESSION_TTL_S", "120")))
    parser.add_argument("--p2p-punch-retry-count", type=int, default=int(os.environ.get("SILICIUM_P2P_PUNCH_RETRY_COUNT", "8")))
    parser.add_argument("--p2p-punch-interval-ms", type=int, default=int(os.environ.get("SILICIUM_P2P_PUNCH_INTERVAL_MS", "120")))
    parser.add_argument("--p2p-session-timeout-ms", type=int, default=int(os.environ.get("SILICIUM_P2P_SESSION_TIMEOUT_MS", "2500")))
    parser.add_argument("--p2p-direct-transport-backend", default=os.environ.get("SILICIUM_P2P_DIRECT_TRANSPORT_BACKEND", "auto"))
    parser.add_argument("--p2p-stun-server", default=os.environ.get("SILICIUM_P2P_STUN_SERVER", ""))
    parser.add_argument("--p2p-turn-server", default=os.environ.get("SILICIUM_P2P_TURN_SERVER", ""))
    parser.add_argument("--p2p-turn-username", default=os.environ.get("SILICIUM_P2P_TURN_USERNAME", "silicium"))
    parser.add_argument("--p2p-turn-password", default=os.environ.get("SILICIUM_P2P_TURN_PASSWORD", os.environ.get("SILICIUM_MESH_KEY", "")))
    parser.add_argument("--p2p-turn-transport", default=os.environ.get("SILICIUM_P2P_TURN_TRANSPORT", "udp"), choices=["udp", "tcp"])


def _add_scheduler_arguments(parser: argparse.ArgumentParser) -> None:
    """On-chain reputation refresh and peer scoring weights."""
    parser.add_argument("--solana-reputation-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_REPUTATION_ENABLE", "0") == "1")
    parser.add_argument("--solana-reputation-refresh-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_REPUTATION_REFRESH_S", "60")))
    parser.add_argument("--scheduler-onchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_ONCHAIN_WEIGHT", "10")))
    parser.add_argument("--scheduler-offchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_OFFCHAIN_WEIGHT", "1")))
    parser.add_argument("--scheduler-capacity-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_CAPACITY_WEIGHT", "0.01")))


def _apply_world_defaults(args: argparse.Namespace) -> None:
    """--world: public binds/ports, derived mesh key and every mesh feature on."""
    advertise_host = guess_world_advertise_host()
    if not str(args.gossip_bind).strip() or str(args.gossip_bind).strip() == "127.0.0.1":
        args.gossip_bind = "0.0.0.0"
    if not str(args.peer_http_bind).strip() or str(args.peer_http_bind).strip() == "127.0.0.1":
        args.peer_http_bind = "0.0.0.0"
    if int(args.gossip_port or 0) <= 0:
        args.gossip_port = WORLD_DEFAULT_GOSSIP_PORT
    if int(args.peer_http_port or 0) <= 0:
        args.peer_http_port = WORLD_DEFAULT_PEER_HTTP_PORT
    if not str(args.peer_advertise_host).strip():
        args.peer_advertise_host = advertise_host
    if not str(args.gossip_advertise_host).strip():
        args.gossip_advertise_host = advertise_host
    if int(args.peer_advertise_port or 0) <= 0:
        args.peer_advertise_port = int(args.peer_http_port)
    if int(args.gossip_advertise_port or 0) <= 0:
        args.gossip_advertise_port = int(args.gossip_port)
    if not str(args.mesh_key).strip():
        args.mesh_key = derive_world_mesh_key(str(args.world_name))
    args.discovery_seeds = merge_csv(str(args.discovery_seeds), str(args.world_seeds), os.environ.get("SILICIUM_WORLD_SEEDS", ""))
    args.gossip_enable = True
    args.relay_enable = True
    args.remote_dispatch_enable = True
    args.nat_punch_enable = True
    args.solana_reputation_enable = True
    args.peer_sync_interval_s = max(int(args.peer_sync_interval_s or 0), WORLD_DEFAULT_PEER_SYNC_INTERVAL_S)
    args.discovery_sync_interval_s = max(int(args.discovery_sync_interval_s or 0), WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S)
    if not str(args.identity_key_path).strip():
        args.identity_key_path = (Path(".silicium") / "world-identities" / safe_id(str(args.node_id)) / "ed25519.pem").as_posix()


def _node_and_solana_options(args: argparse.Namespace) -> dict[str, Any]:
    """NodeConfig fields: roles, identity, loop, Solana, gossip/HTTP binds."""
    return dict(
        roles=parse_roles(args.roles),
        node_id=safe_id(args.node_id),
        idle_ms=int(args.idle_ms),
        once=bool(args.once),
        max_items=int(args.max_items),
        p2p_gateway=str(args.p2p_gateway),
        solana_enable=bool(args.solana_enable),
        solana_rpc=str(args.solana_rpc),
        solana_program_id=str(args.solana_program_id),
        solana_wallet=str(args.solana_wallet),
        solana_bridge=Path(args.solana_bridge).expanduser().resolve(),
        solana_timeout_s=int(args.solana_timeout_s),
        max_retries=max(0, int(args.max_retries)),
        bootstrap_worker=bool(args.bootstrap_worker),
        gossip_enable=bool(args.gossip_enable),
        gossip_bind=str(args.gossip_bind),
        gossip_port=int(args.gossip_port),
        peer_http_bind=str(args.peer_http_bind),
        peer_http_port=int(args.peer_http_port),
    )


def _mesh_options(args: argparse.Namespace) -> dict[str, Any]:
    """NodeConfig fields: advertising, sync, relay, identity, replication, dispatch, pull."""
    return dict(
        peer_http_max_workers=max(1, min(256, int(args.peer_http_max_workers))),
        peer_advertise_url=str(args.peer_advertise_url),
        peer_advertise_host=str(args.peer_advertise_host),
        peer_advertise_port=int(args.peer_advertise_port),
        gossip_advertise_host=str(args.gossip_advertise_host),
        gossip_advertise_port=int(args.gossip_advertise_port),
        seed_peers=[item.strip() for item in str(args.seed_peers).split(",") if item.strip()],
        mesh_key=str(args.mesh_key),
        peer_sync_interval_s=max(0, int(args.peer_sync_interval_s)),
        peer_sync_fanout=max(0, min(256, int(args.peer_sync_fanout))),
        peer_event_limit=max(1, int(args.peer_event_limit)),
        peer_stale_after_s=max(0, int(args.peer_stale_after_s)),
        relay_enable=bool(args.relay_enable),
        relay_hops=max(1, int(args.relay_hops)),
        identity_key_path=str(args.identity_key_path),
        identity_dev_mesh_auth=bool(args.identity_dev_mesh_auth),
        reputation_score=float(args.reputation_score),
        replication_factor=max(0, int(args.replication_factor)),
        replication_quorum=max(0, int(args.replication_quorum)),
        discovery_seeds=[item.strip() for item in str(args.discovery_seeds).split(",") if item.strip()],
        discovery_sync_interval_s=max(0, int(args.discovery_sync_interval_s)),
        remote_dispatch_enable=bool(args.remote_dispatch_enable),
        remote_dispatch_limit=max(1, int(args.remote_dispatch_limit)),
        pull_tasks_enable=bool(args.pull_tasks_enable),
        pull_tasks_interval_s=max(0.25, float(args.pull_tasks_interval_s)),
        pull_tasks_batch_size=max(1, min(32, int(args.pull_tasks_batch_size))),
        app_version=str(args.app_version).strip() or "unknown",
    )


def _nat_and_scheduler_options(args: argparse.Namespace) -> dict[str, Any]:
    """NodeConfig fields: release, NAT traversal, scheduler weights, world."""
    return dict(
        release_channel=str(args.release_channel).strip().lower() or "dev",
        release_build=str(args.release_build).strip(),
        gossip_max_hops=max(1, min(32, int(args.gossip_max_hops))),
        nat_punch_enable=bool(args.nat_punch_enable),
        p2p_candidate_ttl_s=max(1, int(args.p2p_candidate_ttl_s)),
        p2p_candidate_refresh_s=max(1, int(args.p2p_candidate_refresh_s)),
        p2p_session_ttl_s=max(1, int(args.p2p_session_ttl_s)),
        p2p_punch_retry_count=max(1, int(args.p2p_punch_retry_count)),
        p2p_punch_interval_ms=max(1, int(args.p2p_punch_interval_ms)),
        p2p_session_timeout_ms=max(1, int(args.p2p_session_timeout_ms)),
        p2p_direct_transport_backend=str(args.p2p_direct_transport_backend),
        p2p_stun_server=str(args.p2p_stun_server),
        p2p_turn_server=str(args.p2p_turn_server),
        p2p_turn_username=str(args.p2p_turn_username),
        p2p_turn_password=str(args.p2p_turn_password),
        p2p_turn_transport=str(args.p2p_turn_transport),
        solana_reputation_enable=bool(args.solana_reputation_enable),
        solana_reputation_refresh_s=max(1, int(args.solana_reputation_refresh_s)),
        scheduler_onchain_weight=float(args.scheduler_onchain_weight),
        scheduler_offchain_weight=float(args.scheduler_offchain_weight),
        scheduler_capacity_weight=float(args.scheduler_capacity_weight),
        world=bool(args.world),
    )


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv``, build the node configuration and run the daemon."""
    args = build_arg_parser().parse_args(argv)
    if bool(args.world):
        _apply_world_defaults(args)
    args = apply_nat_traversal_defaults(args)
    export_dir = Path(args.export_dir).expanduser().resolve()
    state_dir = Path(args.state_dir).expanduser().resolve() if args.state_dir else export_dir / "node-state" / safe_path_id(safe_id(args.node_id))
    config = NodeConfig(
        export_dir=export_dir,
        state_dir=state_dir,
        **_node_and_solana_options(args),
        **_mesh_options(args),
        **_nat_and_scheduler_options(args),
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    NetworkNode(config).run()
    return 0
