from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ROOT = REPO_ROOT / "catalog" / "workloads"
MANIFESTS = sorted(WORKLOAD_ROOT.rglob("manifest.yaml"))


@pytest.mark.parametrize(
    "manifest_path",
    MANIFESTS,
    ids=lambda path: str(path.parent.relative_to(WORKLOAD_ROOT)),
)
def test_every_catalog_workload_has_a_resolved_default_plan(manifest_path: Path) -> None:
    """Keep every declared workload executable at least through planning.

    Catalog entries are contracts for engines that may be provisioned later;
    this test deliberately does not fake Blender, FFmpeg, or GPU execution.
    It still exercises the public workload CLI for every manifest and catches
    stale presets or commands with unresolved inputs.
    """
    workload_path = manifest_path.parent.relative_to(WORKLOAD_ROOT).as_posix()
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "silicium"),
            "workload",
            "show",
            workload_path,
            "--dry-run",
            "--preset",
            "default",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    plan = json.loads(result.stdout)
    assert plan["path"] == workload_path
    assert plan["preset"] == "default"
    assert plan["missing_variables"] == []
    assert plan["command"].strip()
    assert "{" not in plan["command"] and "}" not in plan["command"]

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
    assert manifest.get("engine") in {"python", "container"}
    assert (manifest_path.parent / "README.md").is_file()
