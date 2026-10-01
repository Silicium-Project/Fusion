"""Task queue visibility, worker liveness and reconciliation of stuck tasks.

Covers announcing the queue and live activity in the peer book, not refreshing
liveness from transitive snapshots, and closing orphaned/lost/incomplete
running or dispatched tasks (interrupted, worker_lost, incomplete).
"""

import json
import time
from pathlib import Path

from tools import network_node
from tests.network_node_support import _path_id, _config


def test_reconcile_keeps_running_task_without_known_worker(tmp_path: Path) -> None:
    export_dir = tmp_path / "reconcile-unassigned"
    node = network_node.NetworkNode(_config(export_dir, "worker-a", roles="compute", gossip_enable=False))
    running = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "render-unassigned",
        "status": "running",
        "required_roles": ["compute"],
        "task": {"kind": "compute"},
    }
    network_node.atomic_write_json(export_dir / "tasks" / "render-unassigned.json", running)
    node.reconcile_orphaned_running_tasks()
    stored = json.loads((export_dir / "tasks" / "render-unassigned.json").read_text(encoding="utf-8"))
    assert stored["status"] == "running"


def test_task_queue_and_live_activity_are_announced_in_peer_book(tmp_path: Path) -> None:
    export_dir = tmp_path / "observable-node"
    node = network_node.NetworkNode(_config(export_dir, "worker-a", roles="compute,verify"))
    network_node.enqueue_task_envelope(
        export_dir,
        {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "render-frag-007-verify",
            "status": "queued",
            "required_roles": ["verify"],
            "task": {
                "kind": "verify",
                "workload": "verification/rendering/raytracer-fragment",
                "fragment_index": 7,
                "fragment_count": 16,
                "source_task_id": "render-frag-007",
                "source_node_id": "worker-b",
            },
        },
    )
    node.remember_task_queue_envelope(
        json.loads(
            (export_dir / "tasks" / f"{_path_id('render-frag-007-verify')}.json").read_text(
                encoding="utf-8"
            )
        )
    )
    node.publish_runtime_state()

    deadline = time.monotonic() + 2.0
    while True:
        node.publish_runtime_state()
        self_peer = next(peer for peer in node.peer_network.peers_snapshot()["peers"] if peer.get("self"))
        if self_peer["task_queue"] or time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    assert self_peer["task_queue"][0]["item_id"] == "render-frag-007-verify"
    assert self_peer["task_queue"][0]["role"] == "verify"
    assert self_peer["task_queue"][0]["source_node_id"] == "worker-b"
    assert self_peer["activity"]["status"] == "idle"


def test_transitive_peer_snapshots_do_not_refresh_worker_liveness(tmp_path: Path) -> None:
    export_dir = tmp_path / "liveness-node"
    peer = network_node.PeerNetwork(_config(export_dir, "orchestrator", gossip_enable=False), export_dir)
    peer.config.peer_stale_after_s = 2
    old_seen = int(time.time()) - 1
    peer._peers["worker-a"] = {
        "node_id": "worker-a",
        "last_seen_unix": old_seen,
        "roles": ["compute"],
    }

    peer._record_peer(
        {
            "node_id": "worker-a",
            "roles": ["compute"],
            "last_seen_unix": old_seen,
            "timestamp_utc": network_node.utc_now(),
        },
        refresh_liveness=False,
    )
    assert peer._peers["worker-a"]["last_seen_unix"] == old_seen

    time.sleep(2.1)
    assert all(item.get("node_id") != "worker-a" for item in peer.peers_snapshot()["peers"])


def test_orphaned_local_running_task_is_closed_as_interrupted(tmp_path: Path) -> None:
    export_dir = tmp_path / "orphaned-task"
    node = network_node.NetworkNode(_config(export_dir, "worker-a", roles="compute"))
    envelope = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "orphaned-task-001",
        "status": "queued",
        "required_roles": ["compute"],
        "task": {"kind": "compute"},
    }
    network_node.enqueue_task_envelope(export_dir, envelope)
    node.update_envelope_status(envelope, "running", {})

    assert node.task_queue_snapshot() == []
    persisted = json.loads(
        (export_dir / "tasks" / f"{_path_id('orphaned-task-001')}.json").read_text(encoding="utf-8")
    )
    assert persisted["status"] == "failed"
    assert persisted["error"] == "task_interrupted"
    assert persisted["error_type"] == "TaskInterrupted"


def test_running_task_on_disconnected_worker_is_closed_as_worker_lost(tmp_path: Path) -> None:
    export_dir = tmp_path / "running-lost-worker-task"
    node = network_node.NetworkNode(_config(export_dir, "orchestrator", roles="storage"))
    node.peer_network._peers["worker-a"] = {
        "node_id": "worker-a",
        "last_seen_unix": int(time.time()) - 120,
        "roles": ["compute"],
    }
    envelope = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "running-lost-worker-task-001",
        "status": "running",
        "handled_by": "worker-a",
        "dispatched_to": "worker-a",
        "required_roles": ["compute"],
        "task": {"kind": "compute"},
    }
    network_node.enqueue_task_envelope(export_dir, envelope)
    network_node.atomic_write_json(
        export_dir / "tasks" / f"{_path_id('running-lost-worker-task-001')}.json",
        envelope,
    )

    assert node.task_queue_snapshot() == []
    persisted = json.loads(
        (export_dir / "tasks" / f"{_path_id('running-lost-worker-task-001')}.json").read_text(encoding="utf-8")
    )
    assert persisted["status"] == "failed"
    assert persisted["error"] == "task_worker_lost"
    assert persisted["error_type"] == "TaskWorkerLost"


def test_dispatched_task_to_stale_worker_is_closed_as_worker_lost(tmp_path: Path) -> None:
    export_dir = tmp_path / "lost-worker-task"
    node = network_node.NetworkNode(_config(export_dir, "orchestrator", roles="storage"))
    node.peer_network._peers["worker-a"] = {
        "node_id": "worker-a",
        "last_seen_unix": int(time.time()) - 120,
        "roles": ["compute"],
    }
    envelope = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "lost-worker-task-001",
        "status": "queued",
        "required_roles": ["compute"],
        "task": {"kind": "compute"},
    }
    network_node.enqueue_task_envelope(export_dir, envelope)
    node.update_envelope_status(envelope, "dispatched", {"dispatched_to": "worker-a"})

    assert node.task_queue_snapshot() == []
    persisted = json.loads(
        (export_dir / "tasks" / f"{_path_id('lost-worker-task-001')}.json").read_text(encoding="utf-8")
    )
    assert persisted["status"] == "failed"
    assert persisted["error"] == "task_worker_lost"
    assert persisted["error_type"] == "TaskWorkerLost"


def test_dispatched_task_without_target_is_closed_as_incomplete(tmp_path: Path) -> None:
    export_dir = tmp_path / "missing-dispatch-target"
    node = network_node.NetworkNode(_config(export_dir, "orchestrator", roles="storage"))
    envelope = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "missing-dispatch-target-001",
        "status": "dispatched",
        "required_roles": ["compute"],
        "task": {"kind": "compute"},
    }
    network_node.enqueue_task_envelope(export_dir, envelope)
    network_node.atomic_write_json(
        export_dir / "tasks" / f"{_path_id('missing-dispatch-target-001')}.json",
        envelope,
    )

    assert node.task_queue_snapshot() == []
    persisted = json.loads(
        (export_dir / "tasks" / f"{_path_id('missing-dispatch-target-001')}.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["status"] == "failed"
    assert persisted["error"] == "task_dispatch_target_missing"
    assert persisted["error_type"] == "TaskDispatchTargetMissing"
