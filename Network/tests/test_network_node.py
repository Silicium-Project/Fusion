import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from tools import network_node


def test_p2p_content_ids_cannot_escape_export_directory(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    assert network_node.p2p_content_path(export_dir, "abc-123_DEF.bin") == export_dir / "p2p" / "abc-123_DEF.bin"
    for unsafe in ("../secret", "..", "folder/file", r"folder\file", "C:secret"):
        try:
            network_node.p2p_content_path(export_dir, unsafe)
        except ValueError as exc:
            assert str(exc) == "invalid_p2p_content_id"
        else:
            raise AssertionError(f"unsafe content id accepted: {unsafe}")


def test_remote_file_references_are_detected() -> None:
    assert network_node.contains_file_reference(
        {"task": {"input": {"protocol": "file", "content_id": "C:/secret.txt"}}}
    )
    assert not network_node.contains_file_reference(
        {"task": {"input": {"protocol": "silicium", "content_id": "abc123"}}}
    )


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
    reputation_score: float = 0.0,
    replication_factor: int = 0,
    replication_quorum: int = 0,
    discovery_seeds: list[str] | None = None,
    remote_dispatch_enable: bool = False,
    remote_dispatch_limit: int = 3,
    nat_punch_enable: bool = False,
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
        reputation_score=reputation_score,
        replication_factor=replication_factor,
        replication_quorum=replication_quorum,
        discovery_seeds=discovery_seeds or [],
        discovery_sync_interval_s=1,
        remote_dispatch_enable=remote_dispatch_enable,
        remote_dispatch_limit=remote_dispatch_limit,
        nat_punch_enable=nat_punch_enable,
        solana_reputation_enable=solana_reputation_enable,
        solana_reputation_refresh_s=1,
        scheduler_onchain_weight=10.0,
        scheduler_offchain_weight=1.0,
        scheduler_capacity_weight=0.01,
        pull_tasks_enable=False,
        pull_tasks_interval_s=1,
    )


