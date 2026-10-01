"""Local role runtime: processing queued tasks and producing verifiable results.

Covers task processing with P2P references, urgent-request priority, expected
hash verification, retries and dead-lettering, bounded ingestion of dispatched
content, the raytracer challenge verifier and signed compute receipts.
"""

import base64
import hashlib
import json
from pathlib import Path

import pytest

from tools import network_node
from tests.network_node_support import _write_jsonl, _path_id, _config


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
            "--app-version",
            "0.2.9-dev.1",
            "--release-channel",
            "dev",
            "--release-build",
            "test-build",
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
    heartbeat = json.loads((export_dir / "node.node-a.heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["app_version"] == "0.2.9-dev.1"
    assert heartbeat["release_channel"] == "dev"
    assert heartbeat["release_build"] == "test-build"
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
    assert result["error_type"]
    assert "Traceback" in result["traceback"]
    log = json.loads((export_dir / f"logs.{_path_id('storage:missing')}.json").read_text(encoding="utf-8"))
    assert log["traceback"] == result["traceback"]
    envelope = json.loads((export_dir / "tasks" / f"{network_node.safe_path_id(network_node.safe_id('storage:missing'))}.json").read_text(encoding="utf-8"))
    assert envelope["traceback"] == result["traceback"]
    assert (export_dir / "dead_letters.ndjson").exists()
    metrics = json.loads((export_dir / "node.node-a.metrics.json").read_text(encoding="utf-8"))
    assert metrics["dead_lettered"] == 1


def test_network_node_ingests_bounded_dispatched_content(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    node = network_node.NetworkNode(_config(export_dir, "worker-node"))
    content = b"inline task input"
    content_id = network_node.sha256_bytes(content)

    stored = node.ingest_content_blobs(
        {
            "content_blobs": [
                {
                    "content_id": content_id,
                    "data_b64": base64.b64encode(content).decode("ascii"),
                }
            ]
        }
    )

    assert stored == [content_id]
    assert (export_dir / "p2p" / content_id).read_bytes() == content


def test_raytracer_verifier_recomputes_only_challenged_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from workloads.raytracer import node_tasks

    header = b"P6\n2 2\n255\n"
    sample_ppm = header + bytes(range(12))
    expected = hashlib.sha256(bytes(range(12))).hexdigest()
    # The pixel hash itself runs in the Rust binary (covered by test_raytracer_native).
    monkeypatch.setattr(node_tasks.native, "pixel_sha256", lambda data: hashlib.sha256(data[len(header):]).hexdigest())
    challenge = {
        "strategy": "random-tile-row-milestone-v2",
        "challenge_nonce": "nonce-test",
        "commitment_hash": "commitment-test",
        "fragment_rows": 20,
        "milestone_count": 10,
        "milestone": {
            "index": 4,
            "x_start": 320,
            "x_end": 322,
            "y_start": 108,
            "y_end": 110,
            "row_count": 2,
            "pixel_sha256": expected,
        },
    }

    class FakeP2P:
        def fetch(self, _ref):
            return b"scene", {"source": "test-scene"}

    def fake_raytracer(scene_path, output_path, _timeout, y_start, y_end, x_start, x_end, *_args):
        output_path.write_bytes(sample_ppm)
        assert y_start == 108
        assert y_end == 110
        assert x_start == 320
        assert x_end == 322
        return {"stdout": "", "stderr": "", "renderer_telemetry": {"renderer": "test"}}

    runtime = network_node.RoleRuntime(_config(tmp_path / "verify", "verifier", roles="verify"), FakeP2P())
    monkeypatch.setattr(node_tasks, "run_raytracer", fake_raytracer)
    result = runtime.run_verify_task(
        {},
        {
            "workload": "verification/rendering/raytracer-fragment",
            "scene_p2p_ref": {"protocol": "test"},
            "max_sample_rows": 20,
        },
        json.dumps(challenge).encode("utf-8"),
        {"source": "test-challenge"},
    )

    assert result["choice"] is True
    assert result["verification_mode"] == "random-tile-row-milestone-v2"
    assert result["verification"]["sample_x_start"] == 320
    assert result["verification"]["sample_rows"] == 2
    assert result["verification"]["fragment_rows"] == 20
    assert result["verification"]["sample_ratio"] == pytest.approx(0.1)


def test_compute_receipt_uses_deterministic_pixels_and_has_valid_signature(tmp_path: Path) -> None:
    node = network_node.NetworkNode(_config(tmp_path / "receipt", "worker-a", roles="compute"))
    envelope = {
        "task_id": "job-1-frag-000",
        "task": {
            "root_job_id": "job-1",
            "workload": "calcul/rendering/raytracer-fragment",
            "x_start": 10,
            "x_end": 30,
            "y_start": 5,
            "y_end": 15,
        },
    }
    receipt = node.build_compute_receipt(
        envelope,
        {"role_result": "compute", "result_hash": "abc"},
        {"duration_ms": 123, "process_cpu_seconds": 99},
        started_utc="2026-07-23T10:00:00Z",
        finished_utc="2026-07-23T10:00:01Z",
    )

    assert receipt["billable_work_units"] == 200
    assert receipt["unit"] == "rendered_pixel"
    unsigned = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_hash", "worker_identity_id", "worker_public_key", "worker_signature"}
    }
    assert receipt["receipt_hash"] == network_node.sha256_json(unsigned)
    assert network_node.NodeIdentity.verify_bytes(
        network_node.stable_json(unsigned).encode("utf-8"),
        receipt["worker_signature"],
        receipt["worker_public_key"],
    )
