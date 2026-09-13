from __future__ import annotations

import json
from pathlib import Path

import pytest

from workloads.standard.standard_workloads import run_standard_workload


def _run(tmp_path: Path, workload: str, payload: object, **task: object) -> dict[str, object]:
    output = tmp_path / "output.json"
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def put_output(value: bytes) -> dict[str, object]:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(value)
        return {"protocol": "file", "content_id": str(output), "size_bytes": len(value)}

    result = run_standard_workload(workload, task, data, {"source": "test", "size_bytes": len(data)}, put_output)
    assert result is not None
    assert output.exists()
    assert result["result_hash"]
    return result


def test_sha256_workload_publishes_a_content_addressed_result(tmp_path: Path) -> None:
    result = _run(tmp_path, "calcul/integrity/sha256", {"payload": "hello"})
    workload_result = result["workload_result"]
    assert isinstance(workload_result, dict)
    assert workload_result["algorithm"] == "sha256"
    assert workload_result["size_bytes"] > 0
    assert result["output_ref"]["protocol"] == "file"  # type: ignore[index]


def test_matrix_workload_is_deterministic_and_bounded(tmp_path: Path) -> None:
    payload = {"a": [[1, 2], [3, 4]], "b": [[5, 6], [7, 8]]}
    first = _run(tmp_path / "first", "calcul/math/matrix-multiply", payload)
    second = _run(tmp_path / "second", "calcul/math/matrix-multiply", payload)
    assert first["result_hash"] == second["result_hash"]
    assert first["workload_result"]["matrix"] == [[19.0, 22.0], [43.0, 50.0]]  # type: ignore[index]

    with pytest.raises(ValueError, match="matrix_dimensions_incompatible"):
        _run(tmp_path / "invalid", "calcul/math/matrix-multiply", {"a": [[1, 2]], "b": [[1, 2]]})


def test_monte_carlo_workload_replays_with_the_same_seed(tmp_path: Path) -> None:
    first = _run(
        tmp_path / "first",
        "calcul/simulation/monte-carlo-pi",
        {"seed": 7, "iterations": 500},
    )
    second = _run(
        tmp_path / "second",
        "calcul/simulation/monte-carlo-pi",
        {"seed": 7, "iterations": 500},
    )
    assert first["result_hash"] == second["result_hash"]
    assert first["workload_result"]["iterations"] == 500  # type: ignore[index]


def test_unknown_workload_is_left_for_external_engines(tmp_path: Path) -> None:
    output = tmp_path / "output.json"
    result = run_standard_workload(
        "calcul/rendering/blender",
        {},
        b"{}",
        {},
        lambda value: {"content_id": str(output)},
    )
    assert result is None
