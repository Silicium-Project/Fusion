from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import perf_budget


def test_parse_time_marker() -> None:
    stderr = "\n".join(
        [
            "normal line",
            "__SILICIUM_PERF__ elapsed=1.25 user=0.50 sys=0.10 rss_kib=2048 exit=0",
        ]
    )
    parsed = perf_budget.parse_time_marker(stderr)
    assert parsed is not None
    assert parsed["elapsed"] == 1.25
    assert parsed["user"] == 0.50
    assert parsed["sys"] == 0.10
    assert parsed["rss_kib"] == 2048.0
    assert parsed["exit"] == 0.0


def test_check_budgets_detects_violation() -> None:
    metrics = {
        "wall_sec": 12.0,
        "cpu_sec": 30.0,
        "max_rss_kib": 4096.0,
    }
    budgets = {
        "wall_sec": 10.0,
        "cpu_sec": 30.0,
        "max_rss_kib": 5000.0,
    }
    violations, unavailable = perf_budget.check_budgets(metrics, budgets)
    assert unavailable == []
    assert len(violations) == 1
    assert violations[0].startswith("wall_sec:")


def test_load_profiles(tmp_path: Path) -> None:
    budget_file = tmp_path / "budgets.json"
    budget_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": {
                    "quick": {
                        "description": "Quick path",
                        "command": ["echo", "ok"],
                        "budgets": {"wall_sec": 1.0, "cpu_sec": 2.0, "max_rss_kib": 3.0},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    profiles = perf_budget.load_profiles(budget_file)
    assert "quick" in profiles
    profile = profiles["quick"]
    assert profile.command == ["echo", "ok"]
    assert profile.budgets["wall_sec"] == 1.0


def test_run_profile_command_not_found() -> None:
    profile = perf_budget.Profile(
        key="missing",
        description="missing command",
        command=["__this_command_does_not_exist__"],
        budgets={"wall_sec": 1.0},
    )
    result = perf_budget.run_profile(profile, Path.cwd())
    assert result.return_code == 127
    assert result.violations
    assert result.violations[0].startswith("command_not_found:")


def test_parse_args_rejects_all_with_profile() -> None:
    with pytest.raises(SystemExit) as exc:
        perf_budget.parse_args(["--all", "--profile", "quick"])
    assert exc.value.code == 2


def test_main_handles_internal_profile_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    budget_file = tmp_path / "budgets.json"
    budget_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": {
                    "quick": {
                        "description": "Quick path",
                        "command": ["echo", "ok"],
                        "budgets": {"wall_sec": 1.0},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    def _explode(*_args: object, **_kwargs: object) -> perf_budget.ProfileResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(perf_budget, "run_profile", _explode)
    code = perf_budget.main(["--budget-file", str(budget_file), "--profile", "quick", "--strict"])
    assert code == 1


def test_normalize_command_for_platform_windows_silicium(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "silicium"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setattr(perf_budget.os, "name", "nt")
    command = perf_budget.normalize_command_for_platform(["./silicium", "budget", "--list"], tmp_path)
    assert command[0] == perf_budget.sys.executable
    assert Path(command[1]) == script
    assert command[2:] == ["budget", "--list"]
