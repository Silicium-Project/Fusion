"""Steps shared by `setup up` and `setup down`.

Each step runs one Docker / Docker Compose action and records its outcome in
the run summary (see `setup_summary.py`): preflight checks, per-target
`compose up` / `compose stop` (+ optional `rm`), `compose down`, and the final
`compose ps` capture.
"""

from __future__ import annotations

import argparse
from typing import Any

from tools.cli.constants import START_TARGETS
from tools.cli.context import Context
from tools.cli.docker import compose_base, compose_command
from tools.cli.framework import _emit_cli_event
from tools.cli.proc import run, run_capture


def record_docker_preflight(summary: dict[str, Any], health: Any) -> bool:
    """Store the Docker health check result; return True when Docker is usable."""
    if not health.ok:
        summary["preflight"]["docker"] = {
            "status": "failed",
            "error_code": health.error_code,
            "reason": health.message,
        }
        return False
    summary["preflight"]["docker"] = {"status": "ok", "detail": health.detail}
    return True


def record_compose_preflight(summary: dict[str, Any], ctx: Context) -> bool:
    """Check that Docker Compose is available; return True when it is."""
    try:
        compose_command(ctx)
    except SystemExit:
        summary["preflight"]["compose"] = {
            "status": "failed",
            "reason": "Docker Compose not available",
        }
        return False
    summary["preflight"]["compose"] = {"status": "ok"}
    return True


def _profiled_compose(ctx: Context, profile: str | None) -> list[str]:
    cmd = compose_base(ctx)
    if profile:
        cmd += ["--profile", profile]
    return cmd


def start_setup_target(summary: dict[str, Any], ctx: Context, target: str) -> None:
    """Run `compose up -d` for one target and record it as started or failed."""
    service, profile = START_TARGETS[target]
    _emit_cli_event(
        "info",
        "dispatch_target",
        "Dispatching setup up target",
        {
            "action": "setup_up",
            "target": target,
            "service": service,
            "profile": profile or "",
        },
    )
    cmd = _profiled_compose(ctx, profile)
    cmd += ["up", "-d", service]
    code = run(cmd, allow_failure=True)
    record = {"target": target, "service": service, "profile": profile or "", "exit_code": code}
    if code == 0:
        summary["started"].append(record)
    else:
        record["reason"] = "compose up failed"
        summary["failed"].append(record)


def stop_all_services(summary: dict[str, Any], ctx: Context, args: argparse.Namespace) -> None:
    """Run `compose down` (with `-v` when `--volumes`) and record the outcome."""
    _emit_cli_event(
        "info",
        "dispatch_target",
        "Dispatching setup down target",
        {
            "action": "setup_down",
            "target": "all",
            "service": "all",
            "profile": "",
            "volumes": bool(args.volumes),
        },
    )
    cmd = compose_base(ctx) + ["down"]
    if args.volumes:
        cmd.append("-v")
    code = run(cmd, allow_failure=True)
    record = {"target": "all", "service": "all", "profile": "", "exit_code": code}
    if code == 0:
        summary["stopped"].append(record)
    else:
        record["reason"] = "compose down failed"
        summary["failed"].append(record)


def stop_setup_target(summary: dict[str, Any], ctx: Context, target: str, args: argparse.Namespace) -> None:
    """Run `compose stop` (then `rm -f` when `--remove`) for one target."""
    service, profile = START_TARGETS[target]
    _emit_cli_event(
        "info",
        "dispatch_target",
        "Dispatching setup down target",
        {
            "action": "setup_down",
            "target": target,
            "service": service,
            "profile": profile or "",
            "remove": bool(args.remove),
        },
    )
    cmd = _profiled_compose(ctx, profile)
    cmd += ["stop", service]
    code = run(cmd, allow_failure=True)
    record = {"target": target, "service": service, "profile": profile or "", "exit_code": code}
    if code != 0:
        record["reason"] = "compose stop failed"
        summary["failed"].append(record)
        return
    if args.remove and not _remove_setup_target(record, ctx, service, profile):
        summary["failed"].append(record)
        return
    summary["stopped"].append(record)


def _remove_setup_target(record: dict[str, Any], ctx: Context, service: str, profile: str | None) -> bool:
    rm_cmd = _profiled_compose(ctx, profile)
    rm_cmd += ["rm", "-f", service]
    rm_code = run(rm_cmd, allow_failure=True)
    record["remove_exit_code"] = rm_code
    if rm_code != 0:
        record["reason"] = "compose rm failed"
        return False
    return True


def record_compose_status(summary: dict[str, Any], ctx: Context) -> None:
    """Capture `compose ps` (exit code, stdout, stderr) into the summary."""
    ps_cmd = compose_base(ctx) + ["ps"]
    code, out, err = run_capture(ps_cmd, timeout_s=20.0)
    summary["status"] = {"exit_code": code}
    if out.strip():
        summary["status"]["stdout"] = out.strip()
    if err.strip():
        summary["status"]["stderr"] = err.strip()
