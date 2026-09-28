"""Handlers of the built-in workloads (referenced by their manifests'
`runtime.handler`). They have no external dependency, so a fresh worker can run
them immediately: smoke tests, capacity measurements, payment reconciliation.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

from workloads.registry import WorkloadContext
from workloads.standard.standard_workloads import (
    MAX_MONTE_CARLO_ITERATIONS,
    _bounded_int,
    _matrix,
    _matrix_multiply,
    _number,
    _output_result,
    _parse_json,
    _sha256,
    _stable_json,
)


def sha256(ctx: WorkloadContext) -> dict[str, Any]:
    """`calcul/integrity/sha256`: SHA-256 of the input bytes."""
    started = time.perf_counter()
    digest = _sha256(ctx.p2p_data)
    return _output_result(
        workload=ctx.workload,
        task=ctx.task,
        p2p_data=ctx.p2p_data,
        p2p_meta=ctx.p2p_meta,
        result={
            "algorithm": "sha256",
            "input_hash": digest,
            "size_bytes": len(ctx.p2p_data),
        },
        work_units=len(ctx.p2p_data),
        unit="byte",
        put_output=ctx.put_output,
        started=started,
    )


def libm(ctx: WorkloadContext) -> dict[str, Any]:
    """`calcul/libm/sin` and `calcul/libm/exp`: one libm call on `value`."""
    started = time.perf_counter()
    payload = _parse_json(ctx.p2p_data, label="libm_input") if ctx.p2p_data else {}
    if not isinstance(payload, dict):
        raise ValueError("libm_input_must_be_object")
    function = ctx.workload.rsplit("/", 1)[-1]
    raw_value = payload.get("value", ctx.task.get("value"))
    value = _number(raw_value, label="value")
    computed = math.sin(value) if function == "sin" else math.exp(value)
    return _output_result(
        workload=ctx.workload,
        task=ctx.task,
        p2p_data=ctx.p2p_data,
        p2p_meta=ctx.p2p_meta,
        result={"function": function, "value": value, "result": computed},
        work_units=1,
        unit="invocation",
        put_output=ctx.put_output,
        started=started,
    )


def matrix_multiply(ctx: WorkloadContext) -> dict[str, Any]:
    """`calcul/math/matrix-multiply`: product of matrices `a` and `b`."""
    started = time.perf_counter()
    payload = _parse_json(ctx.p2p_data, label="matrix_input") if ctx.p2p_data else {}
    if not isinstance(payload, dict):
        raise ValueError("matrix_input_must_be_object")
    left = _matrix(payload.get("a", ctx.task.get("a")), label="matrix_a")
    right = _matrix(payload.get("b", ctx.task.get("b")), label="matrix_b")
    product = _matrix_multiply(left, right)
    inner = len(right)
    work_units = len(left) * len(right[0]) * inner
    return _output_result(
        workload=ctx.workload,
        task=ctx.task,
        p2p_data=ctx.p2p_data,
        p2p_meta=ctx.p2p_meta,
        result={
            "algorithm": "ijk-matrix-multiply-v1",
            "a_shape": [len(left), len(left[0])],
            "b_shape": [len(right), len(right[0])],
            "matrix": product,
        },
        work_units=work_units,
        unit="multiply-add",
        put_output=ctx.put_output,
        started=started,
    )


def monte_carlo_pi(ctx: WorkloadContext) -> dict[str, Any]:
    """`calcul/simulation/monte-carlo-pi`: seeded LCG estimate of pi."""
    started = time.perf_counter()
    payload = _parse_json(ctx.p2p_data, label="monte_carlo_input") if ctx.p2p_data else {}
    if not isinstance(payload, dict):
        raise ValueError("monte_carlo_input_must_be_object")
    seed = _bounded_int(
        ctx.task.get("seed", payload.get("seed", 42)),
        label="seed",
        minimum=0,
        maximum=0xFFFFFFFF,
    )
    iterations = _bounded_int(
        ctx.task.get("iterations", payload.get("iterations", 100_000)),
        label="iterations",
        minimum=1,
        maximum=_bounded_int(
            ctx.task.get("max_iterations", MAX_MONTE_CARLO_ITERATIONS),
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
        workload=ctx.workload,
        task=ctx.task,
        p2p_data=ctx.p2p_data,
        p2p_meta=ctx.p2p_meta,
        result={
            "algorithm": "lcg-pi-v1",
            "seed": seed,
            "iterations": iterations,
            "inside": hits,
            "pi": estimate,
        },
        work_units=iterations,
        unit="sample",
        put_output=ctx.put_output,
        started=started,
    )


def hash_audit(ctx: WorkloadContext) -> dict[str, Any]:
    """`verification/hash-audit/sha256`: compare the SHA-256 of the result with
    the expected hash (from the task or the envelope). The result may also embed
    its own `result_hash` / `compute_result_hash`.

    This is also the default verification of any compute result whose workload
    has no dedicated verifier.
    """
    actual = _sha256(ctx.p2p_data)
    expected = str(ctx.task.get("expected_hash") or ctx.envelope.get("expected_hash") or "").removeprefix("sha256:")
    embedded_hash = ""
    try:
        parsed = json.loads(ctx.p2p_data.decode("utf-8"))
        if isinstance(parsed, dict):
            embedded_hash = str(parsed.get("result_hash") or parsed.get("compute_result_hash") or "").removeprefix("sha256:")
    except Exception:
        pass
    passed = not expected or expected == actual or (bool(embedded_hash) and expected == embedded_hash)
    return {
        "role_result": "verify",
        "input": ctx.p2p_meta,
        "input_hash": actual,
        "expected_hash": expected,
        "recomputed_hash": embedded_hash or actual,
        "verified": passed,
        "choice": passed,
        "result_hash": _sha256(
            _stable_json({"verified": passed, "actual": actual, "expected": expected, "embedded": embedded_hash}).encode("utf-8")
        ),
    }
