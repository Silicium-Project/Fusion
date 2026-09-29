from __future__ import annotations

import argparse
import base64
import json

import pytest

from networked.networked_runtime import attach_network_content_blobs, store_network_content
from workloads.common import ppm_to_png_bytes, sha256_bytes
from workloads.raytracer import raytracer_workload
from workloads.raytracer.run_network_job import (
    discovered_role_capacity,
    ensure_submission_success,
    ensure_raytracer_compute_contract,
    is_transient_task_failure,
    task_failure_details,
    poll_task_result_attempts,
    refresh_attempt_deadline,
    retry_excluded_peer_ids,
    RetryFragmentStage,
    resolve_in_flight_limit,
    run_bounded_fragment_pipeline,
    submit_network_task,
    validate_fragment_ppm,
    wait_for_network_role,
)


def _ppm(width: int, height: int, pixels: bytes) -> bytes:
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels


def test_ppm_parsers_preserve_whitespace_as_first_pixel_byte() -> None:
    ppm = _ppm(1, 1, bytes([0x0A, 0x20, 0x23]))

    width, height, pixels = raytracer_workload.parse_ppm_bytes(ppm)

    assert (width, height) == (1, 1)
    assert pixels == bytes([0x0A, 0x20, 0x23])
    assert ppm_to_png_bytes(ppm).startswith(b"\x89PNG\r\n\x1a\n")


def test_compute_contract_rejects_generic_worker_result() -> None:
    result = {
        "node_id": "legacy-worker",
        "compute": {"mode": "deterministic-local", "executed": False, "reason": "missing_summary"},
    }

    with pytest.raises(RuntimeError, match="raytracer_compute_contract_invalid"):
        ensure_raytracer_compute_contract(result, "fragment-000")


def test_persistent_scheduler_queues_locally_without_http_auth(tmp_path) -> None:
    payload = {
        "task_id": "fragment-000-verify",
        "required_roles": ["verify"],
        "priority": "high",
        "excluded_peer_ids": ["compute-worker"],
        "task": {"kind": "verify", "workload": "raytracer-fragment"},
    }

    submission = submit_network_task(argparse.Namespace(), tmp_path, payload, None)

    assert submission["status"] == "queued"
    assert submission["queue"] == "scheduler://local-export"
    stored = json.loads((tmp_path / "tasks" / "fragment-000-verify.json").read_text(encoding="utf-8"))
    assert stored["excluded_peer_ids"] == ["compute-worker"]
    assert (tmp_path / "tasks.verify.queue.ndjson").exists()


def test_scheduler_dispatch_failure_is_immediate() -> None:
    with pytest.raises(RuntimeError, match="scheduler_dispatch_failed.*Forbidden"):
        ensure_submission_success(
            {
                "status": "dispatch_failed",
                "scheduler_dispatch": {
                    "status": "dispatch_failed",
                    "attempts": [{"http_status": 403, "error": "Forbidden"}],
                },
            }
        )


def test_task_failure_details_preserves_worker_traceback() -> None:
    detail, node_id = task_failure_details(
        {
            "error": "raytracer_fragment_failed",
            "error_type": "RuntimeError",
            "traceback": "Traceback (most recent call last):\n  worker.py:42\nRuntimeError: bad scene",
            "node_id": "worker-a",
        }
    )

    assert node_id == "worker-a"
    assert "RuntimeError: raytracer_fragment_failed" in detail
    assert "worker.py:42" in detail
    assert "RuntimeError: bad scene" in detail


def test_task_dispatch_attaches_hash_verified_network_inputs(tmp_path) -> None:
    scene = store_network_content(tmp_path, b"scene", "emitter")
    spec = store_network_content(tmp_path, b"spec", "emitter")

    payload = attach_network_content_blobs(
        tmp_path,
        {"p2p_ref": spec, "task": {"scene_p2p_ref": scene}},
    )

    blobs = {item["content_id"]: base64.b64decode(item["data_b64"]) for item in payload["content_blobs"]}
    assert blobs[spec["content_id"]] == b"spec"
    assert blobs[scene["content_id"]] == b"scene"


@pytest.mark.parametrize(
    "error",
    [
        "peer_content_not_found:abc",
        "unknown_peer_for_content:emitter",
        "missing network result after deadline: result.json",
        "connection reset by peer",
    ],
)
def test_transient_task_failures_are_retryable(error: str) -> None:
    assert is_transient_task_failure(error)


