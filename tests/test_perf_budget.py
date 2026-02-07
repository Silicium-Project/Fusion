from __future__ import annotations

import json
from pathlib import Path

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
