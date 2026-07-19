import json
import types
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tools import direct_transport, network_node


def _write_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _path_id(value: str) -> str:
    return network_node.safe_path_id(network_node.safe_id(value))


def _fake_solana_bridge(path: Path) -> Path:
    path.write_text(
        """
let data = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => data += chunk);
process.stdin.on("end", () => {
  const request = JSON.parse(data || "{}");
  if (request.op === "fetch_worker") {
    const owner = String((request.params || {}).owner || "");
    const profile = owner.endsWith("A")
      ? { compute: 9000, verify: 6000, storage: 7000, global: 7000, stake: 2500, status: "active" }
      : owner.endsWith("B")
        ? { compute: 6000, verify: 9500, storage: 8500, global: 9000, stake: 5000, status: "active" }
        : { compute: 5000, verify: 5000, storage: 5000, global: 5000, stake: 1000, status: "active" };
    process.stdout.write(JSON.stringify({
      ok: true,
      op: request.op,
      account: {
        owner,
        globalReputation: profile.global,
        computeReputation: profile.compute,
        verifyReputation: profile.verify,
        storageReputation: profile.storage,
        stakeAmount: profile.stake,
        status: profile.status
      },
      accounts: { owner, worker: "worker-" + owner }
    }) + "\\n");
    return;
  }
  process.stdout.write(JSON.stringify({
    ok: true,
    op: request.op,
    params: request.params,
    signatures: ["sig-" + request.op],
    accounts: { touched: "account" }
  }) + "\\n");
});
""".strip(),
        encoding="utf-8",
    )
    return path


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
        worker_binary="missing-worker",
        worker_mode="emu",
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
        solana_reputation_enable=solana_reputation_enable,
        solana_reputation_refresh_s=1,
        scheduler_onchain_weight=10.0,
        scheduler_offchain_weight=1.0,
        scheduler_capacity_weight=0.01,
    )


def _resign_handshake(peer: network_node.PeerNetwork, handshake: dict) -> dict:
    unsigned = dict(handshake)
    unsigned.pop("signature", None)
    unsigned["signature"] = peer.identity.sign_bytes(network_node.stable_json(unsigned).encode("utf-8"))
    return unsigned


class _RequestStub:
    def __init__(self, headers: dict[str, str], *, command: str = "GET", path: str = "/peers") -> None:
        self.headers = headers
        self.command = command
        self.path = path


class _FakeIceCandidate:
    def __init__(
        self,
        foundation: str = "fake-foundation",
        component: int = 1,
        transport: str = "udp",
        priority: int = 2130706431,
        host: str = "127.0.0.1",
        port: int = 49000,
        type: str = "host",
        **_kwargs: object,
    ) -> None:
        self.foundation = foundation
        self.component = component
        self.transport = transport
        self.priority = priority
        self.host = host
        self.port = port
        self.type = type

    @classmethod
    def from_sdp(cls, sdp: str) -> "_FakeIceCandidate":
        parts = str(sdp).split()
        candidate_type = parts[7] if len(parts) > 7 and parts[6] == "typ" else "host"
        return cls(
            foundation=parts[0] if len(parts) > 0 else "remote-foundation",
            component=int(parts[1]) if len(parts) > 1 else 1,
            transport=parts[2] if len(parts) > 2 else "udp",
            priority=int(parts[3]) if len(parts) > 3 else 1,
            host=parts[4] if len(parts) > 4 else "127.0.0.1",
            port=int(parts[5]) if len(parts) > 5 else 49000,
            type=candidate_type,
        )

    def to_sdp(self) -> str:
        return f"{self.foundation} {self.component} {self.transport} {self.priority} {self.host} {self.port} typ {self.type}"


class _FakeIceConnection:
    _next_port = 49000

    def __init__(self, ice_controlling: bool, **_kwargs: object) -> None:
        _FakeIceConnection._next_port += 1
        self.ice_controlling = ice_controlling
        self.local_username = "ufrag-controlling" if ice_controlling else "ufrag-controlled"
        self.local_password = "pwd-controlling" if ice_controlling else "pwd-controlled"
        self.local_candidates: list[_FakeIceCandidate] = []
        self.remote_candidates: list[_FakeIceCandidate | None] = []
        self.remote_username = ""
        self.remote_password = ""
        self._candidate = _FakeIceCandidate(port=_FakeIceConnection._next_port)

    async def gather_candidates(self) -> None:
        self.local_candidates = [self._candidate]

    def get_default_candidate(self, _component: int) -> _FakeIceCandidate:
        return self._candidate

    async def add_remote_candidate(self, candidate: _FakeIceCandidate | None) -> None:
        self.remote_candidates.append(candidate)

    async def connect(self) -> None:
        if not self.remote_username or not self.remote_password:
            raise ConnectionError("remote credentials missing")


def _fake_aioice_module() -> types.SimpleNamespace:
    return types.SimpleNamespace(Connection=_FakeIceConnection, Candidate=_FakeIceCandidate)


def _peer_registration_payload(peer: network_node.PeerNetwork) -> dict:
    return {
        "node_id": peer.node_id,
        "identity_id": peer.identity.identity_id,
        "public_key": peer.identity.public_key_b64,
        "roles": sorted(peer.config.roles),
        "features": peer.direct_transport.features(),
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


def _signed_punch_start(signal: network_node.PeerNetwork, peer_a: network_node.PeerNetwork, peer_b: network_node.PeerNetwork, session_id: str = "p2p-sess-test") -> dict:
    pairs = signal._candidate_pairs(_peer_registration_payload(peer_a), _peer_registration_payload(peer_b))
    session = {
        "session_id": session_id,
        "initiator_peer_id": peer_a.node_id,
        "target_peer_id": peer_b.node_id,
        "candidate_pairs": pairs,
    }
    return signal._punch_start_message(session)


def test_peer_identity_persists_across_restarts(tmp_path: Path) -> None:
    export_dir = tmp_path / "identity"
    config = _config(export_dir, "node-a")

    first = network_node.NodeIdentity(config)
    second = network_node.NodeIdentity(config)

    assert first.identity_id == second.identity_id
    assert first.public_key_b64 == second.public_key_b64
    assert first.private_key_path.exists()
    assert first.public_key_path.exists()


def test_session_handshake_accepts_valid_signed_payload(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a", roles="compute", reputation_score=25), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b", roles="verify"), tmp_path / "target")

    handshake = source.create_session_handshake(
        target_peer_id="node-b",
        session_id="sess-valid",
        purpose="fragment_fetch",
        task_id="task-1",
        candidate_fingerprints=[{"candidate_id": "cand-a", "expires_unix": int(time.time()) + 60}],
    )

    ok, reason = target.verify_session_handshake(
        handshake,
        expected_peer_id="node-a",
        expected_target_peer_id="node-b",
        authorized_task_ids={"task-1"},
    )
    assert ok, reason


