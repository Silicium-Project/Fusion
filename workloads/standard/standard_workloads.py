"""Shared helpers of the built-in CPU workloads.

The handlers themselves are in `handlers.py` and are referenced by the
manifests (`runtime.handler`). `run_standard_workload` is kept for callers
that run a built-in workload directly (tests, `python -m workloads.standard.run`).
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from typing import Any


STANDARD_PERFORMANCE_SCHEMA = "silicium.standard-workload-performance.v1"
MAX_MATRIX_DIMENSION = 256
MAX_MONTE_CARLO_ITERATIONS = 5_000_000


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_json(data: bytes, *, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}_json_invalid:{exc}") from exc


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label}_must_be_numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}_must_be_numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label}_must_be_finite")
    return result


def _bounded_int(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}_must_be_integer") from exc
    if result < minimum or result > maximum:
        raise ValueError(f"{label}_out_of_range:{minimum}:{maximum}")
    return result


def _matrix(value: Any, *, label: str) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}_must_be_non_empty_matrix")
    if len(value) > MAX_MATRIX_DIMENSION:
        raise ValueError(f"{label}_too_many_rows")
    result: list[list[float]] = []
    width = 0
    for row in value:
        if not isinstance(row, list) or not row:
            raise ValueError(f"{label}_rows_must_be_non_empty_arrays")
        if len(row) > MAX_MATRIX_DIMENSION:
            raise ValueError(f"{label}_too_many_columns")
        numbers = [_number(item, label=f"{label}_value") for item in row]
        if not width:
            width = len(numbers)
        if len(numbers) != width:
            raise ValueError(f"{label}_must_be_rectangular")
        result.append(numbers)
    return result


def _matrix_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    if len(left[0]) != len(right):
        raise ValueError("matrix_dimensions_incompatible")
    right_columns = list(zip(*right))
    return [
        [sum(left_value * right_value for left_value, right_value in zip(row, column)) for column in right_columns]
        for row in left
    ]


def _output_result(
    *,
    workload: str,
    task: Mapping[str, Any],
    p2p_data: bytes,
    p2p_meta: Mapping[str, Any],
    result: Mapping[str, Any],
    work_units: int,
    unit: str,
    put_output: Callable[[bytes], dict[str, Any]],
    started: float,
) -> dict[str, Any]:
    output_bytes = (_stable_json(dict(result)) + "\n").encode("utf-8")
    output_ref = put_output(output_bytes)
    total_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "role_result": "compute",
        "input": dict(p2p_meta),
        "input_hash": _sha256(p2p_data),
        "compute": {
            "mode": "standard-python",
            "executed": True,
            "workload": workload,
            "work_units": work_units,
            "unit": unit,
        },
        "workload_result": dict(result),
        "performance": {
            "schema": STANDARD_PERFORMANCE_SCHEMA,
            "total_ms": total_ms,
            "compute_ms": total_ms,
            "network_ms": 0.0,
            "overhead_ms": 0.0,
            "work_units": work_units,
            "unit": unit,
        },
        "output_ref": output_ref,
        "proof_ref": output_ref,
        "result_hash": _sha256(output_bytes),
        "task_parameters": {
            key: task[key]
            for key in ("seed", "iterations", "max_iterations")
            if key in task
        },
    }


def run_standard_workload(
    workload: str,
    task: Mapping[str, Any],
    p2p_data: bytes,
    p2p_meta: Mapping[str, Any],
    put_output: Callable[[bytes], dict[str, Any]],
) -> dict[str, Any] | None:
    """Execute a built-in compute workload, returning ``None`` for other IDs.

    Dispatch goes through the workload registry; only handlers of this package
    are considered, so external or node-level workloads are left to the caller.
    """
    from workloads.registry import default_registry, run_workload

    spec = default_registry().get(workload)
    if spec is None or not (spec.handler_ref or "").startswith("workloads.standard."):
        return None
    return run_workload(
        workload,
        "compute",
        {"task": task, "p2p_data": p2p_data, "p2p_meta": p2p_meta, "put_output": put_output},
    )
