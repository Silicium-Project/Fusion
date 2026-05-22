from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import json
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SILICIUM = REPO_ROOT / "silicium"
MANIFEST_ROOT = REPO_ROOT / "catalog" / "workloads"


def _run_workload_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SILICIUM), "workload", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def _output_lines(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _manifest_taxonomy(path: str) -> dict:
    manifest = MANIFEST_ROOT / path / "manifest.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    taxonomy = data.get("taxonomy", {})
    assert isinstance(taxonomy, dict)
    return taxonomy


def test_workload_list_filter_category() -> None:
    result = _run_workload_command("list", "--category", "calcul")
    assert result.returncode == 0, result.stderr
    lines = _output_lines(result.stdout)
    assert lines
    for path in lines:
        assert path.startswith("calcul/")
        assert _manifest_taxonomy(path)["category"] == "calcul"


def test_workload_list_filter_domain() -> None:
    result = _run_workload_command("list", "--domain", "rendering")
    assert result.returncode == 0, result.stderr
    lines = _output_lines(result.stdout)
    assert lines
    for path in lines:
        assert _manifest_taxonomy(path)["domain"] == "rendering"


def test_workload_show_filter_match_and_mismatch() -> None:
    mismatch = _run_workload_command(
        "show",
        "calcul/libm/sin",
        "--domain",
        "video",
    )
    assert mismatch.returncode != 0
    assert "does not match filters" in mismatch.stdout

    match = _run_workload_command(
        "show",
        "calcul/libm/sin",
        "--domain",
        "math",
        "--tag",
        "libm",
    )
    assert match.returncode == 0, match.stderr
    assert "calcul/libm/sin/manifest.yaml" in match.stdout.replace("\\", "/")


def test_workload_list_details_contains_presets() -> None:
    result = _run_workload_command("list", "--details", "--category", "calcul")
    assert result.returncode == 0, result.stderr
    lines = _output_lines(result.stdout)
    assert lines
    header = lines[0].split("\t")
    assert header[0] == "path"
    rows = [line.split("\t") for line in lines[1:]]
    assert rows
    target = [row for row in rows if row[0] == "calcul/libm/sin"]
    assert target, "Expected calcul/libm/sin in workload details output"
    assert "default" in target[0][-1]


def test_workload_show_dry_run_with_preset() -> None:
    result = _run_workload_command(
        "show",
        "calcul/libm/sin",
        "--dry-run",
        "--preset",
        "default",
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["preset"] == "default"
    assert plan["missing_variables"] == []
    assert "--value 0.5" in plan["command"]
    assert "--out result.json" in plan["command"]
