"""Node configuration dataclass and the derived capacity/constraint helpers."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from tools.node.constants import DEFAULT_PEER_HTTP_MAX_WORKERS, DEFAULT_PEER_SYNC_FANOUT
from tools.node_defaults import DEFAULT_PEER_STALE_AFTER_S, DEFAULT_PEER_SYNC_INTERVAL_S
from tools.resource_intelligence import build_resource_profile


@dataclass
class NodeConfig:
    """Runtime configuration of a node (built by ``cli.main`` from CLI/env)."""

    export_dir: Path
    roles: set[str]
    node_id: str
    idle_ms: int
    once: bool
    max_items: int
    p2p_gateway: str
    state_dir: Path
    solana_enable: bool
    solana_rpc: str
    solana_program_id: str
    solana_wallet: str
    solana_bridge: Path
    solana_timeout_s: int
    max_retries: int
    bootstrap_worker: bool
    gossip_enable: bool
    gossip_bind: str
    gossip_port: int
    peer_http_bind: str
    peer_http_port: int
    peer_advertise_url: str = ""
    peer_advertise_host: str = ""
    peer_advertise_port: int = 0
    gossip_advertise_host: str = ""
    gossip_advertise_port: int = 0
    seed_peers: list[str] = field(default_factory=list)
    mesh_key: str = ""
    peer_sync_interval_s: int = DEFAULT_PEER_SYNC_INTERVAL_S
    peer_event_limit: int = 128
    peer_stale_after_s: int = DEFAULT_PEER_STALE_AFTER_S
    relay_enable: bool = False
    relay_hops: int = 2
    identity_key_path: str = ""
    identity_dev_mesh_auth: bool = False
    reputation_score: float = 0.0
    replication_factor: int = 0
    replication_quorum: int = 0
    discovery_seeds: list[str] = field(default_factory=list)
    discovery_sync_interval_s: int = 30
    remote_dispatch_enable: bool = False
    remote_dispatch_limit: int = 3
    nat_punch_enable: bool = False
    p2p_candidate_ttl_s: int = 60
    p2p_candidate_refresh_s: int = 20
    p2p_session_ttl_s: int = 120
    p2p_punch_retry_count: int = 8
    p2p_punch_interval_ms: int = 120
    p2p_session_timeout_ms: int = 2500
    p2p_direct_transport_backend: str = "auto"
    p2p_stun_server: str = ""
    p2p_turn_server: str = ""
    p2p_turn_username: str = ""
    p2p_turn_password: str = ""
    p2p_turn_transport: str = "udp"
    solana_reputation_enable: bool = False
    solana_reputation_refresh_s: int = 60
    scheduler_onchain_weight: float = 10.0
    scheduler_offchain_weight: float = 1.0
    scheduler_capacity_weight: float = 0.01
    world: bool = False
    pull_tasks_enable: bool = False
    # Pull is a fallback for NATed workers. Keep its idle latency below one
    # renderer tick without making the scheduler spin aggressively.
    pull_tasks_interval_s: float = 0.25
    # High-throughput workers can reserve several compatible tasks with one
    # authenticated request. The default remains one for compatibility.
    pull_tasks_batch_size: int = 1
    app_version: str = "unknown"
    release_channel: str = "dev"
    release_build: str = ""
    gossip_max_hops: int = 8
    # Bound HTTP and anti-entropy fan-out without changing legacy positional
    # construction of NodeConfig's existing fields.
    peer_http_max_workers: int = DEFAULT_PEER_HTTP_MAX_WORKERS
    peer_sync_fanout: int = DEFAULT_PEER_SYNC_FANOUT


def build_capacity_snapshot(config: NodeConfig) -> dict[str, Any]:
    """Static capacity profile announced to peers (CPU, disk, resource profile)."""
    disk = shutil.disk_usage(config.export_dir)
    return {
        "node_id": config.node_id,
        "roles": sorted(config.roles),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "solana_enabled": config.solana_enable,
        "resource_profile": build_resource_profile(config.export_dir),
    }


def _peer_constraints(body: Mapping[str, Any] | None, envelope: Mapping[str, Any] | None = None) -> dict[str, float]:
    body = body or {}
    envelope = envelope or {}
    on_chain = envelope.get("on_chain") if isinstance(envelope.get("on_chain"), dict) else {}
    if not isinstance(on_chain, dict):
        on_chain = {}

    def _float_value(*keys: str) -> float:
        for source in (body, envelope, on_chain):
            for key in keys:
                if key in source and source.get(key) not in (None, ""):
                    try:
                        return float(source.get(key))
                    except Exception:
                        continue
        return 0.0

    return {
        "min_global_reputation": _float_value("min_global_reputation", "required_global_reputation", "global_reputation_threshold"),
        "min_compute_reputation": _float_value("min_compute_reputation", "required_compute_reputation", "compute_reputation_threshold"),
        "min_verify_reputation": _float_value("min_verify_reputation", "required_verify_reputation", "verify_reputation_threshold"),
        "min_storage_reputation": _float_value("min_storage_reputation", "required_storage_reputation", "storage_reputation_threshold"),
        "min_stake_amount": _float_value("min_stake_amount", "required_stake", "stake_threshold"),
    }
