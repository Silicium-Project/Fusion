"""Performance accounting of a raytracer job.

Builds one record per compute/verify task (orchestrator-side timings merged
with what the worker reported) and the job-level summary written to the
progress and summary JSON (`performance` field, schema
`silicium.raytracer-performance.v1`).
"""
from __future__ import annotations

import time
from typing import Any, Iterable

from workloads.common import performance_duration, performance_ratio
from workloads.raytracer.orchestrator.constants import RAYTRACER_PERFORMANCE_SCHEMA


def merge_compute_intervals(records: Iterable[dict[str, Any]]) -> float:
    """Total length of the union of the workers' renderer intervals (ms).

    Parallel work is counted once, so this is the wall time spent rendering.
    """
    intervals: list[tuple[float, float]] = []
    for record in records:
        start = performance_duration(record.get("compute_started_unix_ms"))
        finish = performance_duration(record.get("compute_finished_unix_ms"))
        if start > 0 and finish > start:
            intervals.append((start, finish))
    if not intervals:
        return 0.0
    intervals.sort()
    merged_start, merged_finish = intervals[0]
    total = 0.0
    for start, finish in intervals[1:]:
        if start <= merged_finish:
            merged_finish = max(merged_finish, finish)
            continue
        total += merged_finish - merged_start
        merged_start, merged_finish = start, finish
    return performance_duration(total + merged_finish - merged_start)


def build_performance_summary(records: Iterable[dict[str, Any]], total_ms: float) -> dict[str, Any]:
    """Job-level performance summary from the per-task records."""
    measured = [record for record in records if isinstance(record, dict)]
    compute_records = [record for record in measured if str(record.get("role", "")) == "compute"]
    verify_records = [record for record in measured if str(record.get("role", "")) == "verify"]
    compute_work_ms = performance_duration(sum(performance_duration(item.get("compute_ms")) for item in compute_records))
    verification_work_ms = performance_duration(sum(performance_duration(item.get("compute_ms")) for item in verify_records))
    compute_wall_ms = merge_compute_intervals(compute_records)
    if compute_wall_ms <= 0 and compute_records:
        compute_wall_ms = performance_duration(max(performance_duration(item.get("compute_ms")) for item in compute_records))
    total_wall_ms = performance_duration(total_ms)
    compute_wall_ms = performance_duration(min(total_wall_ms, compute_wall_ms))
    network_ms = performance_duration(sum(performance_duration(item.get("network_ms")) for item in measured))
    worker_overhead_ms = performance_duration(sum(performance_duration(item.get("worker_overhead_ms")) for item in measured))
    return {
        "schema": RAYTRACER_PERFORMANCE_SCHEMA,
        "total_ms": total_wall_ms,
        "compute_ms": compute_wall_ms,
        "compute_work_ms": compute_work_ms,
        "verification_ms": verification_work_ms,
        "network_ms": network_ms,
        "overhead_ms": performance_duration(max(0.0, total_wall_ms - compute_wall_ms)),
        "worker_overhead_ms": worker_overhead_ms,
        "compute_to_total_ratio": performance_ratio(compute_wall_ms, total_wall_ms),
        "compute_to_network_ratio": performance_ratio(compute_work_ms, network_ms),
        "parallelism_factor": performance_ratio(compute_work_ms, compute_wall_ms),
        "measured_compute_tasks": len(compute_records),
        "measured_verify_tasks": len(verify_records),
        "definition": {
            "total_ms": "wall time from workload start to assembled result",
            "compute_ms": "union of renderer intervals on compute workers; parallel work is counted once",
            "compute_work_ms": "sum of renderer time across compute workers",
            "network_ms": "dispatch, queue/result wait and artifact fetch outside the worker; verification is included",
        },
    }


def record_result_wait(token: dict[str, Any]) -> None:
    """Store in `token["result_wait_ms"]` the time since the task was queued."""
    result_wait_started = token.get("result_wait_started")
    if result_wait_started is not None:
        try:
            token["result_wait_ms"] = performance_duration(
                (time.perf_counter() - float(result_wait_started)) * 1000.0
            )
        except (TypeError, ValueError):
            token["result_wait_ms"] = 0.0


def orchestration_performance_record(
    role: str,
    context: dict[str, Any],
    token: dict[str, Any],
    result: dict[str, Any],
    *,
    artifact_fetch_ms: float = 0.0,
) -> dict[str, Any]:
    """Performance record of one compute or verify task.

    Network time is what the orchestrator waited beyond the worker's own
    total (dispatch, queue, result wait, artifact fetch) plus the network
    time the worker reported.
    """
    worker_performance = result.get("performance") if isinstance(result.get("performance"), dict) else {}
    worker_total_ms = performance_duration(
        worker_performance.get("workload_total_ms")
        or worker_performance.get("total_ms")
        or result.get("duration_ms")
    )
    compute_ms = performance_duration(worker_performance.get("compute_ms"))
    worker_network_ms = performance_duration(
        worker_performance.get("worker_network_ms")
        or worker_performance.get("network_ms")
    )
    worker_overhead_ms = performance_duration(
        worker_performance.get("workload_overhead_ms")
        or worker_performance.get("overhead_ms")
    )
    dispatch_ms = performance_duration(token.get("dispatch_ms"))
    result_wait_ms = performance_duration(token.get("result_wait_ms"))
    artifact_fetch_ms = performance_duration(artifact_fetch_ms)
    external_network_ms = performance_duration(
        dispatch_ms + max(0.0, result_wait_ms - worker_total_ms) + artifact_fetch_ms
    )
    total_ms = performance_duration(dispatch_ms + result_wait_ms + artifact_fetch_ms)
    network_ms = performance_duration(external_network_ms + worker_network_ms)
    record = {
        "schema": RAYTRACER_PERFORMANCE_SCHEMA,
        "role": role,
        "fragment_index": int(context["index"]),
        "task_id": str(token.get("resolved_task_id") or token.get("task_id") or ""),
        "node_id": str(result.get("node_id", "")),
        "total_ms": total_ms,
        "compute_ms": compute_ms,
        "network_ms": network_ms,
        "external_network_ms": external_network_ms,
        "worker_total_ms": worker_total_ms,
        "worker_network_ms": worker_network_ms,
        "worker_overhead_ms": worker_overhead_ms,
        "dispatch_ms": dispatch_ms,
        "result_wait_ms": result_wait_ms,
        "artifact_fetch_ms": artifact_fetch_ms,
        "overhead_ms": performance_duration(max(0.0, total_ms - compute_ms)),
        "compute_to_total_ratio": performance_ratio(compute_ms, total_ms),
        "compute_to_network_ratio": performance_ratio(compute_ms, network_ms),
        "compute_started_unix_ms": performance_duration(worker_performance.get("compute_started_unix_ms")),
        "compute_finished_unix_ms": performance_duration(worker_performance.get("compute_finished_unix_ms")),
    }
    return record
