from __future__ import annotations

from pathlib import Path

from tools.load_test import build_compose_config, build_task, role_profile_counts


def test_load_topology_has_one_isolated_service_per_worker(tmp_path: Path) -> None:
    config = build_compose_config(
        repo_root=Path(__file__).resolve().parents[1],
        state_dir=tmp_path,
        worker_count=32,
        batch_size=4,
        scheduler_port=46011,
        mcp_port=9766,
    )
    services = config["services"]
    worker_services = sorted(name for name in services if name.startswith("worker-"))
    assert worker_services == [f"worker-{index:03d}" for index in range(1, 33)]
    node_services = [services["scheduler"], *(services[name] for name in worker_services)]
    assert len({service["command"][service["command"].index("--node-id") + 1] for service in node_services}) == 33
    assert services["scheduler"]["ports"] == ["127.0.0.1:46011:46001"]
    assert services["mcp"]["ports"] == ["127.0.0.1:9766:9765"]
    assert "compute" not in services["scheduler"]["command"][services["scheduler"]["command"].index("--roles") + 1]
    assert all("--pull-tasks-batch-size" in service["command"] for name, service in services.items() if name.startswith("worker-"))
    assert "--peer-http-max-workers" in services["scheduler"]["command"]
    assert all("--peer-http-max-workers" in service["command"] for name, service in services.items() if name.startswith("worker-"))


def test_load_topology_exercises_heterogeneous_worker_roles(tmp_path: Path) -> None:
    config = build_compose_config(
        repo_root=Path(__file__).resolve().parents[1],
        state_dir=tmp_path,
        worker_count=100,
        batch_size=8,
        scheduler_port=46012,
        mcp_port=9767,
    )
    roles = {
        service["command"][service["command"].index("--roles") + 1]
        for name, service in config["services"].items()
        if name.startswith("worker-")
    }
    assert {"compute", "verify", "storage", "audit", "resource"}.issubset(
        {role for profile in roles for role in profile.split(",")}
    )
    assert all(count > 0 for count in role_profile_counts(100).values())


def test_load_task_mix_is_hashable_and_role_specific() -> None:
    compute = build_task(1, verify=False)
    verify = build_task(5, verify=True)
    assert compute["required_roles"] == ["compute"]
    assert compute["task"]["workload"] == "calcul/integrity/sha256"
    assert verify["required_roles"] == ["verify"]
    assert verify["task"]["workload"] == "verification/hash-audit/sha256"
    assert len(verify["task"]["expected_hash"]) == 64
