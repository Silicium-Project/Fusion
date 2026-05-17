import json
import time
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


def _config(export_dir: Path, node_id: str, *, roles: str = "compute", seed_peers: list[str] | None = None) -> network_node.NodeConfig:
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
        solana_enable=False,
        solana_rpc="https://api.devnet.solana.com",
        solana_program_id="HyXT83SzHsEPxNZ5zQPvkLwQ7JwFHh2veAE5PuGUgoiQ",
        solana_wallet=str(export_dir / "wallet.json"),
        solana_bridge=export_dir / "bridge.cjs",
        solana_timeout_s=10,
        max_retries=0,
        worker_binary="missing-worker",
        worker_mode="emu",
        bootstrap_worker=False,
        gossip_enable=True,
        gossip_bind="127.0.0.1",
        gossip_port=0,
        peer_http_bind="127.0.0.1",
        peer_http_port=0,
        seed_peers=seed_peers or [],
    )


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
