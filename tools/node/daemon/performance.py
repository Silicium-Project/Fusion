"""Performance block attached to every task result (timings and resource usage)."""

from __future__ import annotations

import time
from typing import Any

from workloads.common import performance_duration, performance_ratio


def build_task_performance(
    result: dict[str, Any],
    duration_ms: int,
    started_unix_ms: int,
    start_telemetry: dict[str, Any],
    end_telemetry: dict[str, Any],
) -> dict[str, Any]:
    """Merge the workload's own ``performance`` with node-side measurements.

    Node-side wall time (``duration_ms``/``total_ms``) overrides the
    workload's ``total_ms``, which is kept as ``workload_total_ms``.
    ``finished_unix_ms`` is taken when this function runs.
    """
    role_performance = result.get("performance") if isinstance(result.get("performance"), dict) else {}
    workload_total_ms = performance_duration(role_performance.get("total_ms"))
    finished_unix_ms = int(time.time() * 1000)
    role_schema = str(role_performance.get("schema", "")).strip()
    role_overhead_ms = performance_duration(role_performance.get("overhead_ms"))
    role_network_ms = performance_duration(role_performance.get("network_ms"))
    performance = {
        **role_performance,
        "schema": role_schema or "silicium.task-performance.v1",
        "duration_ms": duration_ms,
        "total_ms": duration_ms,
        "started_unix_ms": started_unix_ms,
        "finished_unix_ms": finished_unix_ms,
        "process_cpu_seconds": round(
            max(
                0.0,
                float(end_telemetry.get("process_cpu_seconds", 0.0) or 0.0)
                - float(start_telemetry.get("process_cpu_seconds", 0.0) or 0.0),
            ),
            3,
        ),
        "process_peak_rss_bytes": int(end_telemetry.get("process_peak_rss_bytes", 0) or 0),
        "system_cpu_percent": float(end_telemetry.get("system_cpu_percent", 0.0) or 0.0),
        "system_memory_percent": float(end_telemetry.get("system_memory_percent", 0.0) or 0.0),
        "logical_cpu_count": int(end_telemetry.get("logical_cpu_count", 0) or 0),
    }
    if workload_total_ms > 0:
        performance["workload_total_ms"] = workload_total_ms
    if role_overhead_ms > 0:
        performance["workload_overhead_ms"] = role_overhead_ms
    if role_network_ms > 0:
        performance["worker_network_ms"] = role_network_ms
    compute_ms = performance_duration(performance.get("compute_ms"))
    if compute_ms > 0:
        performance["compute_ms"] = compute_ms
        performance["overhead_ms"] = performance_duration(max(0.0, duration_ms - compute_ms))
        performance["compute_to_total_ratio"] = performance_ratio(compute_ms, float(duration_ms))
        network_ms = performance_duration(performance.get("network_ms"))
        if network_ms > 0:
            performance["compute_to_network_ratio"] = performance_ratio(compute_ms, network_ms)
    return performance
