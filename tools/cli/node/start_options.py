"""Argument parser of `silicium node start`.

The options are registered in a fixed order (it is the order shown by
`--help`), grouped by feature in small helpers. Most defaults come from
`SILICIUM_*` environment variables so the desktop app and `start-node.sh`
can configure the node without command-line flags.
"""

from __future__ import annotations

import argparse
import os

from tools.cli.constants import REPO_ROOT
from tools.node_defaults import DEFAULT_PEER_STALE_AFTER_S, DEFAULT_PEER_SYNC_INTERVAL_S


def configure_node_start(parser: argparse.ArgumentParser) -> None:
    """Register every `node start` option on `parser`, in help order."""
    _add_release_options(parser)
    _add_mode_options(parser)
    _add_runtime_options(parser)
    _add_solana_options(parser)
    _add_worker_options(parser)
    _add_mesh_options(parser)
    _add_relay_identity_options(parser)
    _add_replication_dispatch_options(parser)
    _add_nat_traversal_options(parser)
    _add_scheduler_options(parser)


def _add_release_options(parser: argparse.ArgumentParser) -> None:
    """Export directory and release telemetry (version, channel, build)."""
    parser.add_argument("--export-dir", default="", help="MCP/network export directory (default: MCP config).")
    parser.add_argument("--app-version", default=os.environ.get("SILICIUM_APP_VERSION", "unknown"))
    parser.add_argument(
        "--release-channel",
        default=os.environ.get("SILICIUM_RELEASE_CHANNEL", "dev"),
        choices=["dev", "prod"],
    )
    parser.add_argument("--release-build", default=os.environ.get("SILICIUM_RELEASE_BUILD", ""))


def _add_mode_options(parser: argparse.ArgumentParser) -> None:
    """World mesh mode and the experimental Rust `p2p_node` switch."""
    parser.add_argument(
        "--world",
        action="store_true",
        default=os.environ.get("SILICIUM_WORLD_MODE", "0") == "1",
        help="Enable one-command wide-area mesh defaults (gossip, relay, dispatch, NAT punch, advertised endpoints).",
    )
    parser.add_argument(
        "--experimental-p2p-node",
        action="store_true",
        default=os.environ.get("SILICIUM_EXPERIMENTAL_P2P_NODE", "0") == "1",
        help="Run the experimental Rust p2p_node core instead of the integrated network daemon.",
    )
    parser.add_argument(
        "--world-name",
        default=os.environ.get("SILICIUM_WORLD_NAME", ""),
        help="Shared world namespace used to derive a deterministic mesh key when --mesh-key is omitted.",
    )
    parser.add_argument(
        "--world-seeds",
        default=os.environ.get("SILICIUM_WORLD_SEEDS", ""),
        help="Comma-separated discovery seed URLs used by --world mode.",
    )


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    """Node identity, roles and main loop pacing."""
    parser.add_argument(
        "--roles",
        default=os.environ.get("SILICIUM_NODE_ROLES", "compute,verify,storage,audit,resource"),
        help="Comma-separated node roles: compute,verify,storage,audit,resource.",
    )
    parser.add_argument("--node-id", default=os.environ.get("SILICIUM_NODE_ID", ""), help="Stable node identifier.")
    parser.add_argument("--idle-ms", type=int, default=int(os.environ.get("SILICIUM_NODE_IDLE_MS", "250")))
    parser.add_argument("--once", action="store_true", help="Run one sweep and exit.")
    parser.add_argument("--max-items", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_ITEMS", "0")))
    parser.add_argument("--p2p-gateway", default=os.environ.get("SILICIUM_P2P_GATEWAY", "http://127.0.0.1:5001"))
    parser.add_argument("--state-dir", default="", help="Node cursor/state directory.")


def _add_solana_options(parser: argparse.ArgumentParser) -> None:
    """Solana settlement (RPC, program, wallet, bridge)."""
    parser.add_argument("--solana-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_ENABLE", "0") == "1")
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument(
        "--solana-program-id",
        default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"),
    )
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.path.expanduser("~/.config/solana/id.json")))
    parser.add_argument("--solana-bridge", default=os.environ.get("SILICIUM_SOLANA_BRIDGE", str(REPO_ROOT / "tools" / "solana_layer_bridge.cjs")))
    parser.add_argument("--solana-timeout-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_TIMEOUT_S", "45")))


def _add_worker_options(parser: argparse.ArgumentParser) -> None:
    """Retry budget and bootstrap worker."""
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_RETRIES", "2")))
    parser.add_argument("--bootstrap-worker", action="store_true", default=os.environ.get("SILICIUM_BOOTSTRAP_WORKER", "0") == "1")