def test_late_successful_result_from_predecessor_wins_retry_race(tmp_path) -> None:
    late_task_id = "fragment-007"
    current_task_id = "fragment-007-compute-retry-02"
    expected = {"task_id": late_task_id, "success": True, "result_hash": "abc"}
    (tmp_path / f"result.{late_task_id}.json").write_text(json.dumps(expected), encoding="utf-8")

    resolved = poll_task_result_attempts(
        tmp_path,
        current_task_id,
        [late_task_id],
        deadline=float("inf"),
    )

    assert resolved == (late_task_id, expected)


def test_late_failed_result_does_not_override_current_attempt(tmp_path) -> None:
    late_task_id = "fragment-007"
    current_task_id = "fragment-007-compute-retry-02"
    (tmp_path / f"result.{late_task_id}.json").write_text(
        json.dumps({"task_id": late_task_id, "success": False}),
        encoding="utf-8",
    )

    assert (
        poll_task_result_attempts(
            tmp_path,
            current_task_id,
            [late_task_id],
            deadline=float("inf"),
        )
        is None
    )


def test_claim_starts_a_fresh_execution_deadline(tmp_path, monkeypatch) -> None:
    task_id = "fragment-007"
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / f"{task_id}.json").write_text(
        json.dumps({"task_id": task_id, "status": "running"}),
        encoding="utf-8",
    )
    token = {"task_id": task_id, "queue_deadline": 150.0}
    monkeypatch.setattr("workloads.raytracer.run_network_job.time.monotonic", lambda: 125.0)

    assert refresh_attempt_deadline(tmp_path, token, 300.0) == 425.0
    assert token["execution_deadline"] == 425.0


def test_automatic_in_flight_limit_tracks_discovered_role_capacity(tmp_path) -> None:
    peers = {
        "peers": [
            {"node_id": "compute-a", "roles": ["compute", "verify"], "http_base_url": "http://a"},
            {"node_id": "compute-b", "roles": ["compute"], "http_base_url": "http://b"},
            {"node_id": "storage", "roles": ["storage"], "http_base_url": "http://storage"},
            {"node_id": "offline", "roles": ["compute"], "http_base_url": ""},
        ]
    }
    (tmp_path / "node.orchestrator.peers.json").write_text(json.dumps(peers), encoding="utf-8")

    assert discovered_role_capacity(tmp_path, "orchestrator", "compute") == 2
    assert discovered_role_capacity(tmp_path, "orchestrator", "verify") == 1
    assert resolve_in_flight_limit(0, tmp_path, "orchestrator", "compute") == 2
    assert resolve_in_flight_limit(7, tmp_path, "orchestrator", "compute") == 7


def test_retry_allows_the_only_compatible_worker_to_reclaim() -> None:
    excluded, relaxed = retry_excluded_peer_ids(
        [],
        "only-worker",
        1,
        "peer_content_not_found:scene",
    )

    assert excluded == []
    assert relaxed is True


def test_retry_prefers_another_worker_when_capacity_exists() -> None:
    excluded, relaxed = retry_excluded_peer_ids(
        [],
        "failed-worker",
        2,
        "connection reset by peer",
    )

    assert excluded == ["failed-worker"]
    assert relaxed is False


def test_retry_relaxes_after_every_available_worker_failed() -> None:
    excluded, relaxed = retry_excluded_peer_ids(
        ["worker-a"],
        "worker-b",
        2,
        "connection reset by peer",
    )

    assert excluded == []
    assert relaxed is True


def test_wait_for_network_role_accepts_a_discovered_worker(tmp_path) -> None:
    peers = {
        "peers": [
            {"node_id": "compute-a", "roles": ["compute"], "http_base_url": "http://a"},
        ]
    }
    (tmp_path / "node.orchestrator.peers.json").write_text(json.dumps(peers), encoding="utf-8")

    wait_for_network_role(tmp_path, "orchestrator", "compute", timeout_s=1.0)


