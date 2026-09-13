"""Built-in CPU workloads used by the network and its load tests.

The catalog also contains profiles for optional external engines (Blender,
FFmpeg, ONNX, ...).  The workloads in this module deliberately have no
external runtime dependency: a fresh worker can execute them immediately,
which makes them useful for smoke tests, capacity measurements, and payment
reconciliation tests.
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
    """Execute a built-in workload, returning ``None`` for unknown IDs."""
    normalized = str(workload or "").strip().lower()
    started = time.perf_counter()

    if normalized in {"calcul/integrity/sha256", "calcul/hash/sha256"}:
        digest = _sha256(p2p_data)
        return _output_result(
            workload=normalized,
            task=task,
            p2p_data=p2p_data,
            p2p_meta=p2p_meta,
            result={
                "algorithm": "sha256",
                "input_hash": digest,
                "size_bytes": len(p2p_data),
            },
            work_units=len(p2p_data),
            unit="byte",
            put_output=put_output,
            started=started,
        )

    if normalized in {"calcul/libm/sin", "calcul/libm/exp"}:
        payload = _parse_json(p2p_data, label="libm_input") if p2p_data else {}
        if not isinstance(payload, dict):
            raise ValueError("libm_input_must_be_object")
        function = normalized.rsplit("/", 1)[-1]
        raw_value = payload.get("value", task.get("value"))
        value = _number(raw_value, label="value")
        computed = math.sin(value) if function == "sin" else math.exp(value)
        return _output_result(
            workload=normalized,
            task=task,
            p2p_data=p2p_data,
            p2p_meta=p2p_meta,
            result={"function": function, "value": value, "result": computed},
            work_units=1,
            unit="invocation",
            put_output=put_output,
            started=started,
        )

    if normalized == "calcul/math/matrix-multiply":
        payload = _parse_json(p2p_data, label="matrix_input") if p2p_data else {}
        if not isinstance(payload, dict):
            raise ValueError("matrix_input_must_be_object")
        left = _matrix(payload.get("a", task.get("a")), label="matrix_a")
        right = _matrix(payload.get("b", task.get("b")), label="matrix_b")
        product = _matrix_multiply(left, right)
        inner = len(right)
        work_units = len(left) * len(right[0]) * inner
        return _output_result(
            workload=normalized,
            task=task,
            p2p_data=p2p_data,
            p2p_meta=p2p_meta,
            result={
                "algorithm": "ijk-matrix-multiply-v1",
                "a_shape": [len(left), len(left[0])],
                "b_shape": [len(right), len(right[0])],
                "matrix": product,
            },
            work_units=work_units,
            unit="multiply-add",
            put_output=put_output,
            started=started,
        )

    if normalized == "calcul/simulation/monte-carlo-pi":
        payload = _parse_json(p2p_data, label="monte_carlo_input") if p2p_data else {}
        if not isinstance(payload, dict):
            raise ValueError("monte_carlo_input_must_be_object")
        seed = _bounded_int(
            task.get("seed", payload.get("seed", 42)),
            label="seed",
            minimum=0,
            maximum=0xFFFFFFFF,
        )
        iterations = _bounded_int(
            task.get("iterations", payload.get("iterations", 100_000)),
            label="iterations",
            minimum=1,
            maximum=_bounded_int(
                task.get("max_iterations", MAX_MONTE_CARLO_ITERATIONS),
                label="max_iterations",
                minimum=1,
                maximum=MAX_MONTE_CARLO_ITERATIONS,
            ),
        )
        state = seed
        hits = 0
        for _ in range(iterations):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            x = state / 4294967296.0
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            y = state / 4294967296.0
            if x * x + y * y <= 1.0:
                hits += 1
        estimate = 4.0 * hits / iterations
        return _output_result(
            workload=normalized,
            task=task,
            p2p_data=p2p_data,
            p2p_meta=p2p_meta,
            result={
                "algorithm": "lcg-pi-v1",
                "seed": seed,
                "iterations": iterations,
                "inside": hits,
                "pi": estimate,
            },
            work_units=iterations,
            unit="sample",
            put_output=put_output,
            started=started,
        )

    return None
