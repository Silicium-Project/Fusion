"""`setup up` and `setup down`: start or stop several local Docker targets at
once, with Docker/Compose preflight checks and a structured summary.

The individual Compose actions live in `setup_steps.py`; the summary format
and its rendering live in `setup_summary.py`.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Iterable

from tools.cli.commands.setup_steps import (
    record_compose_preflight,
    record_compose_status,
    record_docker_preflight,
    start_setup_target,
    stop_all_services,
    stop_setup_target,
)
from tools.cli.commands.setup_summary import _emit_setup_summary
from tools.cli.constants import SETUP_DEFAULT_TARGETS, SETUP_TARGET_CHOICES
from tools.cli.context import Context
from tools.cli.docker import docker_health


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _resolve_setup_targets(args: argparse.Namespace) -> list[str]:
    targets = list(args.target or [])
    if args.full:
        targets = list(SETUP_TARGET_CHOICES)
    if not targets:
        targets = list(SETUP_DEFAULT_TARGETS)
    if args.no_proxy:
        targets = [item for item in targets if item != "proxy"]
    return _dedupe(targets)


def _abort(summary: dict[str, Any], args: argparse.Namespace) -> None:
    _emit_setup_summary(summary, as_json=args.json)
    sys.exit(1)


def _finish(summary: dict[str, Any], args: argparse.Namespace, ctx: Context) -> None:
    # Always report `compose ps`, then fail the command if any target failed.
    record_compose_status(summary, ctx)
    _emit_setup_summary(summary, as_json=args.json)
    if summary["failed"]:
        sys.exit(1)


def cmd_setup_up(args: argparse.Namespace, ctx: Context) -> None:
    """Start the selected targets (default localnet+proxy) with `compose up -d`."""
    targets = _resolve_setup_targets(args)
    summary: dict[str, Any] = {
        "action": "setup up",
        "targets": targets,
        "preflight": {},
        "started": [],
        "failed": [],
        "skipped": [],
    }

    health = docker_health(ctx, retries=2, timeout_s=8.0)
    if not record_docker_preflight(summary, health):
        if os.name == "nt":
            summary["preflight"]["hint"] = "Run `python silicium doctor` for WSL integration hints."
        _abort(summary, args)
    if not record_compose_preflight(summary, ctx):
        _abort(summary, args)

    for target in targets:
        start_setup_target(summary, ctx, target)
    _finish(summary, args, ctx)


def configure_setup_up(parser: argparse.ArgumentParser) -> None:
    """Register the `setup up` options."""
    parser.add_argument(
        "--target",
        choices=SETUP_TARGET_CHOICES,
        action="append",
        help="Target to start (repeatable). Defaults to localnet+proxy.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Start all targets (localnet, devnet, testnet, mainnet, proxy).",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Exclude proxy from selected targets.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON summary.",
    )


def cmd_setup_down(args: argparse.Namespace, ctx: Context) -> None:
    """Stop the selected targets, or everything with `compose down`."""
    targets = _dedupe(list(args.target or []))
    summary: dict[str, Any] = {
        "action": "setup down",
        "targets": targets,
        "preflight": {},
        "stopped": [],
        "failed": [],
        "skipped": [],
    }

    health = docker_health(ctx, retries=1, timeout_s=6.0)
    if not record_docker_preflight(summary, health):
        _abort(summary, args)

    if not targets:
        stop_all_services(summary, ctx, args)
    else:
        for target in targets:
            stop_setup_target(summary, ctx, target, args)
    _finish(summary, args, ctx)


def configure_setup_down(parser: argparse.ArgumentParser) -> None:
    """Register the `setup down` options."""
    parser.add_argument(
        "--target",
        choices=SETUP_TARGET_CHOICES,
        action="append",
        help="Target to stop (repeatable). If omitted, runs compose down.",
    )
    parser.add_argument(
        "-v",
        "--volumes",
        action="store_true",
        help="When stopping all, also remove volumes (compose down -v).",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="When stopping selected targets, also remove containers.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON summary.",
    )
