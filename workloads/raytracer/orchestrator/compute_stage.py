"""Compute stage of a fragment: dispatch the tile render, check and store the result.

A compute result is accepted only if the worker ran the raytracer fragment
renderer, signed a valid receipt, returned a tile whose size and hash match,
and committed exactly the milestones the native pipeline recomputes from the
tile. The tile (PPM) and its PNG preview are written to `<job>/fragments/`.
"""
from __future__ import annotations

import json
import time
from typing import Any

from workloads.common import output_ref_from_compute, performance_duration, result_hash_from_compute
from workloads.raytracer import native
from workloads.raytracer.orchestrator.constants import (
    RAYTRACER_FASTPATH_FEATURE,
    RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD,
)
from workloads.raytracer.orchestrator.content_refs import bytes_input_ref, read_ref_bytes
from workloads.raytracer.orchestrator.failures import ensure_raytracer_compute_contract, ensure_task_success
from workloads.raytracer.orchestrator.job_state import JobState
from workloads.raytracer.orchestrator.performance import orchestration_performance_record
from workloads.raytracer.orchestrator.pipeline import RetryFragmentStage
from workloads.raytracer.orchestrator.receipts import validate_compute_receipt
from workloads.raytracer.orchestrator.stage_common import (
    poll_stage_attempt,
    register_stage_result,
    retry_failed_result,
    submit_stage_task,
)