def test_fragment_pipeline_requeues_transient_compute_and_verify_failures() -> None:
    events: list[str] = []

    def launch_compute(_fragment):
        attempt = 1 + events.count("compute_launch")
        events.append("compute_launch")
        return {"attempt": attempt}

    def poll_compute(_fragment, token):
        if token["attempt"] == 1:
            return RetryFragmentStage("peer_content_not_found:input")
        return {"computed": True}

    def launch_verify(_fragment, _computed):
        attempt = 1 + events.count("verify_launch")
        events.append("verify_launch")
        return {"attempt": attempt}

    def poll_verify(_fragment, _computed, token):
        if token["attempt"] == 1:
            return RetryFragmentStage("connection reset")
        return {"verified": True}

    def finish_verify(_fragment, _computed, _token, verified):
        assert verified == {"verified": True}
        events.append("finished")

    run_bounded_fragment_pipeline(
        [{"index": 0}],
        max_compute_in_flight=1,
        max_verify_in_flight=1,
        launch_compute=launch_compute,
        poll_compute=poll_compute,
        launch_verify=launch_verify,
        poll_verify=poll_verify,
        finish_verify=finish_verify,
        idle=lambda: None,
    )

    assert events == ["compute_launch", "compute_launch", "verify_launch", "verify_launch", "finished"]


def test_fragment_pipeline_overlaps_compute_and_verification() -> None:
    tick = 0
    events: list[tuple[str, int, int, tuple[int, ...]]] = []
    active_compute: set[int] = set()
    active_verify: set[int] = set()
    compute_ready_at = {0: 1, 1: 6, 2: 3, 3: 4}
    max_compute_seen = 0
    max_verify_seen = 0

    def launch_compute(fragment: dict[str, int]) -> dict[str, int]:
        nonlocal max_compute_seen
        index = fragment["index"]
        active_compute.add(index)
        max_compute_seen = max(max_compute_seen, len(active_compute))
        events.append(("compute_started", index, tick, tuple(sorted(active_compute))))
        return {"ready_at": compute_ready_at[index]}

    def poll_compute(fragment: dict[str, int], token: dict[str, int]) -> dict[str, int] | None:
        index = fragment["index"]
        if tick < token["ready_at"]:
            return None
        active_compute.remove(index)
        events.append(("compute_finished", index, tick, tuple(sorted(active_compute))))
        return {"index": index}

    def launch_verify(fragment: dict[str, int], _computed: dict[str, int]) -> dict[str, int]:
        nonlocal max_verify_seen
        index = fragment["index"]
        active_verify.add(index)
        max_verify_seen = max(max_verify_seen, len(active_verify))
        events.append(("verify_started", index, tick, tuple(sorted(active_compute))))
        return {"ready_at": tick + 1}

    def poll_verify(
        fragment: dict[str, int],
        _computed: dict[str, int],
        token: dict[str, int],
    ) -> dict[str, bool] | None:
        if tick < token["ready_at"]:
            return None
        index = fragment["index"]
        active_verify.remove(index)
        return {"verified": True}

    def finish_verify(
        fragment: dict[str, int],
        _computed: dict[str, int],
        _token: dict[str, int],
        verified: dict[str, bool],
    ) -> None:
        assert verified["verified"] is True
        events.append(("verify_finished", fragment["index"], tick, tuple(sorted(active_compute))))

    def advance_clock() -> None:
        nonlocal tick
        tick += 1

    run_bounded_fragment_pipeline(
        [{"index": index} for index in range(4)],
        max_compute_in_flight=2,
        max_verify_in_flight=1,
        launch_compute=launch_compute,
        poll_compute=poll_compute,
        launch_verify=launch_verify,
        poll_verify=poll_verify,
        finish_verify=finish_verify,
        idle=advance_clock,
    )

    assert max_compute_seen == 2
    assert max_verify_seen == 1
    assert [(event[0], event[1]) for event in events[:2]] == [
        ("compute_started", 0),
        ("compute_started", 1),
    ]
    verify_zero = next(event for event in events if event[:2] == ("verify_finished", 0))
    compute_one = next(event for event in events if event[:2] == ("compute_finished", 1))
    assert verify_zero[2] < compute_one[2]
    assert verify_zero[3]
    assert sorted(event[1] for event in events if event[0] == "verify_finished") == [0, 1, 2, 3]


