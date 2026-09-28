"""`node start`: world-mode and NAT defaults, then launch of the Python
network node (default) or of the experimental Rust `p2p_node`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import subprocess
from typing import Any, Mapping

from tools.cli.constants import LOCAL_STATE_DIR, REPO_ROOT
from tools.cli.context import Context, _resolve_mcp_settings
from tools.node_defaults import (
    DEFAULT_PEER_STALE_AFTER_S,
    DEFAULT_PEER_SYNC_INTERVAL_S,
    WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S,
    WORLD_DEFAULT_GOSSIP_PORT,
    WORLD_DEFAULT_PEER_HTTP_PORT,
    WORLD_DEFAULT_PEER_SYNC_INTERVAL_S,
)
from tools.node_defaults import apply_nat_traversal_defaults as _apply_nat_traversal_defaults
from tools.node_defaults import derive_world_mesh_key as _derive_world_mesh_key
from tools.node_defaults import guess_world_advertise_host as _guess_world_advertise_host
from tools.node_defaults import merge_csv as _merge_csv


def _apply_world_mode_defaults(args: argparse.Namespace, *, node_id: str) -> argparse.Namespace:
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


def configure_node_start(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--export-dir", default="", help="MCP/network export directory (default: MCP config).")
    parser.add_argument("--app-version", default=os.environ.get("SILICIUM_APP_VERSION", "unknown"))
    parser.add_argument(
        "--release-channel",
        default=os.environ.get("SILICIUM_RELEASE_CHANNEL", "dev"),
        choices=["dev", "prod"],
    )
    parser.add_argument("--release-build", default=os.environ.get("SILICIUM_RELEASE_BUILD", ""))
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
    parser.add_argument("--solana-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_ENABLE", "0") == "1")
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument(
        "--solana-program-id",
        default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"),
    )
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.path.expanduser("~/.config/solana/id.json")))
    parser.add_argument("--solana-bridge", default=os.environ.get("SILICIUM_SOLANA_BRIDGE", str(REPO_ROOT / "tools" / "solana_layer_bridge.cjs")))
    parser.add_argument("--solana-timeout-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_TIMEOUT_S", "45")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_RETRIES", "2")))
    parser.add_argument("--bootstrap-worker", action="store_true", default=os.environ.get("SILICIUM_BOOTSTRAP_WORKER", "0") == "1")
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
    parser.add_argument("--solana-reputation-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_REPUTATION_ENABLE", "0") == "1")
    parser.add_argument("--solana-reputation-refresh-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_REPUTATION_REFRESH_S", "60")))
    parser.add_argument("--scheduler-onchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_ONCHAIN_WEIGHT", "10")))
    parser.add_argument("--scheduler-offchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_OFFCHAIN_WEIGHT", "1")))
    parser.add_argument("--scheduler-capacity-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_CAPACITY_WEIGHT", "0.01")))


def _p2p_node_command() -> list[str]:
    override = os.environ.get("SILICIUM_P2P_NODE_BIN", "").strip()
    if override:
        return [override]

    binary_name = "p2p_node.exe" if os.name == "nt" else "p2p_node"
    release_binary = REPO_ROOT / "crates" / "p2p-node" / "target" / "release" / binary_name
    if release_binary.exists():
        return [str(release_binary)]

    # Never turn a node startup into an implicit production build. End-user
    # runtimes must execute a packaged binary, while developers can opt in by
    # setting SILICIUM_P2P_NODE_BIN explicitly.
    raise RuntimeError("p2p_node_binary_not_found:set_SILICIUM_P2P_NODE_BIN")  # i18n:ignore -- stable machine error code


def _build_p2p_node_env(args: argparse.Namespace, settings: Mapping[str, Any], node_id: str) -> dict[str, str]:
    env = os.environ.copy()
    export_dir = str(args.export_dir or settings["export_dir"])
    env["SILICIUM_APP_VERSION"] = str(args.app_version)
    env["SILICIUM_RELEASE_CHANNEL"] = str(args.release_channel)
    env["SILICIUM_RELEASE_BUILD"] = str(args.release_build)
    env["SILICIUM_NODE_ID"] = node_id
    env["SILICIUM_DATA_DIR"] = export_dir
    env["SILICIUM_DISPATCH_SEED"] = str(
        int.from_bytes(hashlib.sha256(node_id.encode("utf-8")).digest()[:8], "little")
    )
    if getattr(args, "seed_peers", ""):
        env["SILICIUM_BOOTSTRAP_PEERS"] = str(args.seed_peers)
    if getattr(args, "peer_http_port", 0):
        env["API_PORT"] = str(args.peer_http_port)
    return env


def _run_p2p_node(command: list[str], env: Mapping[str, str]) -> int:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=dict(env),
        check=False,
    )
    return int(completed.returncode)


def _network_node_args(
    args: argparse.Namespace,
    settings: Mapping[str, Any],
    node_id: str,
) -> list[str]:
    """Translate the public CLI node options to the integrated daemon.

    ``node start`` used to launch the Rust p2p experiment.  That process has a
    small localhost API but does not publish the heartbeat/peer registry used
    by the site.  Keep the translation in one place so the desktop app,
    ``start-node.sh`` and local network emitters all exercise the same daemon.
    """

    export_dir = str(args.export_dir or settings["export_dir"])
    command = [
        "--export-dir",
        export_dir,
        "--node-id",
        node_id,
        "--roles",
        str(args.roles),
        "--app-version",
        str(args.app_version),
        "--release-channel",
        str(args.release_channel),
        "--release-build",
        str(args.release_build),
        "--idle-ms",
        str(args.idle_ms),
        "--max-items",
        str(args.max_items),
        "--p2p-gateway",
        str(args.p2p_gateway),
        "--gossip-bind",
        str(args.gossip_bind),
        "--gossip-port",
        str(args.gossip_port),
        "--peer-http-bind",
        str(args.peer_http_bind),
        "--peer-http-port",
        str(args.peer_http_port),
        "--peer-http-max-workers",
        str(args.peer_http_max_workers),
        "--peer-advertise-url",
        str(args.peer_advertise_url),
        "--peer-advertise-host",
        str(args.peer_advertise_host),
        "--peer-advertise-port",
        str(args.peer_advertise_port),
        "--gossip-advertise-host",
        str(args.gossip_advertise_host),
        "--gossip-advertise-port",
        str(args.gossip_advertise_port),
        "--seed-peers",
        str(args.seed_peers),
        "--mesh-key",
        str(args.mesh_key),
        "--peer-sync-interval-s",
        str(args.peer_sync_interval_s),
        "--peer-sync-fanout",
        str(args.peer_sync_fanout),
        "--peer-event-limit",
        str(args.peer_event_limit),
        "--gossip-max-hops",
        str(args.gossip_max_hops if hasattr(args, "gossip_max_hops") else 8),
        "--peer-stale-after-s",
        str(args.peer_stale_after_s),
        "--relay-hops",
        str(args.relay_hops),
        "--reputation-score",
        str(args.reputation_score),
        "--replication-factor",
        str(args.replication_factor),
        "--replication-quorum",
        str(args.replication_quorum),
        "--discovery-seeds",
        str(args.discovery_seeds),
        "--discovery-sync-interval-s",
        str(args.discovery_sync_interval_s),
        "--remote-dispatch-limit",
        str(args.remote_dispatch_limit),
        "--pull-tasks-interval-s",
        str(args.pull_tasks_interval_s),
        "--pull-tasks-batch-size",
        str(args.pull_tasks_batch_size),
        "--p2p-candidate-ttl-s",
        str(args.p2p_candidate_ttl_s),
        "--p2p-candidate-refresh-s",
        str(args.p2p_candidate_refresh_s),
        "--p2p-session-ttl-s",
        str(args.p2p_session_ttl_s),
        "--p2p-punch-retry-count",
        str(args.p2p_punch_retry_count),
        "--p2p-punch-interval-ms",
        str(args.p2p_punch_interval_ms),
        "--p2p-session-timeout-ms",
        str(args.p2p_session_timeout_ms),
        "--p2p-direct-transport-backend",
        str(args.p2p_direct_transport_backend),
        "--p2p-turn-username",
        str(args.p2p_turn_username),
        "--p2p-turn-password",
        str(args.p2p_turn_password),
        "--p2p-turn-transport",
        str(args.p2p_turn_transport),
        "--solana-rpc",
        str(args.solana_rpc),
        "--solana-program-id",
        str(args.solana_program_id),
        "--solana-wallet",
        str(args.solana_wallet),
        "--solana-bridge",
        str(args.solana_bridge),
        "--solana-timeout-s",
        str(args.solana_timeout_s),
        "--max-retries",
        str(args.max_retries),
        "--solana-reputation-refresh-s",
        str(args.solana_reputation_refresh_s),
        "--scheduler-onchain-weight",
        str(args.scheduler_onchain_weight),
        "--scheduler-offchain-weight",
        str(args.scheduler_offchain_weight),
        "--scheduler-capacity-weight",
        str(args.scheduler_capacity_weight),
    ]
    if str(args.state_dir).strip():
        command.extend(["--state-dir", str(args.state_dir)])
    if str(args.identity_key_path).strip():
        command.extend(["--identity-key-path", str(args.identity_key_path)])
    if str(args.p2p_stun_server).strip():
        command.extend(["--p2p-stun-server", str(args.p2p_stun_server)])
    if str(args.p2p_turn_server).strip():
        command.extend(["--p2p-turn-server", str(args.p2p_turn_server)])
    if str(args.world_name).strip():
        command.extend(["--world-name", str(args.world_name)])
    if str(args.world_seeds).strip():
        command.extend(["--world-seeds", str(args.world_seeds)])

    boolean_flags = {
        "world": "--world",
        "once": "--once",
        "bootstrap_worker": "--bootstrap-worker",
        "gossip_enable": "--gossip-enable",
        "relay_enable": "--relay-enable",
        "identity_dev_mesh_auth": "--identity-dev-mesh-auth",
        "remote_dispatch_enable": "--remote-dispatch-enable",
        "pull_tasks_enable": "--pull-tasks-enable",
        "nat_punch_enable": "--nat-punch-enable",
        "solana_enable": "--solana-enable",
        "solana_reputation_enable": "--solana-reputation-enable",
    }
    for attribute, flag in boolean_flags.items():
        if bool(getattr(args, attribute, False)):
            command.append(flag)
    return command


def _run_network_node(
    args: argparse.Namespace,
    settings: Mapping[str, Any],
    node_id: str,
) -> int:
    from tools import network_node

    return int(network_node.main(_network_node_args(args, settings, node_id)))


def cmd_node_start(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)

    node_id = args.node_id or f"node-{secrets.token_hex(4)}"
    args = _apply_world_mode_defaults(args, node_id=node_id)
    args = _apply_nat_traversal_defaults(args)
    if not bool(getattr(args, "experimental_p2p_node", False)):
        raise SystemExit(_run_network_node(args, settings, node_id))

    # The Rust p2p_node is retained as an explicitly opt-in experiment.  It is
    # not the production node because it does not publish the integrated
    # heartbeat and peer registry consumed by the site.
    command = _p2p_node_command()
    dispatch_seed = int.from_bytes(hashlib.sha256(node_id.encode("utf-8")).digest()[:8], "little")
    env = _build_p2p_node_env(args, settings, node_id)
    p2p_args = [
        "--data-dir",
        str(args.export_dir or settings["export_dir"]),
        "--dispatcher-seed",
        str(dispatch_seed),
    ]
    if getattr(args, "peer_http_port", 0):
        p2p_args.extend(["--api-port", str(args.peer_http_port)])
    if getattr(args, "seed_peers", ""):
        p2p_args.extend(["--bootstrap-peers", str(args.seed_peers)])
    if getattr(args, "gossip_enable", False):
        p2p_args.append("--enable-quic")
    raise SystemExit(_run_p2p_node([*command, *p2p_args], env))
