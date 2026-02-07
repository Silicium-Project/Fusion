from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