def test_fragment_validation_checks_format_dimensions_and_hash() -> None:
    ppm = _ppm(2, 1, bytes(range(6)))

    metadata = validate_fragment_ppm(
        ppm,
        task_id="fragment-000",
        expected_width=2,
        expected_height=1,
        expected_hash=sha256_bytes(ppm),
    )

    assert metadata == {"width": 2, "height": 1, "sha256": sha256_bytes(ppm), "valid_p6": True}
    with pytest.raises(RuntimeError, match="raytracer_fragment_invalid_ppm"):
        validate_fragment_ppm(
            b'{"role_result":"compute"}',
            task_id="fragment-json",
            expected_width=2,
            expected_height=1,
            expected_hash=sha256_bytes(b'{"role_result":"compute"}'),
        )


def test_reassembly_succeeds_when_optional_png_conversion_fails(tmp_path, monkeypatch) -> None:
    fragment = tmp_path / "fragment.ppm"
    fragment.write_bytes(_ppm(1, 1, bytes([1, 2, 3])))
    output = tmp_path / "render.ppm"
    png = tmp_path / "render.png"
    result_json = tmp_path / "reassemble.json"
    monkeypatch.setattr(
        raytracer_workload,
        "ppm_to_png_bytes",
        lambda _ppm_bytes: (_ for _ in ()).throw(ValueError("synthetic PNG failure")),
    )
    args = argparse.Namespace(
        output=str(output),
        fragment=[str(fragment)],
        x_start=["0"],
        y_start=["0"],
        png=str(png),
        result_json=str(result_json),
    )

    assert raytracer_workload.command_reassemble(args) == 0

    result = json.loads(result_json.read_text(encoding="utf-8"))
    assert output.exists()
    assert result["result_png_ready"] is False
    assert "synthetic PNG failure" in result["result_png_error"]
    assert result["result_png_path"] == ""
    assert not png.exists()


def test_reassembly_places_rectangular_tiles_without_ordering_them(tmp_path) -> None:
    right = tmp_path / "right.ppm"
    left = tmp_path / "left.ppm"
    right.write_bytes(_ppm(1, 2, bytes([20, 21, 22, 23, 24, 25])))
    left.write_bytes(_ppm(1, 2, bytes([1, 2, 3, 4, 5, 6])))
    output = tmp_path / "render.ppm"

    args = argparse.Namespace(
        output=str(output),
        fragment=[str(right), str(left)],
        x_start=["1", "0"],
        y_start=["0", "0"],
        png="",
        result_json="",
    )

    assert raytracer_workload.command_reassemble(args) == 0
    width, height, pixels = raytracer_workload.read_ppm(output)
    assert (width, height) == (2, 2)
    assert pixels == bytes([1, 2, 3, 20, 21, 22, 4, 5, 6, 23, 24, 25])


def test_ppm_parser_rejects_ascii_p3_and_corrupted_headers() -> None:
    # 1. ASCII P3 magic header rejection
    p3_ppm = b"P3\n1 1\n255\n255 0 0\n"
    with pytest.raises(ValueError, match="unsupported_ppm_magic"):
        raytracer_workload.parse_ppm_bytes(p3_ppm, "test-p3")

    # 2. Unsupported max_value (e.g. 65535 16-bit PPM)
    p6_16bit = b"P6\n1 1\n65535\n\x00\xff\x00\xff\x00\xff"
    with pytest.raises(ValueError, match="unsupported_ppm_max_value:65535"):
        raytracer_workload.parse_ppm_bytes(p6_16bit, "test-16bit")

    # 3. Truncated / invalid raster payload size
    truncated_ppm = b"P6\n2 2\n255\n" + bytes([1, 2, 3])
    with pytest.raises(ValueError, match="invalid_ppm_payload_size"):
        raytracer_workload.parse_ppm_bytes(truncated_ppm, "test-truncated")


def test_fragment_validation_rejects_dimension_and_hash_mismatches() -> None:
    ppm = _ppm(2, 2, bytes(range(12)))
    actual_hash = sha256_bytes(ppm)

    # 1. Dimension mismatch
    with pytest.raises(RuntimeError, match="raytracer_fragment_dimensions_mismatch"):
        validate_fragment_ppm(
            ppm,
            task_id="frag-dim-test",
            expected_width=2,
            expected_height=1,
            expected_hash=actual_hash,
        )

    # 2. Hash mismatch
    with pytest.raises(RuntimeError, match="raytracer_fragment_hash_mismatch"):
        validate_fragment_ppm(
            ppm,
            task_id="frag-hash-test",
            expected_width=2,
            expected_height=2,
            expected_hash="0" * 64,
        )
