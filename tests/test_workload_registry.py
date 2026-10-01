"""The workload registry: every workload is declared by a manifest, and nodes
execute it through `runtime.handler` without any workload-specific code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from workloads.registry import (
    WORKLOADS_ROOT,
    WorkloadContext,
    WorkloadError,
    WorkloadRegistry,
    default_registry,
    index_is_current,
    run_workload,
    spec_from_manifest,
    unsupported_reason,
)
from workloads.standard.standard_workloads import run_standard_workload


def _put_output(data: bytes) -> dict[str, object]:
    return {"protocol": "test", "hash": "sha256:" + hashlib.sha256(data).hexdigest()}


def _fields(data: bytes, task: dict | None = None) -> dict:
    return {"task": task or {}, "p2p_data": data, "p2p_meta": {"source": "test"}, "put_output": _put_output}


def test_every_manifest_loads_and_executable_handlers_import() -> None:
    registry = default_registry()
    specs = registry.specs()
    assert len(specs) == len(list(WORKLOADS_ROOT.rglob("manifest.yaml")))
    for spec in specs:
        assert spec.manifest_path.parent.relative_to(WORKLOADS_ROOT).as_posix() == spec.id
        if spec.executable:
            assert callable(spec.load_handler())


def test_index_is_current_and_matches_the_manifests() -> None:
    assert index_is_current(), "run ./silicium workload index"
    from_index = {(spec.id, spec.handler_ref, spec.aliases) for spec in WorkloadRegistry.load().specs()}
    from_yaml = {(spec.id, spec.handler_ref, spec.aliases) for spec in WorkloadRegistry.from_manifests().specs()}
    assert from_index == from_yaml


def test_nodes_do_not_need_pyyaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_yaml)
    assert WorkloadRegistry.load().get("calcul/libm/sin") is not None


def test_built_in_and_raytracer_workloads_are_executable() -> None:
    registry = default_registry()
    for workload in (
        "calcul/integrity/sha256",
        "calcul/libm/sin",
        "calcul/libm/exp",
        "calcul/math/matrix-multiply",
        "calcul/simulation/monte-carlo-pi",
        "calcul/rendering/raytracer-fragment",
        "verification/hash-audit/sha256",
        "verification/rendering/raytracer-fragment",
    ):
        spec = registry.get(workload)
        assert spec is not None and spec.executable, workload


def test_alias_resolves_and_keeps_the_requested_name() -> None:
    result = run_workload("calcul/hash/sha256", "compute", _fields(b"abc"))
    assert result is not None
    assert result["compute"]["workload"] == "calcul/hash/sha256"
    assert result["workload_result"]["input_hash"] == hashlib.sha256(b"abc").hexdigest()


def test_registry_and_legacy_entry_point_give_the_same_result() -> None:
    task = {"seed": 7, "iterations": 1000}
    via_registry = run_workload("calcul/simulation/monte-carlo-pi", "compute", _fields(b"", task))
    via_legacy = run_standard_workload("calcul/simulation/monte-carlo-pi", task, b"", {"source": "test"}, _put_output)
    assert via_registry["result_hash"] == via_legacy["result_hash"]


@pytest.mark.parametrize(
    ("workload", "reason"),
    [
        ("", "unsupported_workload"),
        ("calcul/unknown/thing", "unsupported_workload"),
        ("calcul/rendering/blender", "workload_not_executable"),
        ("verification/hash-audit/sha256", "workload_role_mismatch"),
    ],
)
def test_non_executable_compute_requests(workload: str, reason: str) -> None:
    assert run_workload(workload, "compute", _fields(b"x")) is None
    assert unsupported_reason(workload) == reason


def test_a_new_workload_needs_only_a_manifest_and_a_handler(tmp_path: Path) -> None:
    calls: list[WorkloadContext] = []

    def handler(ctx: WorkloadContext) -> dict:
        calls.append(ctx)
        return {"role_result": "compute", "echo": ctx.p2p_data.decode(), "scale": ctx.parameters["scale"]}

    manifest = tmp_path / "calcul" / "demo" / "echo" / "manifest.yaml"
    spec = spec_from_manifest(
        manifest,
        {
            "id": "calcul/demo/echo",
            "version": "1.0.0",
            "runtime": {"kind": "python", "handler": "tests.fake:handler"},
            "parameters": {"scale": 3},
        },
    )
    registry = WorkloadRegistry([spec])
    import sys
    import types

    module = types.ModuleType("tests.fake")
    module.handler = handler  # type: ignore[attr-defined]
    sys.modules["tests.fake"] = module
    try:
        result = run_workload("calcul/demo/echo", "compute", _fields(b"hello"), registry=registry)
    finally:
        del sys.modules["tests.fake"]
    assert result == {"role_result": "compute", "echo": "hello", "scale": 3}
    assert calls[0].workload == "calcul/demo/echo"


def test_duplicate_names_are_rejected(tmp_path: Path) -> None:
    first = spec_from_manifest(tmp_path / "a", {"id": "calcul/a/b", "aliases": ["calcul/x/y"]})
    second = spec_from_manifest(tmp_path / "b", {"id": "calcul/x/y"})
    with pytest.raises(WorkloadError):
        WorkloadRegistry([first, second])


def test_node_runs_compute_and_default_verification_through_the_registry(tmp_path: Path) -> None:
    from tests.network_node_support import _config  # noqa: PLC0415 - shared node config helper
    from tools import network_node

    class FakeP2P:
        def put_local(self, data: bytes, **_kwargs) -> dict:
            return _put_output(data)

        def fetch(self, _ref):
            raise AssertionError("not used")

    runtime = network_node.RoleRuntime(_config(tmp_path / "node", "worker", roles="compute,verify"), FakeP2P())
    compute = runtime.run_compute_task({}, {"workload": "calcul/libm/sin", "value": 0.5}, b"", {"source": "test"})
    assert compute["compute"]["executed"] is True
    assert compute["workload_result"]["function"] == "sin"

    unsupported = runtime.run_compute_task({}, {"workload": "calcul/rendering/blender"}, b"", {"source": "test"})
    assert unsupported["compute"] == {"mode": "network-workload", "executed": False, "reason": "workload_not_executable"}

    payload = json.dumps({"result_hash": "abc"}).encode()
    verdict = runtime.run_verify_task({}, {"workload": "calcul/libm/sin", "expected_hash": "abc"}, payload, {})
    assert verdict["verified"] is True
