"""Remote task dispatch, result ingestion and task control (cancellation).

Covers dispatch to a remote peer and ingestion of the result at the origin,
skipping canonical queue replays, excluded-peer normalisation, signed task
control (cancel, spoofed issuer, anti-entropy to late workers) and refusing
tasks whose root was cancelled.
"""

import json
import time
from pathlib import Path

import pytest

from tools import network_node
from tests.network_node_support import _write_jsonl, _path_id, _config


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


@pytest.mark.parametrize("canonical_status", ["running", "dispatched", "completed", "failed", "cancelled", "expired"])
def test_network_node_skips_canonical_queue_replays(tmp_path: Path, canonical_status: str) -> None:
    export_dir = tmp_path / f"replay-{canonical_status}"
    node = network_node.NetworkNode(_config(export_dir, "worker-a", roles="compute", gossip_enable=False))
    # The constructor starts a background queue snapshot that reconciles
    # orphaned tasks; let it finish so it cannot race the files written below.
    deadline = time.time() + 10.0
    while node._task_queue_cache_refreshing and time.time() < deadline:
        time.sleep(0.01)
    assert not node._task_queue_cache_refreshing
    queued = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "render-old-fragment",
        "status": "queued",
        "required_roles": ["compute"],
        "task": {"kind": "compute"},
    }
    _write_jsonl(export_dir / "tasks.compute.queue.ndjson", queued)
    canonical = dict(queued)
    canonical["status"] = canonical_status
    network_node.atomic_write_json(export_dir / "tasks" / "render-old-fragment.json", canonical)

    assert node.sweep() == 0
    events = (export_dir / "node.events.ndjson").read_text(encoding="utf-8")
    assert '"kind":"queue_replay_skipped"' in events
    assert f'"status":"{canonical_status}"' in events


def test_remote_dispatch_normalizes_excluded_peer_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    export_dir = tmp_path / "remote-dispatch-excluded"
    node = network_node.NetworkNode(
        _config(export_dir, "node-a", roles="storage", gossip_enable=False, remote_dispatch_enable=True)
    )
    observed_exclude: set[str] = set()

    def select_peers(**kwargs: object) -> list[dict[str, object]]:
        observed_exclude.update(kwargs["exclude"])  # type: ignore[arg-type]
        return []

    monkeypatch.setattr(node.peer_network, "select_peers", select_peers)

    dispatched = node.try_remote_dispatch(
        {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "verify:excluded",
            "required_roles": ["verify"],
            "excluded_peer_ids": ["compute worker", "", None],
            "task": {"kind": "verify"},
        }
    )

    assert dispatched is False
    assert observed_exclude == {"node-a", "compute_worker"}


def test_task_control_cancels_matching_active_work_and_rejects_spoofed_issuer(tmp_path: Path) -> None:
    node = network_node.NetworkNode(_config(tmp_path / "control", "payer-node", roles="compute"))
    with node._activity_lock:
        node._active_tasks = [{"item_id": "job-42-frag-000", "phase": "executing"}]
    control = {
        "control_id": "control-1",
        "root_job_id": "job-42",
        "action": "cancel",
        "reason": "payer request",
        "issuer_node_id": "payer-node",
        "issued_utc": network_node.utc_now(),
    }

    assert node.apply_task_control(control, signed_by="attacker") is False
    assert node.runtime._cancel_event.is_set() is False
    assert node.apply_task_control(control, signed_by="payer-node") is True
    assert node.runtime._cancel_event.is_set() is True
    assert node.task_control_for("job-42-frag-007")["control_id"] == "control-1"


def test_task_control_anti_entropy_reaches_a_late_worker(tmp_path: Path) -> None:
    source = network_node.NetworkNode(
        _config(tmp_path / "control-source", "payer-node", gossip_enable=False, roles="storage")
    )
    source.peer_network.start()
    try:
        control = {
            "control_id": "job-late-cancel-terminal",
            "root_job_id": "job-late",
            "action": "cancel",
            "reason": "payer request",
            "issuer_node_id": "payer-node",
            "issued_utc": network_node.utc_now(),
        }
        assert source.apply_task_control(control, signed_by="payer-node")
        source.peer_network.publish("task_control", control)

        worker = network_node.NetworkNode(
            _config(
                tmp_path / "late-worker",
                "worker-node",
                gossip_enable=False,
                roles="compute",
                seed_peers=[source.peer_network.http_base_url],
            )
        )
        worker.peer_network.start()
        try:
            worker.peer_network.sync_once()
            recovered = worker.task_control_for("job-late-frag-099", "payer-node")
            assert recovered is not None
            assert recovered["control_id"] == "job-late-cancel-terminal"
            assert (tmp_path / "late-worker" / "gossip.task-controls.ndjson").exists()
        finally:
            worker.peer_network.stop()
    finally:
        source.peer_network.stop()


def test_scheduler_refuses_task_enqueued_after_its_root_was_cancelled(tmp_path: Path) -> None:
    export_dir = tmp_path / "cancelled-claim"
    node = network_node.NetworkNode(_config(export_dir, "payer-node", gossip_enable=False, roles="storage"))
    control = {
        "control_id": "job-cancelled-cancel-terminal",
        "root_job_id": "job-cancelled",
        "action": "cancel",
        "reason": "job is terminal",
        "issuer_node_id": "payer-node",
        "issued_utc": network_node.utc_now(),
    }
    assert node.apply_task_control(control, signed_by="payer-node")
    network_node.enqueue_task_envelope(
        export_dir,
        {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "job-cancelled-frag-001",
            "status": "queued",
            "origin_node_id": "payer-node",
            "required_roles": ["compute"],
            "task": {"kind": "compute", "root_job_id": "job-cancelled"},
        },
    )

    assert node.claim_task_for_worker("worker-node", {"compute"}) is None
    envelope = json.loads(
        (export_dir / "tasks" / f"{_path_id('job-cancelled-frag-001')}.json").read_text(encoding="utf-8")
    )
    assert envelope["status"] == "cancelled"
    assert envelope["task_control"]["control_id"] == "job-cancelled-cancel-terminal"
