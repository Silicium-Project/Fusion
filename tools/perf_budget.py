#!/usr/bin/env python3
"""Performance and resource budget runner for Silicium commands."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGET_FILE = REPO_ROOT / "docs" / "performance-budgets.json"
TIME_MARKER = "__SILICIUM_PERF__"


@dataclass(frozen=True)
class Profile:
    key: str
    description: str
    command: list[str]
    budgets: dict[str, float]


@dataclass(frozen=True)
class ProfileResult:
    key: str
    command: list[str]
    description: str
    return_code: int
    wall_sec: float | None
    cpu_sec: float | None
    max_rss_kib: float | None
    budgets: dict[str, float]
    violations: list[str]
    metrics_unavailable: list[str]


def parse_time_marker(stderr: str) -> dict[str, float] | None:
    parsed: dict[str, float] = {}
    for line in stderr.splitlines():
        if not line.startswith(TIME_MARKER):
            continue
        tokens = line[len(TIME_MARKER):].strip().split()
        for token in tokens:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            try:
                parsed[key] = float(value)
            except ValueError:
                continue
        if parsed:
            return parsed
    return None


def load_profiles(path: Path) -> dict[str, Profile]:
    content = json.loads(path.read_text(encoding="utf-8"))
    profiles_data = content.get("profiles", {})
    profiles: dict[str, Profile] = {}
    for key, value in profiles_data.items():
        if not isinstance(value, dict):
            continue
        command = value.get("command", [])
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            continue
        budgets = value.get("budgets", {})
        if not isinstance(budgets, dict):
            budgets = {}
        numeric_budgets: dict[str, float] = {}
        for metric in ("wall_sec", "cpu_sec", "max_rss_kib"):
            raw = budgets.get(metric)
            if isinstance(raw, (int, float)):
                numeric_budgets[metric] = float(raw)
        profiles[key] = Profile(
            key=key,
            description=str(value.get("description", "")).strip(),
            command=command,
            budgets=numeric_budgets,
        )
    return profiles


def check_budgets(metrics: dict[str, float | None], budgets: dict[str, float]) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    unavailable: list[str] = []
    for metric in ("wall_sec", "cpu_sec", "max_rss_kib"):
        limit = budgets.get(metric)
        if limit is None:
            continue
        actual = metrics.get(metric)
        if actual is None:
            unavailable.append(metric)
            continue
        if actual > limit:
            violations.append(f"{metric}: {actual:.3f} > {limit:.3f}")
    return violations, unavailable


def run_profile(profile: Profile, repo_root: Path) -> ProfileResult:
    time_bin = shutil.which("time") or ("/usr/bin/time" if Path("/usr/bin/time").exists() else None)
    command_line = " ".join(shlex.quote(part) for part in profile.command)
    print(f">> [{profile.key}] {command_line}")

    wall_sec: float | None = None
    cpu_sec: float | None = None
    max_rss_kib: float | None = None

    if time_bin:
        fmt = f"{TIME_MARKER} elapsed=%e user=%U sys=%S rss_kib=%M exit=%x"
        cmd = [time_bin, "-f", fmt, *profile.command]
        result = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
        marker = parse_time_marker(result.stderr)
        if marker is not None:
            wall_sec = marker.get("elapsed")
            user_sec = marker.get("user")
            sys_sec = marker.get("sys")
            if user_sec is not None and sys_sec is not None:
                cpu_sec = user_sec + sys_sec
            max_rss_kib = marker.get("rss_kib")
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            filtered = "\n".join(
                line for line in result.stderr.splitlines() if not line.startswith(TIME_MARKER)
            )
            if filtered:
                print(filtered, file=sys.stderr)
        return_code = result.returncode
    else:
        start = time.perf_counter()
        result = subprocess.run(profile.command, cwd=repo_root, text=True, check=False)
        wall_sec = time.perf_counter() - start
        return_code = result.returncode

    metrics = {
        "wall_sec": wall_sec,
        "cpu_sec": cpu_sec,
        "max_rss_kib": max_rss_kib,
    }
    violations, unavailable = check_budgets(metrics, profile.budgets)
    if return_code != 0:
        violations.append(f"exit_code: {return_code}")

    return ProfileResult(
        key=profile.key,
        command=profile.command,
        description=profile.description,
        return_code=return_code,
        wall_sec=wall_sec,
        cpu_sec=cpu_sec,
        max_rss_kib=max_rss_kib,
        budgets=profile.budgets,
        violations=violations,
        metrics_unavailable=unavailable,
    )


def format_metric(name: str, value: float | None, limit: float | None) -> str:
    if value is None:
        return f"{name}=n/a"
    if limit is None:
        return f"{name}={value:.3f}"
    status = "OK" if value <= limit else "OVER"
    return f"{name}={value:.3f} (budget={limit:.3f}, {status})"


def print_result(result: ProfileResult) -> None:
    status = "PASS" if not result.violations else "FAIL"
    print(f"\n[{status}] {result.key}")
    if result.description:
        print(f"  desc: {result.description}")
    print(f"  cmd : {' '.join(shlex.quote(part) for part in result.command)}")
    print(
        "  "
        + ", ".join(
            [
                format_metric("wall_sec", result.wall_sec, result.budgets.get("wall_sec")),
                format_metric("cpu_sec", result.cpu_sec, result.budgets.get("cpu_sec")),
                format_metric("max_rss_kib", result.max_rss_kib, result.budgets.get("max_rss_kib")),
            ]
        )
    )
    if result.metrics_unavailable:
        print(f"  note: unavailable metrics -> {', '.join(result.metrics_unavailable)}")
    if result.violations:
        for violation in result.violations:
            print(f"  violation: {violation}")


def serialize_results(results: list[ProfileResult], budget_file: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for item in results:
        entries.append(
            {
                "profile": item.key,
                "description": item.description,
                "command": item.command,
                "return_code": item.return_code,
                "metrics": {
                    "wall_sec": item.wall_sec,
                    "cpu_sec": item.cpu_sec,
                    "max_rss_kib": item.max_rss_kib,
                },
                "budgets": item.budgets,
                "violations": item.violations,
                "metrics_unavailable": item.metrics_unavailable,
            }
        )
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "budget_file": str(budget_file),
        "results": entries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run budgeted performance checks.")
    parser.add_argument(
        "--budget-file",
        default=str(DEFAULT_BUDGET_FILE),
        help="Path to performance budget JSON.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Profile key to run (repeatable).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all profiles from the budget file.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when budgets are exceeded.",
    )
    parser.add_argument(
        "--output",
        help="Write JSON report to this file.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available profiles and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    budget_file = Path(args.budget_file)
    if not budget_file.exists():
        print(f"Budget file not found: {budget_file}", file=sys.stderr)
        return 2

    profiles = load_profiles(budget_file)
    if not profiles:
        print(f"No valid profiles found in {budget_file}", file=sys.stderr)
        return 2

    if args.list:
        for key in sorted(profiles):
            profile = profiles[key]
            print(f"{key}: {profile.description}")
        return 0

    if args.all:
        selected_keys = sorted(profiles.keys())
    else:
        selected_keys = args.profile or ["check_worker_quick"]

    missing = [key for key in selected_keys if key not in profiles]
    if missing:
        print(f"Unknown profile(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    results: list[ProfileResult] = []
    for key in selected_keys:
        result = run_profile(profiles[key], REPO_ROOT)
        print_result(result)
        results.append(result)

    report = serialize_results(results, budget_file)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote report to {output_path}")

    total_violations = sum(1 for item in results if item.violations)
    print(f"\nProfiles run: {len(results)}, failures: {total_violations}")
    if args.strict and total_violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
