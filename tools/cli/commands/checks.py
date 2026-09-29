"""`test`, `check`, `doctor`, `smoke`, `budget` and `clean` commands.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from tools.cli.commands.ledger import ledger_wipe
from tools.cli.constants import (
    LEDGER_SUFFIX,
    PERF_BUDGET_FILE,
    POSIX_PYTEST_IMAGE_DEFAULT,
    REPO_ROOT,
    WORKLOAD_ROOT,
    WORKLOAD_SCHEMA_FILE,
)
from tools.cli.context import Context
from tools.cli.docker import docker_health, ensure_docker_healthy, list_wsl_distros, remove_path
from tools.cli.proc import COLOR_YELLOW, colorize, run, run_capture
from tools.cli.workload.lint import cmd_workload_lint


def _run_entrypoint_posix_tests_in_docker(args: argparse.Namespace, ctx: Context) -> None:
    ensure_docker_healthy(ctx, retries=2, timeout_s=8.0)
    image = args.posix_pytest_image
    script = (
        "set -euo pipefail; "
        "python -m pip install -q pytest; "
        "python -m pytest -q tests/test_entrypoint.py -rs"
    )
    cmd = [
        ctx.config.docker_bin,
        "run",
        "--rm",
        "-v",
        f"{REPO_ROOT}:/workspace",
        "-w",
        "/workspace",
        image,
        "bash",
        "-lc",
        script,
    ]
    run(cmd)


def cmd_test(args: argparse.Namespace, ctx: Context) -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], allow_failure=True)
    run([sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"], allow_failure=True)
    cmd_workload_lint(
        argparse.Namespace(
            root=str(WORKLOAD_ROOT),
            schema=str(WORKLOAD_SCHEMA_FILE),
            json=False,
        ),
        ctx,
    )
    pytest_cmd = [sys.executable, "-m", "pytest"]
    if args.entrypoint_docker:
        pytest_cmd += ["--ignore=tests/test_entrypoint.py"]
    run(pytest_cmd)
    if args.entrypoint_docker:
        _run_entrypoint_posix_tests_in_docker(args, ctx)


def configure_test(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--entrypoint-docker",
        action="store_true",
        help=(
            "Run tests/test_entrypoint.py in a Linux Docker container "
            "(useful on Windows where this module is skipped on host)."
        ),
    )
    parser.add_argument(
        "--posix-pytest-image",
        default=os.environ.get("SILICIUM_POSIX_PYTEST_IMAGE", POSIX_PYTEST_IMAGE_DEFAULT),
        help=(
            "Container image used with --entrypoint-docker "
            f"(default: {POSIX_PYTEST_IMAGE_DEFAULT})."
        ),
    )


def cmd_doctor(_: argparse.Namespace, ctx: Context) -> None:
    print(colorize("==> Silicium doctor", COLOR_YELLOW))
    print(f"os={os.name} python={sys.version.split()[0]}")
    print(f"docker_bin={ctx.config.docker_bin} DOCKER_HOST={os.environ.get('DOCKER_HOST', '<unset>')}")

    health = docker_health(ctx, retries=1, timeout_s=6.0)
    if health.ok:
        print(f"Docker: OK (server {health.detail or 'unknown'})")
    else:
        print(f"Docker: FAIL [{health.error_code}] {health.message}")
        if health.detail:
            detail = health.detail.strip().replace("\n", " | ")
            print(f"detail={detail[:800]}")

    if os.name != "nt":
        return

    distros = list_wsl_distros()
    if not distros:
        print("WSL: not available or no distributions found.")
        return

    print("WSL distros:")
    for distro in distros:
        flag = "*" if distro.get("default") == "yes" else " "
        print(f"  {flag} {distro['name']} (state={distro['state']} version={distro['version']})")

    default = next((d for d in distros if d.get("default") == "yes"), distros[0])
    name = default["name"]
    state = default.get("state", "")
    wsl_bin = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl_bin:
        print("WSL: wsl.exe not found in PATH.")
        return

    if state.lower() != "running":
        print(f"WSL docker integration: unknown (distro '{name}' is {state}).")
        print("Tip: run `wsl -d <distro>` once, then re-run `python silicium doctor`.")
        return

    code, _, err = run_capture(
        [wsl_bin, "-d", name, "--", "sh", "-lc", "test -S /var/run/docker.sock"],
        timeout_s=5.0,
    )
    if code == 0:
        print(f"WSL docker integration: OK (socket present in '{name}')")
    else:
        detail = err.strip()
        print(f"WSL docker integration: FAIL (no socket in '{name}')")
        if detail:
            print(f"detail={detail[:800]}")
        print("Fix: Docker Desktop -> Settings -> Resources -> WSL Integration -> enable this distro.")

    code, _, _ = run_capture(
        [wsl_bin, "-d", name, "--", "sh", "-lc", "command -v docker >/dev/null 2>&1"],
        timeout_s=5.0,
    )
    if code != 0:
        print(f"WSL docker CLI: missing in '{name}' (install docker-cli or use Windows docker.exe).")


def configure_doctor(parser: argparse.ArgumentParser) -> None:
    pass


def cmd_check(args: argparse.Namespace, ctx: Context) -> None:
    script = REPO_ROOT / "ci" / "core_check.sh"
    if not script.exists():
        print(f"Core check script not found: {script}")
        sys.exit(1)

    env_vars = {
        "CORE_CHECK_MODE": "full" if args.full else "quick",
        "CORE_CHECK_SCOPE": "platform" if args.scope == "all" else args.scope,  # i18n:ignore
    }
    if args.docker is not None:
        env_vars["CORE_CHECK_WITH_DOCKER"] = "1" if args.docker else "0"
    if args.require_docker:
        env_vars["CORE_CHECK_REQUIRE_DOCKER"] = "1"  # i18n:ignore
    if args.python:
        env_vars["PYTHON_BIN"] = args.python  # i18n:ignore

    bash = shutil.which("bash")
    if not bash:
        print("bash not found. Install bash or use a Linux/WSL environment.")
        sys.exit(1)
    env = os.environ.copy()
    env.update(env_vars)
    run([bash, str(script)], env=env)


def configure_check(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the active checks and the optional Docker proxy smoke.",  # i18n:ignore
    )
    parser.add_argument(
        "--scope",
        choices=["all", "platform"],
        default="platform",
        help="Active Network check scope (default: platform).",  # i18n:ignore
    )
    parser.add_argument(
        "--docker",
        dest="docker",
        action="store_true",
        help="Require Docker-backed checks when they are selected.",  # i18n:ignore
    )
    parser.add_argument(
        "--no-docker",
        dest="docker",
        action="store_false",
        help="Skip Docker-backed checks.",  # i18n:ignore
    )
    parser.add_argument(
        "--require-docker",
        action="store_true",
        help="Fail if a selected Docker-backed check cannot run.",  # i18n:ignore
    )
    parser.add_argument("--python", help="Path to Python executable used for checks.")  # i18n:ignore
    parser.set_defaults(docker=None)


def cmd_smoke(_: argparse.Namespace, ctx: Context) -> None:
    run(["tests/smoke/run_proxy_smoke.sh"])


def configure_smoke(parser: argparse.ArgumentParser) -> None:
    pass


def cmd_budget(args: argparse.Namespace, ctx: Context) -> None:
    script = REPO_ROOT / "tools" / "dev" / "quality" / "perf_budget.py"
    if not script.exists():
        print(f"Budget script not found: {script}")
        sys.exit(1)
    if args.all and args.profile:
        print("Use either --all or --profile (repeatable), not both.")
        sys.exit(2)
    cmd = [sys.executable, str(script)]
    if args.budget_file:
        cmd += ["--budget-file", args.budget_file]
    if args.list:
        cmd.append("--list")
    if args.all:
        cmd.append("--all")
    for profile in args.profile:
        cmd += ["--profile", profile]
    if args.strict:
        cmd.append("--strict")
    if args.output:
        cmd += ["--output", args.output]
    code = run(cmd, allow_failure=True)
    if code != 0:
        print(f"Budget check failed with exit code {code}.")
        sys.exit(code)


def configure_budget(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--budget-file",
        default=str(PERF_BUDGET_FILE),
        help="Path to the performance budget JSON file.",
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
        help="Run all budget profiles.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when a budget is exceeded.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report output path.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available profiles and exit.",
    )


def clean_artifacts() -> None:
    print(colorize("Cleaning caches and temporary artifacts...", COLOR_YELLOW))
    paths = [
        REPO_ROOT / ".pytest_cache",
        REPO_ROOT / ".cache",
        REPO_ROOT / ".tmp",
        REPO_ROOT / ".tmp2",
        REPO_ROOT / "build",
        REPO_ROOT / "perf-budget-report.json",
        REPO_ROOT / "target",  # single Cargo workspace build dir
    ]
    for path in paths:
        remove_path(path)


def cmd_clean(args: argparse.Namespace, ctx: Context) -> None:
    mode = args.mode or "cache"
    if args.ledgers:
        mode = "all"
    if mode in {"cache", "all"}:
        clean_artifacts()
    if mode in {"ledgers", "all"}:
        ledger_wipe(networks=list(LEDGER_SUFFIX.keys()), assume_yes=args.yes, ctx=ctx)


def configure_clean(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["cache", "ledgers", "all"],
        help="What to clean (default cache).",
    )
    parser.add_argument(
        "--ledgers",
        action="store_true",
        help="Legacy flag: clean caches and ledgers (same as 'all').",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmations when cleaning ledgers.",
    )
