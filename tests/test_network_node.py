import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from tools import network_node


def _write_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


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

    result = json.loads((export_dir / "result.storage:1.json").read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["required_roles"] == ["storage"]
    assert result["input"]["source"] == "local-p2p-cache"
    assert result["role_result"] == "storage"
    assert result["stored_ref"]["hash"].startswith("sha256:")

    stored = json.loads((export_dir / "tasks" / "storage:1.json").read_text(encoding="utf-8"))
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

    assert (export_dir / "result.audit:now.json").exists()
    assert not (export_dir / "result.compute:late.json").exists()
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

    result = json.loads((export_dir / "result.compute:on-chain.json").read_text(encoding="utf-8"))
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

    result = json.loads((export_dir / "result.audit:on-chain.json").read_text(encoding="utf-8"))
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

    result = json.loads((export_dir / "result.verify:1.json").read_text(encoding="utf-8"))
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

    result = json.loads((export_dir / "result.storage:missing.json").read_text(encoding="utf-8"))
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
        dispatched = json.loads((export_a / "tasks" / "compute:remote.json").read_text(encoding="utf-8"))
        assert dispatched["status"] == "dispatched"
        remote_task = json.loads((export_b / "tasks" / "compute:remote.json").read_text(encoding="utf-8"))
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
        dispatched = json.loads((export_a / "tasks" / "compute:return.json").read_text(encoding="utf-8"))
        assert dispatched["status"] == "dispatched"
        handled_b = node_b.sweep()
        assert handled_b == 1
        result = json.loads((export_a / "result.compute:return.json").read_text(encoding="utf-8"))
        assert result["node_id"] == "node-b"
        origin_task = json.loads((export_a / "tasks" / "compute:return.json").read_text(encoding="utf-8"))
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
        remote_task = json.loads((export_b / "tasks" / "compute:threshold.json").read_text(encoding="utf-8"))
        assert remote_task["task_id"] == "compute:threshold"
        assert not (export_c / "tasks" / "compute:threshold.json").exists()
    finally:
        peer_b.stop()
        peer_c.stop()
