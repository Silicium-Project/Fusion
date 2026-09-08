#!/usr/bin/env python3
"""Performance and resource budget runner for Silicium commands."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
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
    timeout_sec: float | None
    env: dict[str, str]
    platforms: list[str]


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
    timed_out: bool
    skipped: bool
    skip_reason: str | None


def host_os_name() -> str:
    return os.name


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
    if not isinstance(content, dict):
        raise ValueError(f"Invalid budget file format in {path}: root object expected")
    profiles_data = content.get("profiles", {})
    if not isinstance(profiles_data, dict):
        raise ValueError(f"Invalid budget file format in {path}: 'profiles' object expected")
    profiles: dict[str, Profile] = {}
    for key, value in profiles_data.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"Invalid profile key in {path}: non-empty string expected")
        if not isinstance(value, dict):
            raise ValueError(f"Invalid profile '{key}' in {path}: object expected")
        command = value.get("command", [])
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(item, str) and item.strip() for item in command)
        ):
            raise ValueError(
                f"Invalid profile '{key}' in {path}: non-empty string list expected for 'command'"
            )
        budgets = value.get("budgets", {})
        if not isinstance(budgets, dict):
            raise ValueError(f"Invalid profile '{key}' in {path}: object expected for 'budgets'")
        env = value.get("env", {})
        if not isinstance(env, dict):
            raise ValueError(f"Invalid profile '{key}' in {path}: object expected for 'env'")
        normalized_env: dict[str, str] = {}
        for env_key, env_value in env.items():
            if not isinstance(env_key, str) or not env_key.strip():
                raise ValueError(f"Invalid profile '{key}' in {path}: env key must be non-empty string")
            if not isinstance(env_value, str):
                raise ValueError(
                    f"Invalid profile '{key}' in {path}: env value for '{env_key}' must be string"
                )
            normalized_env[env_key] = env_value
        timeout_raw = value.get("timeout_sec")
        timeout_sec: float | None = None
        if timeout_raw is not None:
            if not isinstance(timeout_raw, (int, float)):
                raise ValueError(
                    f"Invalid profile '{key}' in {path}: numeric expected for 'timeout_sec'"
                )
            timeout_sec = float(timeout_raw)
            if not math.isfinite(timeout_sec) or timeout_sec <= 0:
                raise ValueError(
                    f"Invalid profile '{key}' in {path}: positive finite value expected for 'timeout_sec'"
                )
        platforms_raw = value.get("platforms")
        platforms: list[str] = []
        if platforms_raw is not None:
            if not isinstance(platforms_raw, list) or not platforms_raw:
                raise ValueError(
                    f"Invalid profile '{key}' in {path}: non-empty list expected for 'platforms'"
                )
            allowed = {"windows", "linux", "darwin"}
            for item in platforms_raw:
                if not isinstance(item, str):
                    raise ValueError(
                        f"Invalid profile '{key}' in {path}: string entries expected in 'platforms'"
                    )
                item_norm = item.strip().lower()
                if item_norm not in allowed:
                    raise ValueError(
                        f"Invalid profile '{key}' in {path}: unsupported platform '{item}'"
                    )
                platforms.append(item_norm)
        numeric_budgets: dict[str, float] = {}
        for metric in ("wall_sec", "cpu_sec", "max_rss_kib"):
            raw = budgets.get(metric)
            if raw is None:
                continue
            if not isinstance(raw, (int, float)):
                raise ValueError(
                    f"Invalid profile '{key}' in {path}: numeric expected for budget '{metric}'"
                )
            value_num = float(raw)
            if not math.isfinite(value_num) or value_num < 0:
                raise ValueError(
                    f"Invalid profile '{key}' in {path}: non-negative finite value expected for '{metric}'"
                )
            numeric_budgets[metric] = value_num
        profiles[key] = Profile(
            key=key,
            description=str(value.get("description", "")).strip(),
            command=command,
            budgets=numeric_budgets,
            timeout_sec=timeout_sec,
            env=normalized_env,
            platforms=platforms,
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


def normalize_command_for_platform(command: list[str], repo_root: Path) -> list[str]:
    if host_platform_tag() != "windows" or not command:
        return command
    head = command[0].replace("\\", "/")
    if head in {"./silicium", "silicium"}:
        script = repo_root / "silicium"
        if script.exists():
            return [sys.executable, str(script), *command[1:]]
    return command


def host_platform_tag() -> str:
    if host_os_name() == "nt":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    return sys.platform.lower()


def profile_is_supported(profile: Profile) -> tuple[bool, str | None]:
    if not profile.platforms:
        return True, None
    host = host_platform_tag()
    if host in profile.platforms:
        return True, None
    return False, f"host '{host}' not in supported platforms: {', '.join(profile.platforms)}"


def command_is_available(command: list[str], repo_root: Path, env: dict[str, str]) -> bool:
    """Check the executable before wrapping it with ``/usr/bin/time``.

    ``time`` reports a missing child command as exit code 127 instead of
    raising ``FileNotFoundError`` in Python. Preflighting keeps the result
    contract stable across hosts and makes the diagnostic actionable.
    """
    if not command:
        return False
    executable = command[0]
    if os.path.dirname(executable) or (os.altsep and os.altsep in executable):
        path = Path(executable)
        if not path.is_absolute():
            path = repo_root / path
        return path.is_file() and (os.name == "nt" or os.access(path, os.X_OK))
    return shutil.which(executable, path=env.get("PATH")) is not None


def run_profile(profile: Profile, repo_root: Path) -> ProfileResult:
    supported, reason = profile_is_supported(profile)
    effective_command = normalize_command_for_platform(profile.command, repo_root)
    if not supported:
        return ProfileResult(
            key=profile.key,
            command=effective_command,
            description=profile.description,
            return_code=0,
            wall_sec=None,
            cpu_sec=None,
            max_rss_kib=None,
            budgets=profile.budgets,
            violations=[],
            metrics_unavailable=["wall_sec", "cpu_sec", "max_rss_kib"],
            timed_out=False,
            skipped=True,
            skip_reason=reason,
        )

    time_bin = shutil.which("time") or ("/usr/bin/time" if Path("/usr/bin/time").exists() else None)
    command_line = " ".join(shlex.quote(part) for part in effective_command)
    print(f">> [{profile.key}] {command_line}")

    wall_sec: float | None = None
    cpu_sec: float | None = None
    max_rss_kib: float | None = None
    run_env = os.environ.copy()
    run_env.update(profile.env)

    try:
        if not command_is_available(effective_command, repo_root, run_env):
            raise FileNotFoundError(2, "No such file or directory", effective_command[0])
        if time_bin:
            fmt = f"{TIME_MARKER} elapsed=%e user=%U sys=%S rss_kib=%M exit=%x"
            cmd = [time_bin, "-f", fmt, *effective_command]
            result = subprocess.run(
                cmd,
                cwd=repo_root,
                env=run_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=profile.timeout_sec,
            )
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
            result = subprocess.run(
                effective_command,
                cwd=repo_root,
                env=run_env,
                text=True,
                check=False,
                timeout=profile.timeout_sec,
            )
            wall_sec = time.perf_counter() - start
            return_code = result.returncode
    except subprocess.TimeoutExpired:
        return ProfileResult(
            key=profile.key,
            command=effective_command,
            description=profile.description,
            return_code=124,
            wall_sec=profile.timeout_sec,
            cpu_sec=None,
            max_rss_kib=None,
            budgets=profile.budgets,
            violations=[f"timeout: exceeded {profile.timeout_sec:.3f}s"],
            metrics_unavailable=["cpu_sec", "max_rss_kib"],
            timed_out=True,
            skipped=False,
            skip_reason=None,
        )
    except FileNotFoundError as exc:
        return ProfileResult(
            key=profile.key,
            command=effective_command,
            description=profile.description,
            return_code=127,
            wall_sec=None,
            cpu_sec=None,
            max_rss_kib=None,
            budgets=profile.budgets,
            violations=[f"command_not_found: {getattr(exc, 'filename', None) or str(exc)}"],
            metrics_unavailable=["wall_sec", "cpu_sec", "max_rss_kib"],
            timed_out=False,
            skipped=False,
            skip_reason=None,
        )
    except OSError as exc:
        return ProfileResult(
            key=profile.key,
            command=effective_command,
            description=profile.description,
            return_code=127,
            wall_sec=None,
            cpu_sec=None,
            max_rss_kib=None,
            budgets=profile.budgets,
            violations=[f"command_launch_error: {getattr(exc, 'filename', None) or str(exc)}"],
            metrics_unavailable=["wall_sec", "cpu_sec", "max_rss_kib"],
            timed_out=False,
            skipped=False,
            skip_reason=None,
        )

    # GNU time reports a missing child as exit 127 instead of raising in Python.
    if (
        time_bin
        and return_code == 127
        and "cannot run" in (result.stderr or "")
    ):
        return ProfileResult(
            key=profile.key,
            command=effective_command,
            description=profile.description,
            return_code=127,
            wall_sec=None,
            cpu_sec=None,
            max_rss_kib=None,
            budgets=profile.budgets,
            violations=[f"command_not_found: {effective_command[0]}"],
            metrics_unavailable=["wall_sec", "cpu_sec", "max_rss_kib"],
            timed_out=False,
            skipped=False,
            skip_reason=None,
        )

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
        command=effective_command,
        description=profile.description,
        return_code=return_code,
        wall_sec=wall_sec,
        cpu_sec=cpu_sec,
        max_rss_kib=max_rss_kib,
        budgets=profile.budgets,
        violations=violations,
        metrics_unavailable=unavailable,
        timed_out=False,
        skipped=False,
        skip_reason=None,
    )


def format_metric(name: str, value: float | None, limit: float | None) -> str:
    if value is None:
        return f"{name}=n/a"
    if limit is None:
        return f"{name}={value:.3f}"
    status = "OK" if value <= limit else "OVER"
    return f"{name}={value:.3f} (budget={limit:.3f}, {status})"


def print_result(result: ProfileResult) -> None:
    if result.skipped:
        status = "SKIP"
    else:
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
    if result.skipped and result.skip_reason:
        print(f"  note: skipped -> {result.skip_reason}")
    if result.timed_out:
        print("  note: command timed out")
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
                "timed_out": item.timed_out,
                "skipped": item.skipped,
                "skip_reason": item.skip_reason,
            }
        )
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "budget_file": str(budget_file),
        "results": entries,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run budgeted performance checks.")
    parser.add_argument(
        "--budget-file",
        default=str(DEFAULT_BUDGET_FILE),
        help="Path to performance budget JSON.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Profile key to run (repeatable).",
    )
    selection.add_argument(
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    budget_file = Path(args.budget_file)
    if not budget_file.exists():
        print(f"Budget file not found: {budget_file}", file=sys.stderr)
        return 2

    try:
        profiles = load_profiles(budget_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Failed to load budget file '{budget_file}': {exc}", file=sys.stderr)
        return 2
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
        selected_keys = args.profile or ["network_check"]

    missing = [key for key in selected_keys if key not in profiles]
    if missing:
        print(f"Unknown profile(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    results: list[ProfileResult] = []
    for key in selected_keys:
        try:
            result = run_profile(profiles[key], REPO_ROOT)
        except Exception as exc:  # pragma: no cover - defensive fallback
            result = ProfileResult(
                key=profiles[key].key,
                command=profiles[key].command,
                description=profiles[key].description,
                return_code=127,
                wall_sec=None,
                cpu_sec=None,
                max_rss_kib=None,
                budgets=profiles[key].budgets,
                violations=[f"internal_error: {exc.__class__.__name__}: {exc}"],
                metrics_unavailable=["wall_sec", "cpu_sec", "max_rss_kib"],
                timed_out=False,
                skipped=False,
                skip_reason=None,
            )
        print_result(result)
        results.append(result)

    report = serialize_results(results, budget_file)
    if args.output:
        output_path = Path(args.output)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Failed to write report '{output_path}': {exc}", file=sys.stderr)
            return 2
        print(f"\nWrote report to {output_path}")

    executed_results = [item for item in results if not item.skipped]
    total_violations = sum(1 for item in executed_results if item.violations)
    total_skipped = sum(1 for item in results if item.skipped)
    print(f"\nProfiles run: {len(executed_results)}, skipped: {total_skipped}, failures: {total_violations}")
    if args.strict and total_violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
