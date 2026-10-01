"""Single-service Docker Compose commands: `start`, `stop`, `status`, `logs`
and `exec`.

They are thin wrappers over `tools/cli/docker.py`; for several targets at once
with a structured summary, see `setup up` / `setup down` (`setup.py`).
"""

from __future__ import annotations

import argparse

from tools.cli.constants import START_CHOICES, START_TARGETS
from tools.cli.context import Context
from tools.cli.docker import (
    compose_base,
    compose_down,
    compose_stop,
    compose_up,
    resolve_service,
)
from tools.cli.proc import run


def cmd_start(args: argparse.Namespace, ctx: Context) -> None:
    """Start one service (`compose up`)."""
    service, profile = START_TARGETS[args.target]
    compose_up(service, profile, ctx, target=args.target)


def configure_start(parser: argparse.ArgumentParser) -> None:
    """Register the `start` positional target."""
    parser.add_argument(
        "target",
        choices=START_CHOICES,
        help="Which service to start.",
    )


def cmd_stop(args: argparse.Namespace, ctx: Context) -> None:
    """Stop one service, or all of them (`compose down`) by default."""
    target = args.target or "all"
    if target == "all":
        compose_down(ctx, volumes=args.volumes)
    else:
        service, profile = START_TARGETS[target]
        compose_stop(service, profile, ctx, remove=args.remove, target=target)


def configure_stop(parser: argparse.ArgumentParser) -> None:
    """Register the `stop` target and options."""
    parser.add_argument(
        "target",
        nargs="?",
        choices=START_CHOICES + ["all"],
        help="Service to stop (default all).",
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
        help="When stopping a single service, also remove its container.",
    )


def cmd_status(args: argparse.Namespace, ctx: Context) -> None:
    """Show `compose ps`."""
    cmd = compose_base(ctx) + ["ps"]
    run(cmd)


def configure_status(parser: argparse.ArgumentParser) -> None:
    """`status` takes no option."""
    pass


def cmd_logs(args: argparse.Namespace, ctx: Context) -> None:
    """Show (or follow) the logs of one service."""
    service, profile = resolve_service(args.target)
    cmd = compose_base(ctx)
    if profile:
        cmd += ["--profile", profile]
    cmd += ["logs"]
    if args.follow:
        cmd.append("-f")
    cmd.append(service)
    run(cmd)


def configure_logs(parser: argparse.ArgumentParser) -> None:
    """Register the `logs` target and options."""
    parser.add_argument(
        "target",
        nargs="?",
        default="localnet",
        help="Service alias or compose name (default localnet).",
    )
    parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow logs (docker compose logs -f).",
    )


def cmd_exec(args: argparse.Namespace, ctx: Context) -> None:
    """Run a command (default `/bin/bash`) inside a service container."""
    service_name, profile = resolve_service(args.service)
    cmd = compose_base(ctx) + ["exec"]
    if profile:
        cmd += ["--profile", profile]
    if args.user:
        cmd += ["-u", args.user]
    cmd.append(service_name)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        command = ["/bin/bash"]
    cmd += command
    run(cmd)


def configure_exec(parser: argparse.ArgumentParser) -> None:
    """Register the `exec` service, user and command arguments."""
    parser.add_argument(
        "service",
        help="Service alias or compose name.",
    )
    parser.add_argument(
        "-u",
        "--user",
        help="User to run as inside the container.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run (default /bin/bash).",
    )
