"""Shared helpers for the ``tests/test_network_node_*.py`` suites.

Not a test module. It provides the builders used by several node test files:

- ``_config``: a fully populated ``network_node.NodeConfig`` rooted in a temp dir
  (loopback binds, ephemeral ports, fast timers); also reused by
  ``test_workload_registry.py`` and ``test_release_channels.py``.
- ``_write_jsonl`` / ``_path_id``: append a JSONL record and compute the safe
  on-disk id the node uses for task files.
- ``_peer_registration_payload``: the registration body a peer sends to a seed.
- ``_signed_json_request_status`` / ``_signed_json_request``: POST a payload with
  the peer's signed headers and return ``(status, body)`` / the body.
"""

import json
import urllib.error
import urllib.request
from pathlib import Path

from tools import network_node


def _write_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _path_id(value: str) -> str:
    return network_node.safe_path_id(network_node.safe_id(value))


def _config(
    export_dir: Path,
    node_id: str,
    *,
    roles: str = "compute",
    seed_peers: list[str] | None = None,
    gossip_enable: bool = True,
    mesh_key: str = "",
    peer_sync_interval_s: int = 1,
    relay_enable: bool = False,
    identity_dev_mesh_auth: bool = False,
    reputation_score: float = 0.0,
    replication_factor: int = 0,
    replication_quorum: int = 0,
    discovery_seeds: list[str] | None = None,
    remote_dispatch_enable: bool = False,
    remote_dispatch_limit: int = 3,
    nat_punch_enable: bool = False,
    p2p_candidate_ttl_s: int = 60,
    p2p_candidate_refresh_s: int = 20,
    p2p_session_ttl_s: int = 120,
    p2p_punch_retry_count: int = 8,
    p2p_punch_interval_ms: int = 20,
    p2p_session_timeout_ms: int = 1000,
    p2p_direct_transport_backend: str = "native-light",
    p2p_stun_server: str = "",
    p2p_turn_server: str = "",
    p2p_turn_username: str = "",
    p2p_turn_password: str = "",
    p2p_turn_transport: str = "udp",
    solana_enable: bool = False,
    solana_bridge: Path | None = None,
    solana_wallet: str | None = None,
    solana_reputation_enable: bool = False,
    app_version: str = "0.2.9-dev.1",
    release_channel: str = "dev",
    release_build: str = "test-build",
) -> network_node.NodeConfig:
    state_dir = export_dir / "state"
    export_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    return network_node.NodeConfig(
        export_dir=export_dir,
        roles=network_node.parse_roles(roles),
        node_id=node_id,
        idle_ms=10,
        once=True,
        max_items=0,
        p2p_gateway="http://127.0.0.1:5001",
        state_dir=state_dir,
        solana_enable=solana_enable,
        solana_rpc="https://api.devnet.solana.com",
        solana_program_id="HyXT83SzHsEPxNZ5zQPvkLwQ7JwFHh2veAE5PuGUgoiQ",
        solana_wallet=str(solana_wallet or (export_dir / "wallet.json")),
        solana_bridge=solana_bridge or (export_dir / "bridge.cjs"),
        solana_timeout_s=10,
        max_retries=0,
        bootstrap_worker=False,
        gossip_enable=gossip_enable,
        gossip_bind="127.0.0.1",
        gossip_port=0,
        peer_http_bind="127.0.0.1",
        peer_http_port=0,
        peer_advertise_url="",
        peer_advertise_host="",
        peer_advertise_port=0,
        gossip_advertise_host="",
        gossip_advertise_port=0,
        seed_peers=seed_peers or [],
        mesh_key=mesh_key,
        peer_sync_interval_s=peer_sync_interval_s,
        peer_event_limit=64,
        peer_stale_after_s=60,
        relay_enable=relay_enable,
        relay_hops=2,
        identity_key_path="",
        identity_dev_mesh_auth=identity_dev_mesh_auth,
        reputation_score=reputation_score,
        replication_factor=replication_factor,
        replication_quorum=replication_quorum,
        discovery_seeds=discovery_seeds or [],
        discovery_sync_interval_s=1,
        remote_dispatch_enable=remote_dispatch_enable,
        remote_dispatch_limit=remote_dispatch_limit,
        pull_tasks_enable=False,
        pull_tasks_interval_s=2,
        nat_punch_enable=nat_punch_enable,
        p2p_candidate_ttl_s=p2p_candidate_ttl_s,
        p2p_candidate_refresh_s=p2p_candidate_refresh_s,
        p2p_session_ttl_s=p2p_session_ttl_s,
        p2p_punch_retry_count=p2p_punch_retry_count,
        p2p_punch_interval_ms=p2p_punch_interval_ms,
        p2p_session_timeout_ms=p2p_session_timeout_ms,
        p2p_direct_transport_backend=p2p_direct_transport_backend,
        p2p_stun_server=p2p_stun_server,
        p2p_turn_server=p2p_turn_server,
        p2p_turn_username=p2p_turn_username,
        p2p_turn_password=p2p_turn_password,
        p2p_turn_transport=p2p_turn_transport,
        app_version=app_version,
        release_channel=release_channel,
        release_build=release_build,
        solana_reputation_enable=solana_reputation_enable,
        solana_reputation_refresh_s=1,
        scheduler_onchain_weight=10.0,
        scheduler_offchain_weight=1.0,
        scheduler_capacity_weight=0.01,
    )


def _peer_registration_payload(peer: network_node.PeerNetwork) -> dict:
    return {
        "node_id": peer.node_id,
        "identity_id": peer.identity.identity_id,
        "public_key": peer.identity.public_key_b64,
        "roles": sorted(peer.config.roles),
        "features": peer.direct_transport.features(),
        "transport_attestations": peer.recent_transport_attestations(4),
        "http_base_url": peer.advertised_http_base_url,
        "mesh_post_url": peer.mesh_post_url,
        "gossip_bind": peer._advertised_gossip_host(),
        "gossip_port": peer._advertised_gossip_port(),
        "candidates": peer.refresh_candidates(force=True),
        "relay_capable": bool(peer.config.relay_enable),
        "capacity": peer.local_capacity,
        "reputation_score": peer.local_reputation_score,
        "timestamp_utc": network_node.utc_now(),
    }


def _signed_json_request_status(signer: network_node.PeerNetwork, base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    raw = network_node.stable_json(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=raw,
        method="POST",
        headers=signer._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _signed_json_request(signer: network_node.PeerNetwork, base_url: str, path: str, payload: dict) -> dict:
    status, body = _signed_json_request_status(signer, base_url, path, payload)
    assert status in {200, 201, 202}
    return body
