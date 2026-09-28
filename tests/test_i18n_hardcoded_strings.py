from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "tools" / "dev" / "quality" / "check_i18n_hardcoded_strings.py"


def _run_checker(diff_text: str, strict: bool) -> subprocess.CompletedProcess[str]:
    diff_file = REPO_ROOT / "tests" / "_tmp_i18n_diff.patch"
    diff_file.write_text(diff_text, encoding="utf-8")
    try:
        cmd = [
            sys.executable,
            str(CHECKER),
            "--diff-file",
            str(diff_file),
            "--json",
        ]
        if strict:
            cmd.append("--strict")
        return subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
    finally:
        if diff_file.exists():
            diff_file.unlink()


def test_hardcoded_string_detected_in_added_line() -> None:
    diff = "\n".join(
        [
            "diff --git a/silicium b/silicium",
            "--- a/silicium",
            "+++ b/silicium",
            "@@ -1,0 +1,1 @@",
            '+print("Hello world from runtime")',
            "",
        ]
    )
    result = _run_checker(diff, strict=True)
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert len(report["violations"]) == 1


def test_key_like_string_is_not_reported() -> None:
    diff = "\n".join(
        [
            "diff --git a/silicium b/silicium",
            "--- a/silicium",
            "+++ b/silicium",
            "@@ -1,0 +1,1 @@",
            '+print("cli.shell.prompt")',
            "",
        ]
    )
    result = _run_checker(diff, strict=True)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["violations"] == []


def test_inline_ignore_suppresses_violation() -> None:
    diff = "\n".join(
        [
            "diff --git a/silicium b/silicium",
            "--- a/silicium",
            "+++ b/silicium",
            "@@ -1,0 +1,1 @@",
            '+print("Hello world from runtime")  # i18n:ignore',
            "",
        ]
    )
    result = _run_checker(diff, strict=True)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["violations"] == []


def test_moved_line_is_not_reported() -> None:
    diff = "\n".join(
        [
            "diff --git a/silicium b/silicium",
            "--- a/silicium",
            "+++ b/silicium",
            "@@ -1,1 +0,0 @@",
            '-    print("Hello world from runtime")',
            "diff --git a/tools/cli/main.py b/tools/cli/main.py",
            "--- /dev/null",
            "+++ b/tools/cli/main.py",
            "@@ -0,0 +1,2 @@",
            '+print("Hello world from runtime")',
            '+print("A brand new sentence here")',
            "",
        ]
    )
    result = _run_checker(diff, strict=True)
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert [item["literal"] for item in report["violations"]] == ["A brand new sentence here"]
