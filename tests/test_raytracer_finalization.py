from __future__ import annotations

import argparse
import json

import pytest

from workloads.common import ppm_to_png_bytes, sha256_bytes
from workloads.raytracer import raytracer_workload
from workloads.raytracer.run_network_job import (
    ensure_submission_success,
    ensure_raytracer_compute_contract,
    run_bounded_fragment_pipeline,
    submit_network_task,
    validate_fragment_ppm,
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

    assert metadata == {"width": 2, "height": 1, "sha256": sha256_bytes(ppm)}
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
