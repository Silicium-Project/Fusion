"""Command line of the integrated Python network daemon (`tools/network_node.py`).

`node start` (default mode) forwards its options to `network_node.main(argv)`.
Valued options are always forwarded, in a fixed order and grouped by feature;
optional paths and names only when set; boolean switches only when enabled.
"""

from __future__ import annotations

import argparse
from typing import Any, Mapping


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
        *_base_args(args, export_dir, node_id),
        *_mesh_args(args),
        *_replication_dispatch_args(args),
        *_nat_traversal_args(args),
        *_solana_scheduler_args(args),
    ]
    command.extend(_optional_value_args(args))
    command.extend(_boolean_flag_args(args))
    return command


def _base_args(args: argparse.Namespace, export_dir: str, node_id: str) -> list[str]:
    """Export directory, identity, release telemetry and main loop pacing."""
    return [
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
    ]


def _mesh_args(args: argparse.Namespace) -> list[str]:
    """Gossip and peer HTTP endpoints, seeds, peer sync and relay hops."""
    return [
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
    ]


def _replication_dispatch_args(args: argparse.Namespace) -> list[str]:
    """Reputation, replication, discovery, remote dispatch and task pulling."""
    return [
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
    ]


def _nat_traversal_args(args: argparse.Namespace) -> list[str]:
    """Direct transport sessions, hole punching and TURN credentials."""
    return [
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
    ]


def _solana_scheduler_args(args: argparse.Namespace) -> list[str]:
    """Solana settlement, retries, on-chain reputation and scheduler weights."""
    return [
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


def _optional_value_args(args: argparse.Namespace) -> list[str]:
    """Paths, servers and world settings, forwarded only when non-empty."""
    command: list[str] = []
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
    return command


def _boolean_flag_args(args: argparse.Namespace) -> list[str]:
    """Switches forwarded only when enabled."""
    command: list[str] = []
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
