"""Reputation persistence and the Solana bridge integration.

Covers on-chain compute result submission and audit votes through a fake Node
bridge, local reputation persistence, and scheduler/remote-dispatch decisions
driven by (role-specific) on-chain reputation and thresholds.
"""

import json
from pathlib import Path

from tools import network_node
from tests.network_node_support import _write_jsonl, _path_id, _config


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