def _queued_task(export_dir: Path, task_id: str, role: str, **extra: object) -> None:
    payload = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": task_id,
        "status": "queued",
        "required_roles": [role],
        "task": {"kind": role},
        **extra,
    }
    path = export_dir / "tasks" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_claim_does_not_wait_for_a_busy_alternative(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    node = network_node.NetworkNode(_config(export_dir, "orchestrator", roles="resource"))
    _queued_task(
        export_dir,
        "render-frag-000-verify",
        "verify",
        excluded_node_ids=["worker-a"],
        excluded_until_unix=time.time() + 120,
    )
    node.peer_network._peers["worker-b"] = {
        "node_id": "worker-b",
        "roles": ["verify"],
        "last_seen_unix": time.time(),
        "accepting_tasks": False,
        "active_task_count": 1,
    }

    claimed = node.claim_task_for_peer(
        {
            "node_id": "worker-a",
            "roles": ["verify"],
            "capacity": {"cpu_count": 8},
            "active_task_ids": [],
            "active_task_count": 0,
            "accepting_tasks": True,
        }
    )

    assert claimed["claimed"] is True
    assert claimed["task"]["claimed_by"] == "worker-a"


def test_claim_waits_for_an_available_alternative(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    node = network_node.NetworkNode(_config(export_dir, "orchestrator", roles="resource"))
    _queued_task(
        export_dir,
        "render-frag-000-verify",
        "verify",
        excluded_node_ids=["worker-a"],
        excluded_until_unix=time.time() + 120,
    )
    node.peer_network._peers["worker-b"] = {
        "node_id": "worker-b",
        "roles": ["verify"],
        "last_seen_unix": time.time(),
        "accepting_tasks": True,
        "active_task_count": 0,
    }

    claimed = node.claim_task_for_peer(
        {
            "node_id": "worker-a",
            "roles": ["verify"],
            "capacity": {"cpu_count": 8},
            "active_task_ids": [],
            "active_task_count": 0,
            "accepting_tasks": True,
        }
    )

    assert claimed["claimed"] is False


def test_worker_accepts_claims_until_its_cpu_slot_limit(tmp_path: Path, monkeypatch) -> None:
    node = network_node.NetworkNode(_config(tmp_path / "export", "worker-a"))
    monkeypatch.setattr(node, "local_max_active_tasks", lambda: 2)

    assert node.local_available_task_slots() == 2
    with node._active_task_lock:
        node._active_task_ids.add("fragment-a")
    assert node.local_available_task_slots() == 1
    with node._active_task_lock:
        node._active_task_ids.add("fragment-b")
    assert node.local_available_task_slots() == 0


def test_result_return_retries_transient_network_errors(tmp_path: Path, monkeypatch) -> None:
    node = network_node.NetworkNode(_config(tmp_path / "export", "worker-a"))
    calls = 0

    class Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def flaky_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == 5
        if calls < 3:
            raise urllib.error.URLError("temporary")
        return Response()

    monkeypatch.setattr(network_node.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(network_node.time, "sleep", lambda _seconds: None)

    delivered = node.return_dispatched_result(
        {
            "task_id": "render-frag-000",
            "dispatched_by": "orchestrator",
            "result_return_url": "http://127.0.0.1:46100/results/dispatch",
        },
        {"success": True, "result_hash": "sha256:test"},
        {"role": "compute", "fragment_index": 0},
    )

    assert delivered is True
    assert calls == 3


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

    result = json.loads((export_dir / "result.storage_1.json").read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["required_roles"] == ["storage"]
    assert result["input"]["source"] == "local-p2p-cache"
    assert result["role_result"] == "storage"
    assert result["stored_ref"]["hash"].startswith("sha256:")

    stored = json.loads((export_dir / "tasks" / "storage_1.json").read_text(encoding="utf-8"))
    assert stored["status"] == "completed"
    assert stored["handled_by"] == "node-a"
    heartbeat = json.loads((export_dir / "node.node-a.heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["online"] is True
    assert heartbeat["status"] == "idle"
    assert heartbeat["active_tasks"] == []
    assert heartbeat["last_response"]["item_id"] == "storage:1"
    assert heartbeat["last_response"]["ok"] is True
    events = [json.loads(line) for line in (export_dir / "node.events.ndjson").read_text(encoding="utf-8").splitlines()]
    assert any(event["kind"] == "task_started" and event["item_id"] == "storage:1" for event in events)
    assert any(event["kind"] == "task_input_fetched" and event["ok"] is True for event in events)
    assert any(event["kind"] == "task" and event["phase"] == "completed" and event["ok"] is True for event in events)
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

    assert (export_dir / "result.audit_now.json").exists()
    assert not (export_dir / "result.compute_late.json").exists()
    events = [json.loads(line) for line in (export_dir / "node.events.ndjson").read_text(encoding="utf-8").splitlines()]
    completed = [event for event in events if event.get("phase") == "completed"]
    assert completed[0]["kind"] == "request"
    assert completed[0]["item_id"] == "audit:now"


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

    result = json.loads((export_dir / "result.compute_on-chain.json").read_text(encoding="utf-8"))
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

    result = json.loads((export_dir / "result.audit_on-chain.json").read_text(encoding="utf-8"))
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

    result = json.loads((export_dir / "result.verify_1.json").read_text(encoding="utf-8"))
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

    result = json.loads((export_dir / "result.storage_missing.json").read_text(encoding="utf-8"))
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
    peer_a.set_local_activity(
        {
            "status": "working",
            "active_task_count": 1,
            "active_tasks": [
                {
                    "item_id": "render:fragment:2",
                    "role": "compute",
                    "activity": "fragment",
                    "fragment_index": 2,
                }
            ],
            "last_response": {"item_id": "verify:1", "ok": True, "timestamp_utc": network_node.utc_now()},
        }
    )
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
    peer_a.set_local_activity(
        {
            "status": "working",
            "active_task_count": 1,
            "active_tasks": [{"item_id": "render:fragment:2", "role": "compute", "activity": "fragment", "fragment_index": 2}],
            "last_response": {"item_id": "verify:1", "ok": True, "timestamp_utc": network_node.utc_now()},
        }
    )
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
            peer_a_from_b = next(peer for peer in peer_b.peers_snapshot()["peers"] if peer["node_id"] == "node-a")
            assert peer_a_from_b["online"] is True
            assert peer_a_from_b["activity"]["status"] == "working"
            assert peer_a_from_b["activity"]["active_tasks"][0]["fragment_index"] == 2
            assert peer_a_from_b["activity"]["last_response"]["ok"] is True

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
        dispatched = json.loads((export_a / "tasks" / "compute_remote.json").read_text(encoding="utf-8"))
        assert dispatched["status"] == "dispatched"
        remote_task = json.loads((export_b / "tasks" / "compute_remote.json").read_text(encoding="utf-8"))
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
        dispatched = json.loads((export_a / "tasks" / "compute_return.json").read_text(encoding="utf-8"))
        assert dispatched["status"] == "dispatched"
        handled_b = node_b.sweep()
        assert handled_b == 1
        result = json.loads((export_a / "result.compute_return.json").read_text(encoding="utf-8"))
        assert result["node_id"] == "node-b"
        origin_task = json.loads((export_a / "tasks" / "compute_return.json").read_text(encoding="utf-8"))
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
        remote_task = json.loads((export_b / "tasks" / "compute_threshold.json").read_text(encoding="utf-8"))
        assert remote_task["task_id"] == "compute:threshold"
        assert not (export_c / "tasks" / "compute_threshold.json").exists()
    finally:
        peer_b.stop()
        peer_c.stop()
