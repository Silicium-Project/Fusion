"""Pull-based work claims by workers.

Covers claiming over HTTP polling, assigned/excluded peer constraints, batch
claims, index-balanced fragment claims, generic claims, exclusion of terminal
tasks and avoiding reputation rewrites on the claim hot path.
"""

import json
import time
from pathlib import Path

import pytest

from tools import network_node
from tests.network_node_support import _path_id, _config


def test_peer_registration_does_not_rewrite_unchanged_score_on_claim_hot_path(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer-score", "node-a"), tmp_path / "peer-score")
    updates: list[tuple[str, float]] = []
    peer.set_peer_score_sink(lambda node_id, score: updates.append((str(node_id), float(score))))
    message = {
        "node_id": "worker-a",
        "roles": ["compute"],
        "reputation_score": 50.0,
        "release_channel": "dev",
        "last_seen_unix": int(time.time()),
    }

    peer._record_peer(message, persist_snapshot=False)
    peer._record_peer(message, persist_snapshot=False)

    assert updates == [("worker-a", 50.0)]


def test_worker_claims_task_over_http_poll(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    export_seed = tmp_path / "seed"
    export_worker = tmp_path / "worker"
    config_seed = _config(export_seed, "seed-orchestrator", roles="storage")
    seed_node = network_node.NetworkNode(config_seed)
    seed_node.peer_network.start()
    try:
        task_envelope = {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "test:claim:001",
            "status": "queued",
            "required_roles": ["compute"],
            "task": {
                "kind": "compute",
                "workload": "raytracer-fragment",
                "scene_p2p_ref": {
                    "protocol": "silicium",
                    "content_id": network_node.sha256_bytes(b"scene"),
                    "peer_id": "seed-orchestrator",
                },
            },
        }
        scene_id = network_node.sha256_bytes(b"scene")
        (export_seed / "p2p").mkdir(parents=True)
        (export_seed / "p2p" / scene_id).write_bytes(b"scene")
        network_node.enqueue_task_envelope(export_seed, task_envelope)

        config_worker = _config(
            export_worker,
            "worker-node",
            roles="compute",
            seed_peers=[seed_node.peer_network.advertised_http_base_url],
        )
        config_worker.pull_tasks_enable = True
        config_worker.pull_tasks_interval_s = 1
        config_worker.gossip_port = 46133
        worker_node = network_node.NetworkNode(config_worker)
        worker_node.peer_network.refresh_candidates()
        monkeypatch.setattr(
            worker_node.peer_network,
            "_poll_signaling_sessions",
            lambda _base_url: pytest.fail("signaling sync must stay out of the claim hot path"),
        )
        monkeypatch.setattr(
            worker_node.peer_network,
            "_sync_task_controls",
            lambda _base_url: pytest.fail("control anti-entropy must stay out of the claim hot path"),
        )
        monkeypatch.setattr(
            worker_node.peer_network,
            "refresh_candidates",
            lambda: pytest.fail("candidate discovery must stay out of the claim hot path"),
        )

        worker_node._poll_and_claim_tasks_once()

        claimed_path = export_worker / "tasks" / f"{_path_id('test:claim:001')}.json"
        assert claimed_path.exists()
        claimed_data = json.loads(claimed_path.read_text(encoding="utf-8"))
        assert claimed_data["task_id"] == "test:claim:001"
        assert claimed_data["result_return_url"] == (
            seed_node.peer_network.advertised_http_base_url.rstrip("/") + "/results/dispatch"
        )
        assert (export_worker / "p2p" / scene_id).read_bytes() == b"scene"
        assert (export_worker / "claim-poll.health.json").exists()
        claim_health = json.loads((export_worker / "claim-poll.health.json").read_text(encoding="utf-8"))
        assert claim_health["duration_ms"] >= 0
        assert claim_health["attempts"][0]["duration_ms"] >= 0
        worker_peer = next(
            peer
            for peer in seed_node.peer_network.peers_snapshot()["peers"]
            if peer["node_id"] == "worker-node"
        )
        assert worker_peer["candidates"]
        assert worker_peer["features"]
    finally:
        seed_node.peer_network.stop()


def test_worker_claim_respects_assigned_peer_id(tmp_path: Path) -> None:
    export_seed = tmp_path / "assigned-seed"
    config_seed = _config(export_seed, "seed-orchestrator", roles="storage")
    seed_node = network_node.NetworkNode(config_seed)
    task_envelope = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "test:assigned:001",
        "status": "queued",
        "assigned_peer_id": "worker-b",
        "required_roles": ["verify"],
        "task": {"kind": "verify"},
    }
    network_node.enqueue_task_envelope(export_seed, task_envelope)

    assert seed_node.claim_task_for_worker("worker-a", {"verify"}) is None
    claimed = seed_node.claim_task_for_worker("worker-b", {"verify"})
    assert claimed is not None
    assert claimed["task_id"] == "test:assigned:001"
    assert claimed["dispatched_to"] == "worker-b"


def test_worker_claims_multiple_tasks_in_one_batch(tmp_path: Path) -> None:
    export_seed = tmp_path / "batch-seed"
    seed_node = network_node.NetworkNode(_config(export_seed, "seed-orchestrator", roles="storage"))
    for index in range(3):
        network_node.enqueue_task_envelope(
            export_seed,
            {
                "schema_version": 1,
                "envelope_kind": "task",
                "task_id": f"batch-task-{index}",
                "status": "queued",
                "required_roles": ["compute"],
                "task": {"kind": "compute", "workload": "calcul/integrity/sha256"},
            },
        )

    first_batch = seed_node.claim_tasks_for_worker("worker-a", {"compute"}, limit=2)
    assert [item["task_id"] for item in first_batch] == ["batch-task-0", "batch-task-1"]
    assert all(item["dispatched_to"] == "worker-a" for item in first_batch)
    second_batch = seed_node.claim_tasks_for_worker("worker-a", {"compute"}, limit=2)
    assert [item["task_id"] for item in second_batch] == ["batch-task-2"]


def test_worker_claim_respects_excluded_peer_ids(tmp_path: Path) -> None:
    export_seed = tmp_path / "excluded-seed"
    seed_node = network_node.NetworkNode(_config(export_seed, "seed-orchestrator", roles="storage"))
    task_envelope = {
        "schema_version": 1,
        "envelope_kind": "task",
        "task_id": "test:excluded:001",
        "status": "queued",
        "excluded_peer_ids": ["compute-worker"],
        "required_roles": ["verify"],
        "task": {"kind": "verify"},
    }
    network_node.enqueue_task_envelope(export_seed, task_envelope)

    assert seed_node.claim_task_for_worker("compute-worker", {"verify"}) is None
    claimed = seed_node.claim_task_for_worker("independent-verifier", {"verify"})
    assert claimed is not None
    assert claimed["task_id"] == "test:excluded:001"
    assert claimed["dispatched_to"] == "independent-verifier"


def test_fragment_claims_are_balanced_by_index_across_compatible_workers(tmp_path: Path) -> None:
    export_seed = tmp_path / "balanced-seed"
    seed_node = network_node.NetworkNode(_config(export_seed, "seed-orchestrator", roles="storage"))
    for worker_id in ("worker-a", "worker-b"):
        seed_node.peer_network.update_peer_metadata(
            worker_id,
            {
                "roles": ["compute", "verify"],
                "last_seen_unix": int(time.time()),
            },
        )
    for fragment_index in range(2):
        network_node.enqueue_task_envelope(
            export_seed,
            {
                "schema_version": 1,
                "envelope_kind": "task",
                "task_id": f"render-frag-{fragment_index:03d}",
                "status": "queued",
                "required_roles": ["compute"],
                "task": {
                    "kind": "compute",
                    "workload": "calcul/rendering/raytracer-fragment",
                    "fragment_index": fragment_index,
                    "fragment_count": 2,
                },
            },
        )

    first = seed_node.claim_task_for_worker("worker-a", {"compute", "verify"})
    assert first is not None
    assert first["task"]["fragment_index"] == 0
    assert seed_node.claim_task_for_worker("worker-a", {"compute", "verify"}) is None
    second = seed_node.claim_task_for_worker("worker-b", {"compute", "verify"})
    assert second is not None
    assert second["task"]["fragment_index"] == 1


def test_generic_claim_is_served_by_the_requesting_compatible_worker(tmp_path: Path) -> None:
    export_seed = tmp_path / "generic-claim"
    seed_node = network_node.NetworkNode(_config(export_seed, "seed-orchestrator", roles="storage"))
    for worker_id in ("worker-a", "worker-b"):
        seed_node.peer_network.update_peer_metadata(
            worker_id,
            {
                "roles": ["compute"],
                "last_seen_unix": int(time.time()),
            },
        )
    network_node.enqueue_task_envelope(
        export_seed,
        {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": "generic-compute-001",
            "status": "queued",
            "required_roles": ["compute"],
            "task": {"kind": "compute", "workload": "calcul/integrity/sha256"},
        },
    )

    claimed = seed_node.claim_task_for_worker("worker-a", {"compute"})

    assert claimed is not None
    assert claimed["dispatched_to"] == "worker-a"


@pytest.mark.parametrize(
    "status",
    [
        "completed",
        "failed",
        "dead_lettered",
        "cancelled",
        "canceled",
        "expired",
        "finalized",
        "resolved",
        "COMPLETED",
    ],
)
def test_terminal_tasks_are_excluded_from_queue_and_claims(tmp_path: Path, status: str) -> None:
    export_dir = tmp_path / f"terminal-{status.lower()}"
    node = network_node.NetworkNode(_config(export_dir, "worker-a", roles="compute"))
    network_node.enqueue_task_envelope(
        export_dir,
        {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": f"terminal-{status.lower()}",
            "status": status,
            "required_roles": ["compute"],
            "task": {"kind": "compute"},
        },
    )

    assert node.task_queue_snapshot() == []
    assert node.claim_task_for_worker("worker-a", {"compute"}) is None