def launch_compute(state: JobState, context: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a new compute attempt of the fragment and return its polling token."""
    args = state.args
    index = int(context["index"])
    fragment_id = str(context["fragment_id"])
    attempt = int(context.get("compute_attempt", 0)) + 1
    context["compute_attempt"] = attempt
    task_id = fragment_id if attempt == 1 else f"{fragment_id}-compute-retry-{attempt:02d}"
    spec = _compute_spec(state, context)
    state.progress_fragments[index].update(
        {
            "status": "queued_compute",
            "compute_attempt": attempt,
            "compute_max_attempts": max(1, int(args.max_compute_attempts)),
        }
    )
    dispatch_started = time.perf_counter()
    compute_payload = _compute_payload(state, context, task_id, spec)
    submit_stage_task(state, compute_payload, index, "compute")
    dispatch_ms = performance_duration((time.perf_counter() - dispatch_started) * 1000.0)
    state.write_progress("compute_queued")
    return {
        "task_id": task_id,
        "attempt": attempt,
        "queue_deadline": time.monotonic() + args.result_timeout_s,
        "dispatch_ms": dispatch_ms,
        "result_wait_started": time.perf_counter(),
    }


def _compute_spec(state: JobState, context: dict[str, Any]) -> dict[str, Any]:
    """Tile description sent to the worker (also stored as the task's p2p input)."""
    return {
        "fragment_index": int(context["index"]),
        "fragment_count": len(state.fragments),
        "x_start": int(context["x_start"]),
        "x_end": int(context["x_end"]),
        "y_start": int(context["y_start"]),
        "y_end": int(context["y_end"]),
        "scene_p2p_ref": state.scene_ref,
        "verification_batch_rows": max(1, int(state.args.verification_batch_rows)),
    }


def _compute_payload(
    state: JobState,
    context: dict[str, Any],
    task_id: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Scheduler envelope of a compute task."""
    args = state.args
    return {
        "task_id": task_id,
        "required_roles": ["compute"],
        # Do not send latency-sensitive tiles to a legacy worker
        # whose renderer progress writes serialize the pixel loop.
        "required_features": [RAYTRACER_FASTPATH_FEATURE],
        "priority": args.priority,
        "excluded_peer_ids": list(context.get("compute_excluded_peer_ids", [])),
        "p2p_ref": bytes_input_ref(args, state.export_dir, json.dumps(spec, sort_keys=True).encode("utf-8")),
        "task": {
            "kind": "compute",
            "workload": RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD,
            "required_features": [RAYTRACER_FASTPATH_FEATURE],
            "inline_input": spec,
            "fragment_index": int(context["index"]),
            "fragment_count": len(state.fragments),
            "x_start": int(context["x_start"]),
            "x_end": int(context["x_end"]),
            "y_start": int(context["y_start"]),
            "y_end": int(context["y_end"]),
            "verification_batch_rows": max(1, int(args.verification_batch_rows)),
            "scene_p2p_ref": state.scene_ref,
            "timeout_s": int(args.node_timeout_s),
            "root_job_id": state.job_id,
        },
    }


def poll_compute(
    state: JobState,
    context: dict[str, Any],
    token: dict[str, Any],
) -> dict[str, Any] | RetryFragmentStage | None:
    """Poll a compute attempt; on a result, validate it and store the tile.

    Returns the `computed` record handed to the verify stage, None while
    waiting, or a RetryFragmentStage.
    """
    resolved = poll_stage_attempt(state, context, token, "compute")
    if resolved is None or isinstance(resolved, RetryFragmentStage):
        return resolved
    resolved_task_id, compute_result = resolved
    register_stage_result(state, token, "compute", resolved_task_id, compute_result)
    retry = retry_failed_result(state, context, token, "compute", compute_result)
    if retry is not None:
        return retry
    try:
        checked = _check_compute_result(state, context, compute_result, resolved_task_id)
    except Exception as error:
        state.fail_fragment(int(context["index"]), "compute_failed", error)
        raise
    compute_performance = orchestration_performance_record(
        "compute",
        context,
        token,
        compute_result,
        artifact_fetch_ms=checked["artifact_fetch_ms"],
    )
    state.record_performance(compute_performance)
    preview = _store_fragment(state, context, checked["fragment_bytes"])
    _mark_computed(state, context, checked, preview, compute_performance)
    state.write_progress("fragment_computed")
    return {
        "compute_result": compute_result,
        "compute_task_id": resolved_task_id,
        "expected_milestones": checked["expected_milestones"],
        "result_hash": checked["result_hash"],
        "output_ref": checked["output_ref"],
        "compute_receipt": checked["compute_receipt"],
    }


def _check_compute_result(
    state: JobState,
    context: dict[str, Any],
    compute_result: dict[str, Any],
    resolved_task_id: str,
) -> dict[str, Any]:
    """Validate a compute result and fetch its tile; any failure raises."""
    x_start = int(context["x_start"])
    x_end = int(context["x_end"])
    y_start = int(context["y_start"])
    y_end = int(context["y_end"])
    ensure_task_success(compute_result, resolved_task_id)
    ensure_raytracer_compute_contract(compute_result, resolved_task_id)
    compute_receipt = validate_compute_receipt(compute_result, resolved_task_id)
    output_ref = output_ref_from_compute(compute_result)
    result_hash = result_hash_from_compute(compute_result)
    artifact_fetch_started = time.perf_counter()
    fragment_bytes = read_ref_bytes(state.args, state.export_dir, output_ref)
    artifact_fetch_ms = performance_duration((time.perf_counter() - artifact_fetch_started) * 1000.0)
    fragment_metadata = native.validate_fragment(
        fragment_bytes,
        task_id=resolved_task_id,
        expected_width=x_end - x_start,
        expected_height=y_end - y_start,
        expected_hash=result_hash,
    )
    # The worker's milestone commitment must equal the one recomputed from
    # the returned tile, otherwise the verify challenge would be meaningless.
    worker_milestones = compute_result.get("verification_milestones")
    expected_milestones = native.build_milestones(
        fragment_bytes,
        y_start,
        max(1, int(state.args.verification_batch_rows)),
        x_start,
    )
    if worker_milestones != expected_milestones:
        raise RuntimeError("raytracer_milestone_commitment_invalid")
    return {
        "compute_receipt": compute_receipt,
        "output_ref": output_ref,
        "result_hash": result_hash,
        "fragment_bytes": fragment_bytes,
        "artifact_fetch_ms": artifact_fetch_ms,
        "fragment_metadata": fragment_metadata,
        "expected_milestones": expected_milestones,
    }


def _store_fragment(state: JobState, context: dict[str, Any], fragment_bytes: bytes) -> dict[str, Any]:
    """Write `fragment-NNN.ppm` and its PNG preview; queue the tile for reassembly."""
    index = int(context["index"])
    fragment_file = state.fragments_dir / f"fragment-{index:03d}.ppm"
    fragment_png = state.fragments_dir / f"fragment-{index:03d}.png"
    fragment_file.write_bytes(fragment_bytes)
    preview = native.write_png(fragment_bytes, fragment_png)
    state.fragment_files.append((int(context["x_start"]), int(context["y_start"]), fragment_file))
    return preview


def _mark_computed(
    state: JobState,
    context: dict[str, Any],
    checked: dict[str, Any],
    preview: dict[str, Any],
    compute_performance: dict[str, Any],
) -> None:
    """Record the accepted compute result in the fragment's progress entry."""
    result_hash = checked["result_hash"]
    output_ref = checked["output_ref"]
    expected_milestones = checked["expected_milestones"]
    compute_receipt = checked["compute_receipt"]
    fragment_metadata = checked["fragment_metadata"]
    state.progress_fragments[int(context["index"])].update(
        {
            "status": "computed",
            "preview_ready": preview["ready"],
            "preview_path": preview["path"],
            "preview_error": preview["error"],
            "fragment_width": fragment_metadata["width"],
            "fragment_height": fragment_metadata["height"],
            "result_hash": result_hash,
            "output_ref": output_ref,
            "expected_hash": result_hash,
            "compute_result_hash": result_hash,
            "compute_output_ref": output_ref,
            "verification_mode": expected_milestones["strategy"],
            "verification_commitment_hash": expected_milestones["commitment_hash"],
            "verification_milestone_count": expected_milestones["milestone_count"],
            "compute_receipt_hash": compute_receipt["receipt_hash"],
            "compute_billable_work_units": int(compute_receipt.get("billable_work_units", 0) or 0),
            "performance": compute_performance,
        }
    )
