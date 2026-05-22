from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SILICIUM = REPO_ROOT / "silicium"


def _run_alignment_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SILICIUM), "workload", "alignment", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_workload_alignment_json_report() -> None:
    result = _run_alignment_command("--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["total_families"] >= 1
    assert "verification/hash-audit" in report["families_with_fixtures"]
    assert "calcul/libm" in report["families_with_fixtures"]


def test_workload_alignment_strict_passes_for_critical_families() -> None:
    result = _run_alignment_command("--strict")
    assert result.returncode == 0, result.stderr
