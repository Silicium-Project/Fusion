"""Node-side handlers of the raytracer workloads (referenced by the manifests
`calcul/rendering/raytracer-fragment` and
`verification/rendering/raytracer-fragment`).

A compute node renders one tile with the native renderer; a verifier node
re-renders one randomly challenged milestone of a tile and compares pixel
hashes. The whole-job orchestration (split, challenges, reassembly) is in
`run_network_job.py`.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from workloads.common import (
    RAYTRACER_PERFORMANCE_SCHEMA,
    last_json_object,
    performance_duration,
    performance_ratio,
    sha256_bytes,
    sha256_json,
)
from workloads.raytracer import native
from workloads.raytracer.raytracer_workload import run_raytracer
from workloads.registry import WorkloadContext


def _require(ctx: WorkloadContext) -> None:
    if ctx.fetch is None or ctx.run_process is None:
        raise RuntimeError("raytracer_workload_requires_node_runtime")


def compute_fragment(ctx: WorkloadContext) -> dict[str, Any]:
    """Render the tile described by the task / fragment spec and publish it."""
    _require(ctx)
    task, p2p_data, p2p_meta = ctx.task, ctx.p2p_data, ctx.p2p_meta
    fragment_started = time.perf_counter()
    try:
        spec = json.loads(p2p_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"raytracer_fragment_spec_invalid:{exc}") from exc
    if not isinstance(spec, dict):
        raise RuntimeError("raytracer_fragment_spec_invalid")
    scene_ref = task.get("scene_p2p_ref") or spec.get("scene_p2p_ref")
    if not isinstance(scene_ref, dict):
        raise RuntimeError("raytracer_scene_ref_missing")
    scene_fetch_started = time.perf_counter()
    scene_bytes, scene_meta = ctx.fetch(scene_ref)
    scene_fetch_ms = performance_duration((time.perf_counter() - scene_fetch_started) * 1000.0)
    compute_script = Path(__file__).resolve().parent / "compute.py"
    with tempfile.TemporaryDirectory(prefix="silicium-raytracer-fragment-") as temp_dir:
        temp_path = Path(temp_dir)
        scene_path = temp_path / "scene.cfg"
        output_path = temp_path / "fragment.ppm"
        staging_started = time.perf_counter()
        scene_path.write_bytes(scene_bytes)
        staging_ms = performance_duration((time.perf_counter() - staging_started) * 1000.0)
        x_start = int(task.get("x_start", spec.get("x_start", 0)) or 0)
        x_end = int(task.get("x_end", spec.get("x_end", 0)) or 0)
        if x_end <= x_start:
            x_end = native.scene_resolution(scene_path)[0]
        command = [
            sys.executable,
            str(compute_script),
            "--scene", str(scene_path),
            "--output", str(output_path),
            "--x-start", str(x_start),
            "--x-end", str(x_end),
            "--y-start", str(int(task.get("y_start", spec.get("y_start", 0)) or 0)),
            "--y-end", str(int(task.get("y_end", spec.get("y_end", 0)) or 0)),
            "--verification-batch-rows", str(int(task.get("verification_batch_rows", spec.get("verification_batch_rows", 20)) or 20)),
            "--timeout-s", str(int(task.get("timeout_s", 300) or 300)),
        ]
        progress_file = str(task.get("_runtime_progress_path", "")).strip()
        if progress_file:
            command.extend(["--progress-file", progress_file])
        compute_started_unix_ms = int(time.time() * 1000)
        compute_started = time.perf_counter()
        completed = ctx.run_process(command, timeout=int(task.get("timeout_s", 300) or 300) + 15)
        compute_process_ms = performance_duration((time.perf_counter() - compute_started) * 1000.0)
        compute_finished_unix_ms = int(time.time() * 1000)
        if completed.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"raytracer_fragment_failed:exit={completed.returncode}:stderr={completed.stderr[-2048:]}")
        output = output_path.read_bytes()
        renderer_result = last_json_object(completed.stdout)
    if not output.startswith(b"P6\n"):
        raise RuntimeError("raytracer_fragment_invalid_ppm")
    renderer_performance = renderer_result.get("performance") if isinstance(renderer_result.get("performance"), dict) else {}
    compute_ms = performance_duration(renderer_performance.get("compute_ms"))
    if compute_ms <= 0:
        compute_ms = performance_duration(renderer_result.get("renderer_duration_ms")) or compute_process_ms
    output_store_started = time.perf_counter()
    output_ref = ctx.put_output(output)
    output_store_ms = performance_duration((time.perf_counter() - output_store_started) * 1000.0)
    fragment_total_ms = performance_duration((time.perf_counter() - fragment_started) * 1000.0)
    overhead_ms = performance_duration(max(0.0, fragment_total_ms - compute_ms))
    fragment_performance = {
        "schema": RAYTRACER_PERFORMANCE_SCHEMA,
        "total_ms": fragment_total_ms,
        "compute_ms": compute_ms,
        "network_ms": scene_fetch_ms,
        "overhead_ms": overhead_ms,
        "compute_to_total_ratio": performance_ratio(compute_ms, fragment_total_ms),
        "compute_to_network_ratio": performance_ratio(compute_ms, scene_fetch_ms),
        "compute_started_unix_ms": compute_started_unix_ms,
        "compute_finished_unix_ms": compute_finished_unix_ms,
        "stages_ms": {
            "scene_fetch": scene_fetch_ms,
            "input_staging": staging_ms,
            "compute_process": compute_process_ms,
            "output_store": output_store_ms,
        },
        "scene_fetch_source": str(scene_meta.get("source", "")),
    }
    result_hash = sha256_bytes(output)
    # compute.py already committed to the milestones of this exact output.
    milestone_manifest = renderer_result.get("verification_milestones")
    if not isinstance(milestone_manifest, dict):
        raise RuntimeError("raytracer_fragment_milestones_missing")
    return {
        "role_result": "compute",
        "input": p2p_meta,
        "scene": scene_meta,
        "input_hash": sha256_bytes(p2p_data),
        "compute": {"mode": "raytracer-fragment", "executed": True, "stdout": completed.stdout[-2048:], "stderr": completed.stderr[-2048:]},
        "performance": fragment_performance,
        "output_ref": output_ref,
        "proof_ref": output_ref,
        "result_hash": result_hash,
        "verification_milestones": milestone_manifest,
    }


def verify_fragment_milestone(ctx: WorkloadContext) -> dict[str, Any]:
    """Re-render the challenged milestone rows and compare their pixel hash."""
    _require(ctx)
    task, p2p_data, p2p_meta = ctx.task, ctx.p2p_data, ctx.p2p_meta
    verification_started = time.perf_counter()
    try:
        challenge = json.loads(p2p_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"raytracer_verification_challenge_invalid:{exc}") from exc
    supported_strategies = {"random-row-milestone-v1", "random-tile-row-milestone-v2"}
    if not isinstance(challenge, dict) or challenge.get("strategy") not in supported_strategies:
        raise RuntimeError("raytracer_verification_challenge_invalid")

    sample = challenge.get("milestone")
    if not isinstance(sample, dict):
        raise RuntimeError("raytracer_verification_milestone_missing")
    y_start = int(sample.get("y_start", -1))
    y_end = int(sample.get("y_end", -1))
    x_start = int(sample.get("x_start", 0))
    x_end = int(sample.get("x_end", 0))
    sample_rows = y_end - y_start
    max_sample_rows = max(1, int(task.get("max_sample_rows", 256) or 256))
    if y_start < 0 or x_start < 0 or sample_rows <= 0 or sample_rows > max_sample_rows:
        raise RuntimeError("raytracer_verification_milestone_range_invalid")
    expected = str(sample.get("pixel_sha256", "")).removeprefix("sha256:").lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise RuntimeError("raytracer_verification_milestone_hash_invalid")

    scene_ref = task.get("scene_p2p_ref") or challenge.get("scene_p2p_ref")
    if not isinstance(scene_ref, dict):
        raise RuntimeError("raytracer_scene_ref_missing")
    scene_fetch_started = time.perf_counter()
    scene_bytes, scene_meta = ctx.fetch(scene_ref)
    scene_fetch_ms = performance_duration((time.perf_counter() - scene_fetch_started) * 1000.0)
    source_output_ref = task.get("source_output_ref")
    handoff_meta: dict[str, Any] = {}
    source_handoff_ms = 0.0
    if isinstance(source_output_ref, dict):
        source_handoff_started = time.perf_counter()
        source_output, handoff_meta = ctx.fetch(source_output_ref)
        source_handoff_ms = performance_duration((time.perf_counter() - source_handoff_started) * 1000.0)
        source_manifest = native.build_milestones(
            source_output,
            int(task.get("y_start", 0) or 0),
            max(1, int(task.get("max_sample_rows", 20) or 20)),
            int(task.get("x_start", 0) or 0),
        )
        if str(source_manifest.get("commitment_hash", "")) != str(challenge.get("commitment_hash", "")):
            raise RuntimeError("raytracer_source_handoff_commitment_invalid")
    with tempfile.TemporaryDirectory(prefix="silicium-raytracer-milestone-verify-") as temp_dir:
        temp_path = Path(temp_dir)
        scene_path = temp_path / "scene.cfg"
        output_path = temp_path / "sample.ppm"
        scene_path.write_bytes(scene_bytes)
        if x_end <= x_start and challenge.get("strategy") == "random-row-milestone-v1":
            x_end = native.scene_resolution(scene_path)[0]
        if x_end <= x_start:
            raise RuntimeError("raytracer_verification_milestone_range_invalid")
        recomputed = run_raytracer(
            scene_path,
            output_path,
            int(task.get("timeout_s", 300) or 300),
            y_start,
            y_end,
            x_start,
            x_end,
        )
        recomputed_hash = native.pixel_sha256(output_path.read_bytes())

    passed = recomputed_hash == expected
    recompute_performance = recomputed.get("performance") if isinstance(recomputed.get("performance"), dict) else {}
    compute_ms = performance_duration(recompute_performance.get("compute_ms"))
    total_ms = performance_duration((time.perf_counter() - verification_started) * 1000.0)
    network_ms = performance_duration(scene_fetch_ms + source_handoff_ms)
    overhead_ms = performance_duration(max(0.0, total_ms - compute_ms))
    fragment_rows = max(sample_rows, int(challenge.get("fragment_rows", sample_rows) or sample_rows))
    verification = {
        "mode": str(challenge.get("strategy")),
        "challenge_nonce": str(challenge.get("challenge_nonce", "")),
        "commitment_hash": str(challenge.get("commitment_hash", "")),
        "milestone_index": int(sample.get("index", 0) or 0),
        "milestone_count": int(challenge.get("milestone_count", 1) or 1),
        "sample_y_start": y_start,
        "sample_y_end": y_end,
        "sample_x_start": x_start,
        "sample_x_end": x_end,
        "sample_rows": sample_rows,
        "fragment_rows": fragment_rows,
        "sample_ratio": sample_rows / fragment_rows,
        "expected_pixel_hash": expected,
        "recomputed_pixel_hash": recomputed_hash,
    }
    return {
        "role_result": "verify",
        "input": p2p_meta,
        "scene": scene_meta,
        "source_handoff": {
            **handoff_meta,
            "source_node_id": str(task.get("source_node_id", "")),
            "direct": bool(handoff_meta),
        },
        "input_hash": sha256_bytes(p2p_data),
        "expected_hash": expected,
        "recomputed_hash": recomputed_hash,
        "verification_mode": str(challenge.get("strategy")),
        "verification": verification,
        "verified": passed,
        "choice": passed,
        "result_hash": sha256_json({"verified": passed, **verification}),
        "performance": {
            "schema": RAYTRACER_PERFORMANCE_SCHEMA,
            "total_ms": total_ms,
            "compute_ms": compute_ms,
            "network_ms": network_ms,
            "overhead_ms": overhead_ms,
            "compute_to_total_ratio": performance_ratio(compute_ms, total_ms),
            "compute_to_network_ratio": performance_ratio(compute_ms, network_ms),
            "stages_ms": {
                "scene_fetch": scene_fetch_ms,
                "source_handoff_fetch": source_handoff_ms,
                "compute_process": performance_duration(recompute_performance.get("process_ms")),
            },
            "scene_fetch_source": str(scene_meta.get("source", "")),
            "source_handoff_source": str(handoff_meta.get("source", "")),
        },
    }
