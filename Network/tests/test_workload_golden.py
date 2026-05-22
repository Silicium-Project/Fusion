from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SILICIUM = REPO_ROOT / "silicium"


def _run_golden_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SILICIUM), "workload", "golden", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_workload_golden_json_report() -> None:
    result = _run_golden_command("--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["checked"] >= 1
    assert report["failed"] == 0


def test_workload_golden_strict_passes() -> None:
    result = _run_golden_command("--strict")
    assert result.returncode == 0, result.stderr