def _add_mesh_options(parser: argparse.ArgumentParser) -> None:
    """Gossip and peer HTTP binds, advertised endpoints, seeds and peer sync."""
    parser.add_argument("--gossip-enable", action="store_true", default=os.environ.get("SILICIUM_GOSSIP_ENABLE", "0") == "1")
    parser.add_argument("--gossip-bind", default=os.environ.get("SILICIUM_GOSSIP_BIND", "127.0.0.1"))
    parser.add_argument("--gossip-port", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_PORT", "0")))
    parser.add_argument("--peer-http-bind", default=os.environ.get("SILICIUM_PEER_HTTP_BIND", "127.0.0.1"))
    parser.add_argument("--peer-http-port", type=int, default=int(os.environ.get("SILICIUM_PEER_HTTP_PORT", "0")))
    parser.add_argument(
        "--peer-http-max-workers",
        type=int,
        default=int(os.environ.get("SILICIUM_PEER_HTTP_MAX_WORKERS", "16")),
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
        default=int(os.environ.get("SILICIUM_PEER_SYNC_FANOUT", "8")),
        help="Additional peer HTTP anti-entropy targets per sync (0 means unlimited; default: 8).",
    )
    parser.add_argument("--peer-event-limit", type=int, default=int(os.environ.get("SILICIUM_PEER_EVENT_LIMIT", "128")))
    parser.add_argument("--peer-stale-after-s", type=int, default=int(os.environ.get("SILICIUM_PEER_STALE_AFTER_S", str(DEFAULT_PEER_STALE_AFTER_S))))


def _add_relay_identity_options(parser: argparse.ArgumentParser) -> None:
    """Relay, node identity key and reputation score."""
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


def _add_replication_dispatch_options(parser: argparse.ArgumentParser) -> None:
    """Replication, discovery, remote dispatch and task pulling."""
    parser.add_argument("--replication-factor", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_FACTOR", "0")))
    parser.add_argument("--replication-quorum", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_QUORUM", "0")))
    parser.add_argument("--discovery-seeds", default=os.environ.get("SILICIUM_DISCOVERY_SEEDS", ""))
    parser.add_argument("--discovery-sync-interval-s", type=int, default=int(os.environ.get("SILICIUM_DISCOVERY_SYNC_INTERVAL_S", "30")))
    parser.add_argument("--remote-dispatch-enable", action="store_true", default=os.environ.get("SILICIUM_REMOTE_DISPATCH_ENABLE", "0") == "1")
    parser.add_argument("--remote-dispatch-limit", type=int, default=int(os.environ.get("SILICIUM_REMOTE_DISPATCH_LIMIT", "3")))
    parser.add_argument("--pull-tasks-enable", action="store_true", default=os.environ.get("SILICIUM_PULL_TASKS_ENABLE", "0") == "1")
    parser.add_argument("--pull-tasks-interval-s", type=float, default=float(os.environ.get("SILICIUM_PULL_TASKS_INTERVAL_S", "0.25")))
    parser.add_argument("--pull-tasks-batch-size", type=int, default=int(os.environ.get("SILICIUM_PULL_TASKS_BATCH_SIZE", "1")))


def _add_nat_traversal_options(parser: argparse.ArgumentParser) -> None:
    """NAT hole punching, STUN/TURN and direct transport sessions."""
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
    parser.add_argument("--p2p-turn-username", default=os.environ.get("SILICIUM_P2P_TURN_USERNAME", ""))
    parser.add_argument("--p2p-turn-password", default=os.environ.get("SILICIUM_P2P_TURN_PASSWORD", ""))
    parser.add_argument("--p2p-turn-transport", default=os.environ.get("SILICIUM_P2P_TURN_TRANSPORT", "udp"), choices=["udp", "tcp"])


def _add_scheduler_options(parser: argparse.ArgumentParser) -> None:
    """On-chain reputation refresh and scheduler weights."""
    parser.add_argument("--solana-reputation-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_REPUTATION_ENABLE", "0") == "1")
    parser.add_argument("--solana-reputation-refresh-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_REPUTATION_REFRESH_S", "60")))
    parser.add_argument("--scheduler-onchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_ONCHAIN_WEIGHT", "10")))
    parser.add_argument("--scheduler-offchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_OFFCHAIN_WEIGHT", "1")))
    parser.add_argument("--scheduler-capacity-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_CAPACITY_WEIGHT", "0.01")))
