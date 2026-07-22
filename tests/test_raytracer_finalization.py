from __future__ import annotations

import argparse
import json

import pytest

from workloads.common import ppm_to_png_bytes, sha256_bytes
from workloads.raytracer import raytracer_workload
from workloads.raytracer.run_network_job import (
    ensure_submission_success,
    ensure_raytracer_compute_contract,
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