def test_session_handshake_rejects_replay(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-replay")

    assert target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")[0]
    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_replay"


def test_session_handshake_rejects_wrong_peer_id(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-wrong-peer")

    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-c", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_peer_mismatch"


def test_session_handshake_rejects_expired_payload(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-expired")
    handshake["timestamp_unix"] = int(time.time()) - 600
    handshake["expires_unix"] = int(time.time()) - 300
    handshake = _resign_handshake(source, handshake)

    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_expired"


def test_session_handshake_rejects_tampered_payload(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-tamper", task_id="task-1")
    handshake["task_id"] = "task-2"

    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_signature_invalid"


def test_session_handshake_rejects_unauthorized_task(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-task", task_id="task-a")

    ok, reason = target.verify_session_handshake(
        handshake,
        expected_peer_id="node-a",
        expected_target_peer_id="node-b",
        authorized_task_ids={"task-b"},
    )
    assert not ok
    assert reason == "handshake_task_unauthorized"


def test_mesh_key_bearer_auth_requires_explicit_dev_flag(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a", mesh_key="demo-mesh"), tmp_path / "peer")
    request = _RequestStub({"Authorization": "Bearer demo-mesh"})

    assert not peer._authorize_peer_request(request)

    dev_peer = network_node.PeerNetwork(
        _config(tmp_path / "dev-peer", "node-a", mesh_key="demo-mesh", identity_dev_mesh_auth=True),
        tmp_path / "dev-peer",
    )
    assert dev_peer._authorize_peer_request(request)


def test_candidate_gathering_reports_host_and_server_observed_candidates(tmp_path: Path) -> None:
    config = _config(tmp_path / "peer", "node-a", p2p_candidate_ttl_s=30, p2p_candidate_refresh_s=1)
    config.gossip_port = 46101
    config.gossip_advertise_host = "192.168.1.20"
    peer = network_node.PeerNetwork(config, tmp_path / "peer")

    host_candidates = peer.refresh_candidates(force=True)
    host = next(candidate for candidate in host_candidates if candidate["ip"] == "192.168.1.20")
    assert host["candidate_type"] == "host"
    assert host["address_family"] == "ipv4"
    assert host["private"] is True
    assert host["internet_routable"] is False
    assert host["expires_unix"] > int(time.time())

    observed = peer.record_observed_candidate("93.184.216.34", source="observe:http://seed")
    assert observed is not None
    assert observed["candidate_type"] == "srflx"
    assert observed["internet_routable"] is True
    diagnostics = peer.candidate_diagnostics()
    assert diagnostics["observed_public_address"] == "93.184.216.34"
    assert diagnostics["selected_candidate"]["candidate_type"] == "srflx"
    assert (tmp_path / "peer" / "p2p.candidates.json").exists()


def test_candidate_validation_rejects_malformed_candidates(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [
            {"candidate_type": "host", "transport": "udp", "ip": "not-an-ip", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "host", "transport": "tcp", "ip": "127.0.0.1", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "invalid", "transport": "udp", "ip": "127.0.0.1", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "host", "transport": "udp", "ip": "127.0.0.1", "port": 0, "observed_unix": now, "expires_unix": now + 30},
        ],
        "node-b",
        now,
    )

    assert candidates == []


def test_candidate_validation_rejects_expired_candidates(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [{"candidate_type": "host", "transport": "udp", "ip": "127.0.0.1", "port": 46101, "observed_unix": now - 60, "expires_unix": now - 1}],
        "node-b",
        now,
    )

    assert candidates == []


def test_candidate_validation_deduplicates_candidates(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [
            {"candidate_type": "host", "transport": "udp", "ip": "10.0.0.5", "port": 46101, "priority": 10, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "host", "transport": "udp", "ip": "10.0.0.5", "port": 46101, "priority": 30, "observed_unix": now, "expires_unix": now + 30},
        ],
        "node-b",
        now,
    )

    assert len(candidates) == 1
    assert candidates[0]["priority"] == 30


def test_candidate_validation_formats_ipv4_and_ipv6(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [
            {"candidate_type": "srflx", "transport": "udp", "ip": "93.184.216.34", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "srflx", "transport": "udp", "ip": "[2001:4860:4860::8888]", "port": 46102, "observed_unix": now, "expires_unix": now + 30},
        ],
        "node-b",
        now,
    )

    by_ip = {candidate["ip"]: candidate for candidate in candidates}
    assert by_ip["2001:4860:4860::8888"]["address_family"] == "ipv6"
    assert by_ip["93.184.216.34"]["address_family"] == "ipv4"


def test_network_node_processes_role_task_with_p2p_ref(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "p2p").mkdir()
    (export_dir / "p2p" / "bafyinput").write_bytes(b"payload")

    task = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "storage:1",
        "status": "queued",
        "required_roles": ["storage"],
        "priority": "high",
        "p2p_ref": {"protocol": "ipfs", "content_id": "bafyinput"},
        "task": {"kind": "storage", "path": "object.bin"},
    }
    _write_jsonl(export_dir / "tasks.storage.queue.ndjson", task)

    code = network_node.main(
        [
            "--export-dir",
            str(export_dir),
            "--roles",
            "storage",
            "--node-id",
            "node-a",
            "--once",
        ]
    )
    assert code == 0

    result = json.loads((export_dir / f"result.{_path_id('storage:1')}.json").read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["required_roles"] == ["storage"]
    assert result["input"]["source"] == "local-p2p-cache"
    assert result["role_result"] == "storage"
    assert result["stored_ref"]["hash"].startswith("sha256:")

    stored = json.loads((export_dir / "tasks" / f"{_path_id('storage:1')}.json").read_text(encoding="utf-8"))
    assert stored["status"] == "completed"
    assert stored["handled_by"] == "node-a"
    assert (export_dir / "node.node-a.heartbeat.json").exists()
    metrics = json.loads((export_dir / "node.node-a.metrics.json").read_text(encoding="utf-8"))
    assert metrics["handled"] == 1


def test_network_node_prioritizes_urgent_requests(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "p2p").mkdir()
    (export_dir / "p2p" / "auditcid").write_bytes(b"audit-data")

    task = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "compute:late",
        "status": "queued",
        "required_roles": ["compute"],
        "task": {"kind": "compute"},
    }
    request = {
        "schema_version": 1,
        "envelope_kind": "request",
        "request_id": "audit:now",
        "kind": "audit",
        "status": "queued",
        "priority": "urgent",
        "target_roles": ["audit"],
        "p2p_ref": {"protocol": "ipfs", "content_id": "auditcid"},
        "request": {"sample": "full"},
    }
    _write_jsonl(export_dir / "tasks.compute.queue.ndjson", task)
    _write_jsonl(export_dir / "requests.urgent.ndjson", request)

    code = network_node.main(
        [
            "--export-dir",
            str(export_dir),
            "--roles",
            "compute,audit",
            "--node-id",
            "node-a",
            "--once",
            "--max-items",
            "1",
        ]
    )
    assert code == 0

    assert (export_dir / f"result.{_path_id('audit:now')}.json").exists()
    assert not (export_dir / f"result.{_path_id('compute:late')}.json").exists()
    events = [json.loads(line) for line in (export_dir / "node.events.ndjson").read_text(encoding="utf-8").splitlines()]
    assert events[0]["kind"] == "request"


def test_network_node_submits_compute_result_on_chain_when_enabled(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "p2p").mkdir()
    (export_dir / "p2p" / "compute-input").write_bytes(b"payload")
    bridge = _fake_solana_bridge(tmp_path / "fake_bridge.cjs")

    task = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "compute:on-chain",
        "status": "queued",
        "required_roles": ["compute"],
        "p2p_ref": {"protocol": "ipfs", "content_id": "compute-input"},
        "task": {"kind": "compute"},
        "on_chain": {
            "job": "11111111111111111111111111111111",
            "fragment_index": 0,
            "worker_token": "11111111111111111111111111111111",
            "skip_claim": True,
        },
    }
    _write_jsonl(export_dir / "tasks.compute.queue.ndjson", task)

    code = network_node.main(
        [
            "--export-dir",
            str(export_dir),
            "--roles",
            "compute",
            "--node-id",
            "node-a",
            "--once",
            "--solana-enable",
            "--solana-wallet",
            str(tmp_path / "wallet.json"),
            "--solana-bridge",
            str(bridge),
        ]
    )
    assert code == 0

    result = json.loads((export_dir / f"result.{_path_id('compute:on-chain')}.json").read_text(encoding="utf-8"))
    assert result["on_chain"][0]["op"] == "submit_fragment_result"
    assert result["on_chain"][0]["params"]["fragment_index"] == 0
    assert result["on_chain"][0]["params"]["result_hash"] == result["result_hash"]


def test_network_node_votes_on_audit_request_when_enabled(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    bridge = _fake_solana_bridge(tmp_path / "fake_bridge.cjs")

    request = {
        "schema_version": 1,
        "envelope_kind": "request",
        "request_id": "audit:on-chain",
        "kind": "audit",
        "status": "queued",
        "priority": "urgent",
        "target_roles": ["audit", "verify"],
        "request": {"choice": True},
        "on_chain": {
            "job": "11111111111111111111111111111111",
            "fragment": "11111111111111111111111111111111",
            "escrow": "11111111111111111111111111111111",
            "worker_token": "11111111111111111111111111111111",
        },
    }
    _write_jsonl(export_dir / "requests.urgent.ndjson", request)

    code = network_node.main(
        [
            "--export-dir",
            str(export_dir),
            "--roles",
            "audit,verify",
            "--node-id",
            "node-a",
            "--once",
            "--solana-enable",
            "--solana-wallet",
            str(tmp_path / "wallet.json"),
            "--solana-bridge",
            str(bridge),
        ]
    )
    assert code == 0

    result = json.loads((export_dir / f"result.{_path_id('audit:on-chain')}.json").read_text(encoding="utf-8"))
    assert result["on_chain"][0]["op"] == "vote_fragment"
    assert result["on_chain"][0]["params"]["choice"] is True


def test_network_node_verifies_expected_hash(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "p2p").mkdir()
    payload = b"verified-payload"
    digest = network_node.sha256_bytes(payload)
    (export_dir / "p2p" / "verifycid").write_bytes(payload)

    task = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "verify:1",
        "status": "queued",
        "required_roles": ["verify"],
        "p2p_ref": {"protocol": "ipfs", "content_id": "verifycid"},
        "task": {"kind": "verify", "expected_hash": "sha256:" + digest},
    }
    _write_jsonl(export_dir / "tasks.verify.queue.ndjson", task)

    code = network_node.main(["--export-dir", str(export_dir), "--roles", "verify", "--node-id", "node-a", "--once"])
    assert code == 0

    result = json.loads((export_dir / f"result.{_path_id('verify:1')}.json").read_text(encoding="utf-8"))
    assert result["role_result"] == "verify"
    assert result["verified"] is True
    assert result["choice"] is True


def test_network_node_retries_then_dead_letters_failures(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    task = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "storage:missing",
        "status": "queued",
        "required_roles": ["storage"],
        "p2p_ref": {"protocol": "file", "content_id": str(tmp_path / "missing.bin")},
        "task": {"kind": "storage"},
    }
    _write_jsonl(export_dir / "tasks.storage.queue.ndjson", task)

    code = network_node.main(
        [
            "--export-dir",
            str(export_dir),
            "--roles",
            "storage",
            "--node-id",
            "node-a",
            "--once",
            "--max-retries",
            "0",
        ]
    )
    assert code == 0

    result = json.loads((export_dir / f"result.{_path_id('storage:missing')}.json").read_text(encoding="utf-8"))
    assert result["success"] is False
    assert (export_dir / "dead_letters.ndjson").exists()
    metrics = json.loads((export_dir / "node.node-a.metrics.json").read_text(encoding="utf-8"))
    assert metrics["dead_lettered"] == 1


def test_peer_network_gossips_and_serves_p2p_content(tmp_path: Path) -> None:
    export_a = tmp_path / "a"
    export_b = tmp_path / "b"
    config_a = _config(export_a, "node-a")
    peer_a = network_node.PeerNetwork(config_a, export_a)
    p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
    peer_a.start()
    try:
        config_b = _config(export_b, "node-b", seed_peers=[f"127.0.0.1:{config_a.gossip_port}"])
        peer_b = network_node.PeerNetwork(config_b, export_b)
        p2p_b = network_node.P2PClient(config_b.p2p_gateway, export_b, peer_b)
        peer_b.start()
        try:
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if peer_b.peers_snapshot()["count"] >= 2:
                    break
                time.sleep(0.05)

            stored = p2p_a.put_local(b"hello-peers")
            shared_ref = stored["shared_ref"]
            data, meta = p2p_b.fetch(shared_ref)
            assert data == b"hello-peers"
            assert meta["source"] == "silicium-peer"
            assert meta["peer_id"] == "node-a"

            peer_a.publish("fragment_result", {"result_hash": "sha256:test", "proof_ref": shared_ref})
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if (export_b / "gossip.events.ndjson").exists():
                    lines = (export_b / "gossip.events.ndjson").read_text(encoding="utf-8").splitlines()
                    if any('"topic":"fragment_result"' in line for line in lines):
                        break
                time.sleep(0.05)
            assert (export_b / "gossip.events.ndjson").exists()
            assert '"topic":"fragment_result"' in (export_b / "gossip.events.ndjson").read_text(encoding="utf-8")
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_peer_network_syncs_over_http_with_public_identity(tmp_path: Path) -> None:
    export_a = tmp_path / "a"
    export_b = tmp_path / "b"
    config_a = _config(export_a, "node-a", gossip_enable=False)
    peer_a = network_node.PeerNetwork(config_a, export_a)
    p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
    peer_a.start()
    try:
        unauthorized = urllib.request.Request(peer_a.http_base_url + "/peers")
        try:
            urllib.request.urlopen(unauthorized, timeout=2)
            raise AssertionError("expected mesh auth failure")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403

        config_b = _config(
            export_b,
            "node-b",
            gossip_enable=False,
            seed_peers=[peer_a.http_base_url],
            peer_sync_interval_s=1,
        )
        peer_b = network_node.PeerNetwork(config_b, export_b)
        p2p_b = network_node.P2PClient(config_b.p2p_gateway, export_b, peer_b)
        peer_b.start()
        try:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                peer_b.sync_once()
                if peer_b.peers_snapshot()["count"] >= 2 and peer_a.peers_snapshot()["count"] >= 2:
                    break
                time.sleep(0.05)
            assert peer_b.peers_snapshot()["count"] >= 2
            assert peer_a.peers_snapshot()["count"] >= 2

            stored = p2p_a.put_local(b"hello-http-mesh")
            data, meta = p2p_b.fetch(stored["shared_ref"])
            assert data == b"hello-http-mesh"
            assert meta["source"] == "silicium-peer"

            peer_a.publish("fragment_result", {"result_hash": "sha256:http", "proof_ref": stored["shared_ref"]})
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if (export_b / "gossip.events.ndjson").exists():
                    lines = (export_b / "gossip.events.ndjson").read_text(encoding="utf-8").splitlines()
                    if any('"topic":"fragment_result"' in line for line in lines):
                        break
                time.sleep(0.05)
            assert (export_b / "gossip.events.ndjson").exists()
            assert '"topic":"fragment_result"' in (export_b / "gossip.events.ndjson").read_text(encoding="utf-8")
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_peer_network_discovers_server_observed_candidate_over_http(tmp_path: Path) -> None:
    export_a = tmp_path / "a"
    export_b = tmp_path / "b"
    config_a = _config(export_a, "node-a", gossip_enable=False)
    peer_a = network_node.PeerNetwork(config_a, export_a)
    peer_a.start()
    try:
        config_b = _config(
            export_b,
            "node-b",
            gossip_enable=False,
            seed_peers=[peer_a.http_base_url],
            p2p_candidate_ttl_s=30,
            p2p_candidate_refresh_s=1,
        )
        config_b.gossip_port = 46102
        peer_b = network_node.PeerNetwork(config_b, export_b)
        peer_b.start()
        try:
            candidates = peer_b.refresh_candidates(force=True)
            observed = [candidate for candidate in candidates if candidate["candidate_type"] == "srflx"]
            assert observed
            assert observed[0]["source"].startswith("observe:")
            assert observed[0]["ip"] == "127.0.0.1"
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_p2p_signaling_creates_authorized_session_with_candidate_pairs(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    peer_a_export = tmp_path / "peer-a"
    peer_b_export = tmp_path / "peer-b"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a_config = _config(peer_a_export, "node-a", gossip_enable=False)
    peer_b_config = _config(peer_b_export, "node-b", gossip_enable=False)
    peer_a_config.gossip_port = 46111
    peer_b_config.gossip_port = 46112
    peer_a = network_node.PeerNetwork(peer_a_config, peer_a_export)
    peer_b = network_node.PeerNetwork(peer_b_config, peer_b_export)
    task_dir = signal_export / "tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "compute_42.json").write_text(
        json.dumps({"task_id": "compute_42", "requester_peer_id": "node-a", "dispatched_to": "node-b"}),
        encoding="utf-8",
    )

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]

        status, body = _signed_json_request_status(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "task_id": "compute_42", "purpose": "fragment_fetch"},
        )
        assert status == 201
        session = body["session"]
        assert session["status"] == "signaling"
        assert session["initiator_peer_id"] == "node-a"
        assert session["target_peer_id"] == "node-b"
        assert session["candidate_pairs"]
        assert session["candidate_pairs"][0]["local_candidate"]["peer_id"] == "node-a"
        assert session["candidate_pairs"][0]["remote_candidate"]["peer_id"] == "node-b"

        session_id = session["session_id"]
        ready_a = _signed_json_request(peer_a, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert ready_a["session"]["status"] == "ready_wait"
        ready_b = _signed_json_request(peer_b, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert ready_b["session"]["status"] == "punching"
        assert ready_b["punch_start"]["candidate_pairs"]
        result = _signed_json_request(
            peer_a,
            signal.http_base_url,
            f"/p2p/sessions/{session_id}/result",
            {
                "ok": True,
                "transport": "direct",
                "selected_local_candidate_id": session["candidate_pairs"][0]["local_candidate_id"],
                "selected_remote_candidate_id": session["candidate_pairs"][0]["remote_candidate_id"],
            },
        )
        assert result["session"]["status"] == "direct"
        assert result["session"]["results"][0]["ok"] is True
        assert (signal_export / "p2p.sessions.ndjson").exists()
    finally:
        signal.stop()


def test_p2p_signaling_rejects_unauthorized_pairing(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a = network_node.PeerNetwork(_config(tmp_path / "peer-a", "node-a", gossip_enable=False), tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(_config(tmp_path / "peer-b", "node-b", gossip_enable=False), tmp_path / "peer-b")
    task_dir = signal_export / "tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "compute_42.json").write_text(
        json.dumps({"task_id": "compute_42", "requester_peer_id": "node-a", "dispatched_to": "node-c"}),
        encoding="utf-8",
    )

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]
        status, body = _signed_json_request_status(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "task_id": "compute_42", "purpose": "fragment_fetch"},
        )
        assert status == 403
        assert body["error"] == "task_peer_pair_unauthorized"
    finally:
        signal.stop()


def test_p2p_signaling_expires_stale_session(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False, p2p_session_ttl_s=1), signal_export)
    peer_a_config = _config(tmp_path / "peer-a", "node-a", gossip_enable=False)
    peer_b_config = _config(tmp_path / "peer-b", "node-b", gossip_enable=False)
    peer_a_config.gossip_port = 46121
    peer_b_config.gossip_port = 46122
    peer_a = network_node.PeerNetwork(peer_a_config, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(peer_b_config, tmp_path / "peer-b")

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]
        created = _signed_json_request(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "purpose": "nat_punch"},
        )
        session_id = created["session"]["session_id"]
        time.sleep(1.2)
        status, body = _signed_json_request_status(peer_a, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert status == 404
        assert body["error"] == "session_not_found"
        assert signal.sessions_snapshot()["count"] == 0
    finally:
        signal.stop()


def test_p2p_signaling_closes_session_on_peer_disconnect(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a_config = _config(tmp_path / "peer-a", "node-a", gossip_enable=False)
    peer_b_config = _config(tmp_path / "peer-b", "node-b", gossip_enable=False)
    peer_a_config.gossip_port = 46131
    peer_b_config.gossip_port = 46132
    peer_a = network_node.PeerNetwork(peer_a_config, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(peer_b_config, tmp_path / "peer-b")

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]
        created = _signed_json_request(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "purpose": "nat_punch"},
        )
        session_id = created["session"]["session_id"]
        closed = _signed_json_request(peer_b, signal.http_base_url, f"/p2p/sessions/{session_id}/close", {"reason": "peer_disconnect"})
        assert closed["session"]["status"] == "closed"
        status, body = _signed_json_request_status(peer_a, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert status == 409
        assert body["error"] == "session_closed"
    finally:
        signal.stop()


def test_udp_hole_punch_establishes_direct_session_between_local_nodes(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_b = _config(tmp_path / "peer-b", "node-b", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_a.gossip_advertise_host = "127.0.0.1"
    config_b.gossip_advertise_host = "127.0.0.1"
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(config_b, tmp_path / "peer-b")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    peer_b.start()
    try:
        punch_start = _signed_punch_start(signal, peer_a, peer_b)
        results: dict[str, dict] = {}
        thread_a = threading.Thread(target=lambda: results.setdefault("a", peer_a.establish_direct_udp_session(punch_start)))
        thread_b = threading.Thread(target=lambda: results.setdefault("b", peer_b.establish_direct_udp_session(punch_start)))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=3)
        thread_b.join(timeout=3)

        assert results["a"]["status"] == "direct"
        assert results["b"]["status"] == "direct"
        assert results["a"]["transport_backend"] == "native-light"
        assert results["b"]["transport_backend"] == "native-light"
        assert results["a"]["rtt_ms"] >= 0
        assert results["a"]["selected_candidate_pair"]["local_candidate_id"]
        assert (tmp_path / "peer-a" / "p2p.direct_sessions.json").exists()
    finally:
        peer_b.stop()
        peer_a.stop()


def test_udp_hole_punch_rejects_wrong_session_id(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_retry_count=2, p2p_punch_interval_ms=10, p2p_session_timeout_ms=120)
    config_b = _config(tmp_path / "peer-b", "node-b", gossip_enable=True, nat_punch_enable=True)
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(config_b, tmp_path / "peer-b")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    peer_b.start()
    try:
        punch_start = _signed_punch_start(signal, peer_a, peer_b, session_id="p2p-sess-a")
        wrong_probe = {
            "message_type": "punch_probe",
            "session_id": "p2p-sess-wrong",
            "peer_id": "node-b",
            "target_peer_id": "node-a",
            "candidate_id": "cand-b",
            "nonce": "probe-wrong",
            "timestamp_unix": int(time.time()),
        }
        peer_b._sign_message(wrong_probe)
        peer_a._handle_network_message(wrong_probe, f"127.0.0.1:{config_b.gossip_port}")

        result = peer_a.establish_direct_udp_session(punch_start)
        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"
    finally:
        peer_b.stop()
        peer_a.stop()


def test_direct_transport_backend_rejects_unknown_backend(tmp_path: Path) -> None:
    config = _config(
        tmp_path / "peer",
        "node-a",
        gossip_enable=False,
        p2p_direct_transport_backend="custom-ice",
    )

    try:
        network_node.PeerNetwork(config, tmp_path / "peer")
        raise AssertionError("expected unsupported direct transport backend")
    except ValueError as exc:
        assert str(exc) == "unsupported_direct_transport_backend:custom-ice"


def test_direct_transport_auto_selects_ice_when_dependency_is_available(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(network_node.importlib.util, "find_spec", lambda name: object() if name == "aioice" else None)
    peer = network_node.PeerNetwork(
        _config(tmp_path / "auto-ice", "node-auto", gossip_enable=False, p2p_direct_transport_backend="auto"),
        tmp_path / "auto-ice",
    )
    assert peer.direct_transport.name == "ice"


def test_ice_direct_transport_builds_ready_payload_and_features(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(direct_transport.importlib, "import_module", lambda name: _fake_aioice_module() if name == "aioice" else None)
    config = _config(
        tmp_path / "peer",
        "node-a",
        gossip_enable=False,
        nat_punch_enable=True,
        p2p_direct_transport_backend="ice",
        p2p_stun_server="stun.example.test:3478",
        p2p_turn_server="turn.example.test:3478",
        p2p_turn_username="turn-user",
        p2p_turn_password="turn-pass",
        p2p_turn_transport="tcp",
    )
    peer = network_node.PeerNetwork(config, tmp_path / "peer")

    diagnostics = peer.candidate_diagnostics()
    ready = peer.build_session_ready_payload({"session_id": "ice-sess", "initiator_peer_id": "node-a", "target_peer_id": "node-b"})

    assert peer.direct_transport.name == "ice"
    assert "ice_v1" in diagnostics["direct_transport_features"]
    assert "stun_v1" in diagnostics["direct_transport_features"]
    assert "turn_v1" in diagnostics["direct_transport_features"]
    assert ready["direct_transport_backend"] == "ice"
    assert ready["ice"]["supported"] is True
    assert ready["ice"]["ufrag"] == "ufrag-controlling"
    assert ready["ice"]["candidates"][0]["ice_sdp"]
    assert ready["ice"]["turn_server"] == "turn.example.test:3478"
    assert "turn-pass" not in json.dumps(ready)


def test_ice_signaling_embeds_ready_candidates_in_punch_start(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(direct_transport.importlib, "import_module", lambda name: _fake_aioice_module() if name == "aioice" else None)
    signal_export = tmp_path / "signal"
    peer_a_export = tmp_path / "ice-a"
    peer_b_export = tmp_path / "ice-b"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a = network_node.PeerNetwork(
        _config(peer_a_export, "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        peer_a_export,
    )
    peer_b = network_node.PeerNetwork(
        _config(peer_b_export, "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        peer_b_export,
    )

    signal._record_peer(_peer_registration_payload(peer_a))
    signal._record_peer(_peer_registration_payload(peer_b))
    status, body = signal.create_signaling_session(
        {"peer_id": "node-a", "target_peer_id": "node-b", "purpose": "nat_punch", "allowed_transports": ["ice"]},
        "node-a",
    )
    assert status == 201
    session = body["session"]
    ready_a = peer_a.build_session_ready_payload(session)
    ready_b = peer_b.build_session_ready_payload(session)

    first_status, first_body = signal.mark_session_ready(session["session_id"], "node-a", ready_a)
    second_status, second_body = signal.mark_session_ready(session["session_id"], "node-b", ready_b)

    assert first_status == 200
    assert first_body["session"]["status"] == "ready_wait"
    assert second_status == 200
    assert second_body["session"]["status"] == "punching"
    punch_start = second_body["punch_start"]
    assert punch_start["ice"]["peers"]["node-a"]["candidates"][0]["ice_sdp"]
    assert punch_start["ice"]["peers"]["node-b"]["ufrag"] == "ufrag-controlled"


def test_ice_backend_establishes_session_through_aioice_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(direct_transport.importlib, "import_module", lambda name: _fake_aioice_module() if name == "aioice" else None)
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a = network_node.PeerNetwork(
        _config(tmp_path / "ice-a", "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "ice-a",
    )
    peer_b = network_node.PeerNetwork(
        _config(tmp_path / "ice-b", "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "ice-b",
    )
    session = {
        "session_id": "ice-sess-direct",
        "initiator_peer_id": "node-a",
        "target_peer_id": "node-b",
        "candidate_pairs": [],
    }
    ready_a = peer_a.build_session_ready_payload(session)
    ready_b = peer_b.build_session_ready_payload(session)
    punch_start = signal._punch_start_message({**session, "ready_transports": {"node-a": ready_a, "node-b": ready_b}})

    result_a = peer_a.establish_direct_udp_session(punch_start)
    result_b = peer_b.establish_direct_udp_session(punch_start)

    assert result_a["status"] == "direct"
    assert result_b["status"] == "direct"
    assert result_a["transport_backend"] == "ice"
    assert result_b["transport_backend"] == "ice"
    assert result_a["selected_candidate_pair"]["remote_candidate_id"]
    assert (tmp_path / "ice-a" / "p2p.direct_sessions.json").exists()


def test_ice_backend_establishes_real_loopback_session_when_installed(tmp_path: Path) -> None:
    pytest.importorskip("aioice")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a = network_node.PeerNetwork(
        _config(tmp_path / "real-ice-a", "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "real-ice-a",
    )
    peer_b = network_node.PeerNetwork(
        _config(tmp_path / "real-ice-b", "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "real-ice-b",
    )
    session = {
        "session_id": "real-ice-loopback",
        "initiator_peer_id": "node-a",
        "target_peer_id": "node-b",
        "candidate_pairs": [],
    }
    try:
        ready_a = peer_a.build_session_ready_payload(session)
        ready_b = peer_b.build_session_ready_payload(session)
        punch_start = signal._punch_start_message({**session, "ready_transports": {"node-a": ready_a, "node-b": ready_b}})
        results: dict[str, dict] = {}
        thread_a = threading.Thread(target=lambda: results.setdefault("a", peer_a.establish_direct_udp_session(punch_start)))
        thread_b = threading.Thread(target=lambda: results.setdefault("b", peer_b.establish_direct_udp_session(punch_start)))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)
        assert results["a"]["status"] == "direct"
        assert results["b"]["status"] == "direct"
        assert results["a"]["transport_backend"] == "ice"
        assert results["b"]["transport_backend"] == "ice"
    finally:
        peer_a.direct_transport.close()
        peer_b.direct_transport.close()


def test_ice_data_plane_fetches_content_without_http_payload(tmp_path: Path) -> None:
    pytest.importorskip("aioice")
    export_a = tmp_path / "data-a"
    export_b = tmp_path / "data-b"
    peer_a = network_node.PeerNetwork(
        _config(export_a, "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        export_a,
    )
    peer_b = network_node.PeerNetwork(
        _config(export_b, "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        export_b,
    )
    peer_a.start()
    peer_b.start()
    try:
        peer_a._record_peer(_peer_registration_payload(peer_b))
        peer_b._record_peer(_peer_registration_payload(peer_a))
        expected_data = b"ice-data-plane-" * 5000
        stored = network_node.P2PClient(peer_b.config.p2p_gateway, export_b, peer_b).put_local(expected_data)
        peer_a._fetch_direct_from_peer = lambda _peer, _content_id: None
        result = network_node.P2PClient(peer_a.config.p2p_gateway, export_a, peer_a).fetch(stored["shared_ref"])
        assert result[0] == expected_data
        assert result[1]["source"] == "silicium-ice"
        assert result[1]["transport_backend"] == "ice"
    finally:
        peer_a.stop()
        peer_b.stop()


def test_ice_backend_reports_missing_optional_dependency(tmp_path: Path, monkeypatch) -> None:
    def _missing_aioice(name: str) -> object:
        if name == "aioice":
            raise ModuleNotFoundError("aioice")
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(direct_transport.importlib, "import_module", _missing_aioice)
    peer = network_node.PeerNetwork(
        _config(tmp_path / "ice-missing", "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "ice-missing",
    )

    ready = peer.build_session_ready_payload({"session_id": "ice-sess", "initiator_peer_id": "node-a", "target_peer_id": "node-b"})

    assert ready["direct_transport_backend"] == "ice"
    assert ready["ice"]["supported"] is False
    assert ready["ice"]["error"] == "aioice_missing"


def test_udp_hole_punch_rejects_wrong_peer_id(tmp_path: Path) -> None:
    peer_a = network_node.PeerNetwork(
        _config(tmp_path / "peer-a", "node-a", gossip_enable=False, nat_punch_enable=True),
        tmp_path / "peer-a",
    )
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    punch_start = {
        "message_type": "punch_start",
        "session_id": "p2p-sess-wrong-peer",
        "peer_id": "node-signal",
        "identity_id": signal.identity.identity_id,
        "public_key": signal.identity.public_key_b64,
        "initiator_peer_id": "node-x",
        "target_peer_id": "node-y",
        "candidate_pairs": [],
        "timestamp_unix": int(time.time()),
        "nonce": "punch-start-wrong-peer",
    }
    signal._sign_message(punch_start)

    result = peer_a.establish_direct_udp_session(punch_start)
    assert result["status"] == "failed"
    assert result["failure_reason"] == "wrong_peer_id"


def test_udp_hole_punch_times_out_with_unreachable_candidate(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_retry_count=2, p2p_punch_interval_ms=10, p2p_session_timeout_ms=120)
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    try:
        now = int(time.time())
        local = next(candidate for candidate in peer_a.refresh_candidates(force=True) if candidate["address_family"] == "ipv4")
        remote = {
            "candidate_id": "cand-node-b-unreachable",
            "peer_id": "node-b",
            "address_family": "ipv4",
            "transport": "udp",
            "ip": "127.0.0.1",
            "port": 9,
            "candidate_type": "host",
            "priority": 100,
            "observed_unix": now,
            "expires_unix": now + 30,
            "source": "test",
        }
        punch_start = signal._punch_start_message(
            {
                "session_id": "p2p-sess-timeout",
                "initiator_peer_id": "node-a",
                "target_peer_id": "node-b",
                "candidate_pairs": [
                    {
                        "local_candidate_id": local["candidate_id"],
                        "remote_candidate_id": remote["candidate_id"],
                        "transport": "udp",
                        "address_family": "ipv4",
                        "priority": 100,
                        "local_candidate": local,
                        "remote_candidate": remote,
                    }
                ],
            }
        )

        result = peer_a.establish_direct_udp_session(punch_start)
        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"
    finally:
        peer_a.stop()


def test_udp_hole_punch_ignores_duplicate_acks(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_b = _config(tmp_path / "peer-b", "node-b", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_a.gossip_advertise_host = "127.0.0.1"
    config_b.gossip_advertise_host = "127.0.0.1"
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(config_b, tmp_path / "peer-b")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    peer_b.start()
    try:
        punch_start = _signed_punch_start(signal, peer_a, peer_b, session_id="p2p-sess-dup")
        results: dict[str, dict] = {}
        thread_a = threading.Thread(target=lambda: results.setdefault("a", peer_a.establish_direct_udp_session(punch_start)))
        thread_b = threading.Thread(target=lambda: results.setdefault("b", peer_b.establish_direct_udp_session(punch_start)))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=3)
        thread_b.join(timeout=3)
        assert results["a"]["status"] == "direct"

        session = peer_a._direct_sessions["p2p-sess-dup"]
        sent_probe_nonce = next(iter(session["sent_probes"].keys()))
        ack = {
            "message_type": "punch_ack",
            "session_id": "p2p-sess-dup",
            "peer_id": "node-b",
            "target_peer_id": "node-a",
            "probe_nonce": sent_probe_nonce,
            "selected_remote_candidate_id": session["selected_candidate_pair"]["local_candidate_id"],
            "selected_local_candidate_id": session["selected_candidate_pair"]["remote_candidate_id"],
            "nonce": session["seen_ack_nonces"][0],
            "timestamp_unix": int(time.time()),
        }
        peer_b._sign_message(ack)
        before = list(peer_a._direct_sessions["p2p-sess-dup"]["seen_ack_nonces"])
        peer_a._handle_network_message(ack, f"127.0.0.1:{config_b.gossip_port}")
        after = list(peer_a._direct_sessions["p2p-sess-dup"]["seen_ack_nonces"])
        assert after == before
    finally:
        peer_b.stop()
        peer_a.stop()


def test_peer_network_relay_fetches_unreachable_peer_content(tmp_path: Path) -> None:
    export_a = tmp_path / "relay-a"
    export_b = tmp_path / "relay-b"
    export_c = tmp_path / "relay-c"
    config_a = _config(export_a, "node-a", gossip_enable=False)
    peer_a = network_node.PeerNetwork(config_a, export_a)
    p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
    peer_a.start()
    try:
        config_c = _config(export_c, "node-c", gossip_enable=False, relay_enable=True, seed_peers=[peer_a.http_base_url], peer_sync_interval_s=1)
        peer_c = network_node.PeerNetwork(config_c, export_c)
        peer_c.start()
        try:
            config_b = _config(export_b, "node-b", gossip_enable=False, relay_enable=True, seed_peers=[peer_c.http_base_url], peer_sync_interval_s=1)
            peer_b = network_node.PeerNetwork(config_b, export_b)
            p2p_b = network_node.P2PClient(config_b.p2p_gateway, export_b, peer_b)
            peer_b.start()
            try:
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    peer_b.sync_once()
                    peer_c.sync_once()
                    if peer_b.peers_snapshot()["count"] >= 3:
                        break
                    time.sleep(0.05)
                assert peer_b.peers_snapshot()["count"] >= 3

                stored = p2p_a.put_local(b"relay-path")
                content_id = str(stored["shared_ref"]["content_id"])
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    target_peer = peer_c._peers.get("node-a", {})
                    if peer_c._fetch_direct_from_peer(target_peer, content_id) == b"relay-path":
                        break
                    peer_c.sync_once()
                    time.sleep(0.05)
                peer_b._peers["node-a"]["http_base_url"] = "http://127.0.0.1:9"
                data, meta = p2p_b.fetch(stored["shared_ref"])
                assert data == b"relay-path"
                assert meta["relayed_via"] == "node-c"
            finally:
                peer_b.stop()
        finally:
            peer_c.stop()
    finally:
        peer_a.stop()


def test_storage_replication_meets_quorum(tmp_path: Path) -> None:
    export_a = tmp_path / "replica-a"
    export_b = tmp_path / "replica-b"
    export_c = tmp_path / "replica-c"
    config_b = _config(export_b, "node-b", gossip_enable=False, roles="storage", reputation_score=2.0)
    config_c = _config(export_c, "node-c", gossip_enable=False, roles="storage", reputation_score=1.0)
    peer_b = network_node.PeerNetwork(config_b, export_b)
    peer_c = network_node.PeerNetwork(config_c, export_c)
    peer_b.start()
    peer_c.start()
    try:
        config_a = _config(
            export_a,
            "node-a",
            gossip_enable=False,
            roles="storage",
            seed_peers=[peer_b.http_base_url, peer_c.http_base_url],
            peer_sync_interval_s=1,
            replication_factor=2,
            replication_quorum=2,
        )
        peer_a = network_node.PeerNetwork(config_a, export_a)
        p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
        peer_a.start()
        try:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                peer_a.sync_once()
                if peer_a.peers_snapshot()["count"] >= 3:
                    break
                time.sleep(0.05)
            stored = p2p_a.put_local(b"replicated-bytes", replication_factor=2, replication_quorum=2, replication_roles={"storage"})
            digest = stored["shared_ref"]["content_id"]
            assert stored["replication"]["satisfied"] is True
            assert stored["replication"]["stored"] == 2
            assert (export_b / "p2p" / digest).exists()
            assert (export_c / "p2p" / digest).exists()
        finally:
            peer_a.stop()
    finally:
        peer_b.stop()
        peer_c.stop()


def test_peer_network_discovers_peers_via_public_seed_registry(tmp_path: Path) -> None:
    export_seed = tmp_path / "seed"
    export_b = tmp_path / "discover-b"
    export_c = tmp_path / "discover-c"
    seed = network_node.PeerNetwork(_config(export_seed, "seed-node", gossip_enable=False), export_seed)
    seed.start()
    try:
        peer_b = network_node.PeerNetwork(
            _config(export_b, "node-b", gossip_enable=False, discovery_seeds=[seed.http_base_url], peer_sync_interval_s=1),
            export_b,
        )
        peer_c = network_node.PeerNetwork(
            _config(export_c, "node-c", gossip_enable=False, discovery_seeds=[seed.http_base_url], peer_sync_interval_s=1),
            export_c,
        )
        peer_b.start()
        peer_c.start()
        try:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                peer_b.sync_once()
                peer_c.sync_once()
                if peer_b.peers_snapshot()["count"] >= 3 and peer_c.peers_snapshot()["count"] >= 3:
                    break
                time.sleep(0.05)
            assert peer_b.peers_snapshot()["count"] >= 3
            assert peer_c.peers_snapshot()["count"] >= 3
        finally:
            peer_b.stop()
            peer_c.stop()
    finally:
        seed.stop()


def test_network_node_dispatches_task_to_remote_peer(tmp_path: Path) -> None:
    export_a = tmp_path / "dispatch-a"
    export_b = tmp_path / "dispatch-b"
    export_a.mkdir()
    export_b.mkdir()
    peer_b = network_node.PeerNetwork(_config(export_b, "node-b", gossip_enable=False, roles="compute"), export_b)
    peer_b.start()
    try:
        task = {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "compute:remote",
            "status": "queued",
            "required_roles": ["compute"],
            "task": {"kind": "compute"},
        }
        _write_jsonl(export_a / "tasks.queue.ndjson", task)
        code = network_node.main(
            [
                "--export-dir",
                str(export_a),
                "--roles",
                "storage",
                "--node-id",
                "node-a",
                "--once",
                "--remote-dispatch-enable",
                "--seed-peers",
                peer_b.http_base_url,
            ]
        )
        assert code == 0
        dispatched = json.loads((export_a / "tasks" / f"{_path_id('compute:remote')}.json").read_text(encoding="utf-8"))
        assert dispatched["status"] == "dispatched"
        remote_task = json.loads((export_b / "tasks" / f"{_path_id('compute:remote')}.json").read_text(encoding="utf-8"))
        assert remote_task["task_id"] == "compute:remote"
        metrics = json.loads((export_a / "node.node-a.metrics.json").read_text(encoding="utf-8"))
        assert metrics["dispatched"] == 1
    finally:
        peer_b.stop()


def test_network_node_ingests_remote_result_back_to_origin(tmp_path: Path) -> None:
    export_a = tmp_path / "dispatch-return-a"
    export_b = tmp_path / "dispatch-return-b"
    config_a = _config(export_a, "node-a", roles="storage", gossip_enable=False, remote_dispatch_enable=True)
    node_a = network_node.NetworkNode(config_a)
    node_b = network_node.NetworkNode(_config(export_b, "node-b", roles="compute", gossip_enable=False))
    node_b.peer_network.start()
    node_a.peer_network.start()
    try:
        node_a.write_heartbeat()
        node_b.write_heartbeat()
        node_a.peer_network.update_peer_metadata(
            "node-b",
            {
                "node_id": "node-b",
                "roles": ["compute"],
                "http_base_url": node_b.peer_network.http_base_url,
                "mesh_post_url": node_b.peer_network.mesh_post_url,
                "gossip_bind": "127.0.0.1",
                "gossip_port": 0,
                "relay_capable": True,
                "capacity": node_b.runtime.capacity(),
                "reputation_score": 0.0,
            },
        )
        task = {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "compute:return",
            "status": "queued",
            "required_roles": ["compute"],
            "task": {"kind": "compute"},
        }
        _write_jsonl(export_a / "tasks.queue.ndjson", task)
        handled_a = node_a.sweep()
        assert handled_a == 1
        dispatched = json.loads((export_a / "tasks" / f"{_path_id('compute:return')}.json").read_text(encoding="utf-8"))
        assert dispatched["status"] == "dispatched"
        handled_b = node_b.sweep()
        assert handled_b == 1
        result = json.loads((export_a / f"result.{_path_id('compute:return')}.json").read_text(encoding="utf-8"))
        assert result["node_id"] == "node-b"
        origin_task = json.loads((export_a / "tasks" / f"{_path_id('compute:return')}.json").read_text(encoding="utf-8"))
        assert origin_task["status"] == "completed"
        assert origin_task["handled_by"] == "node-b"
    finally:
        node_a.peer_network.stop()
        node_b.peer_network.stop()


def test_network_node_persists_reputation_updates(tmp_path: Path) -> None:
    export_dir = tmp_path / "rep-score"
    export_dir.mkdir()
    (export_dir / "p2p").mkdir()
    (export_dir / "p2p" / "compute-input").write_bytes(b"payload")
    task = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "compute:rep",
        "status": "queued",
        "required_roles": ["compute"],
        "p2p_ref": {"protocol": "ipfs", "content_id": "compute-input"},
        "task": {"kind": "compute"},
    }
    _write_jsonl(export_dir / "tasks.compute.queue.ndjson", task)
    code = network_node.main(["--export-dir", str(export_dir), "--roles", "compute", "--node-id", "node-a", "--once"])
    assert code == 0
    reputation = json.loads((export_dir / "node.node-a.reputation.json").read_text(encoding="utf-8"))
    assert reputation["local_score"] > 0
    heartbeat = json.loads((export_dir / "node.node-a.heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["reputation_score"] == reputation["local_score"]


def test_scheduler_prefers_verified_onchain_reputation(tmp_path: Path) -> None:
    export_dir = tmp_path / "sched"
    export_dir.mkdir()
    bridge = _fake_solana_bridge(tmp_path / "fake_bridge.cjs")
    wallet_path = tmp_path / "wallet.json"
    wallet_path.write_text(json.dumps([0] * 64), encoding="utf-8")
    config = _config(
        export_dir,
        "node-a",
        roles="storage",
        solana_enable=True,
        solana_bridge=bridge,
        solana_wallet=str(wallet_path),
        solana_reputation_enable=True,
    )
    node = network_node.NetworkNode(config)
    node.peer_network.update_peer_metadata(
        "peer-low-offchain-high-onchain",
        {
            "node_id": "peer-low-offchain-high-onchain",
            "roles": ["storage"],
            "capacity": {"cpu_count": 1, "disk_free_bytes": 1},
            "reputation_score": 10.0,
            "solana_owner": "ownerB",
        },
    )
    node.peer_network.update_peer_metadata(
        "peer-high-offchain-low-onchain",
        {
            "node_id": "peer-high-offchain-low-onchain",
            "roles": ["storage"],
            "capacity": {"cpu_count": 8, "disk_free_bytes": 999999999},
            "reputation_score": 1000.0,
            "solana_owner": "ownerA",
        },
    )
    node.refresh_known_peer_onchain_reputations()
    selected = node.peer_network.select_peers(required_roles={"storage"}, limit=2)
    assert selected[0]["node_id"] == "peer-low-offchain-high-onchain"
    assert selected[0]["onchain_reputation"] == 9000


def test_scheduler_prefers_role_specific_onchain_reputation(tmp_path: Path) -> None:
    export_dir = tmp_path / "sched-role"
    export_dir.mkdir()
    bridge = _fake_solana_bridge(tmp_path / "fake_bridge.cjs")
    wallet_path = tmp_path / "wallet.json"
    wallet_path.write_text(json.dumps([0] * 64), encoding="utf-8")
    config = _config(
        export_dir,
        "node-a",
        roles="verify",
        solana_enable=True,
        solana_bridge=bridge,
        solana_wallet=str(wallet_path),
        solana_reputation_enable=True,
    )
    node = network_node.NetworkNode(config)
    node.peer_network.update_peer_metadata(
        "peer-compute",
        {
            "node_id": "peer-compute",
            "roles": ["verify"],
            "capacity": {"cpu_count": 8, "disk_free_bytes": 999999999},
            "reputation_score": 200.0,
            "solana_owner": "ownerA",
        },
    )
    node.peer_network.update_peer_metadata(
        "peer-verify",
        {
            "node_id": "peer-verify",
            "roles": ["verify"],
            "capacity": {"cpu_count": 1, "disk_free_bytes": 1},
            "reputation_score": 10.0,
            "solana_owner": "ownerB",
        },
    )
    node.refresh_known_peer_onchain_reputations()
    selected = node.peer_network.select_peers(required_roles={"verify"}, limit=2)
    assert selected[0]["node_id"] == "peer-verify"
    assert selected[0]["onchain_verify_reputation"] == 9500


def test_remote_dispatch_filters_peers_with_onchain_thresholds(tmp_path: Path) -> None:
    export_a = tmp_path / "dispatch-threshold-a"
    export_b = tmp_path / "dispatch-threshold-b"
    export_c = tmp_path / "dispatch-threshold-c"
    export_a.mkdir()
    export_b.mkdir()
    export_c.mkdir()
    bridge = _fake_solana_bridge(tmp_path / "fake_bridge.cjs")
    wallet_path = tmp_path / "wallet.json"
    wallet_path.write_text(json.dumps([0] * 64), encoding="utf-8")

    peer_b = network_node.PeerNetwork(_config(export_b, "node-b", gossip_enable=False, roles="compute"), export_b)
    peer_c = network_node.PeerNetwork(_config(export_c, "node-c", gossip_enable=False, roles="compute"), export_c)
    peer_b.set_local_profile(solana_owner="ownerA")
    peer_c.set_local_profile(solana_owner="ownerB")
    peer_b.start()
    peer_c.start()
    try:
        task = {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "compute:threshold",
            "status": "queued",
            "required_roles": ["compute"],
            "task": {"kind": "compute", "required_compute_reputation": 8500},
        }
        _write_jsonl(export_a / "tasks.queue.ndjson", task)
        code = network_node.main(
            [
                "--export-dir",
                str(export_a),
                "--roles",
                "storage",
                "--node-id",
                "node-a",
                "--once",
                "--remote-dispatch-enable",
                "--seed-peers",
                ",".join([peer_b.http_base_url, peer_c.http_base_url]),
                "--solana-enable",
                "--solana-bridge",
                str(bridge),
                "--solana-wallet",
                str(wallet_path),
                "--solana-reputation-enable",
            ]
        )
        assert code == 0
        remote_task = json.loads((export_b / "tasks" / f"{_path_id('compute:threshold')}.json").read_text(encoding="utf-8"))
        assert remote_task["task_id"] == "compute:threshold"
        assert not (export_c / "tasks" / f"{_path_id('compute:threshold')}.json").exists()
    finally:
        peer_b.stop()
        peer_c.stop()
