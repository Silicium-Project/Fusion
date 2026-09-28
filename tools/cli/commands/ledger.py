"""`ledger` commands: list, wipe, export and import Solana ledger volumes.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from tools.cli.constants import LEDGER_NETWORKS, LEDGER_SUFFIX
from tools.cli.context import Context
from tools.cli.docker import confirm, ensure_docker_healthy
from tools.cli.proc import COLOR_YELLOW, colorize, run


def ledger_volume_name(network: str, ctx: Context) -> str:
    suffix = LEDGER_SUFFIX[network]
    return f"{ctx.config.ledger_prefix}-{suffix}"


def ledger_wipe(*, networks: Iterable[str], assume_yes: bool = False, ctx: Context) -> None:
    ensure_docker_healthy(ctx, retries=2, timeout_s=8.0)
    volumes = [ledger_volume_name(net, ctx) for net in networks]
    if not volumes:
        print("No ledger volumes selected.")
        return
    if not assume_yes:
        listing = "\n  ".join(volumes)
        if not confirm(f"Delete the following volumes?\n  {listing}"):
            print("Aborted.")
            return
    for volume in volumes:
        cmd = [ctx.config.docker_bin, "volume", "rm", "-f", volume]
        try:
            run(cmd)
        except subprocess.CalledProcessError as exc:
            print(f"Warning: failed to remove {volume} ({exc}).")


def cmd_ledger_list(_: argparse.Namespace, ctx: Context) -> None:
    ensure_docker_healthy(ctx, retries=2, timeout_s=8.0)
    try:
        result = subprocess.run(
            [ctx.config.docker_bin, "volume", "ls", "--format", "{{.Name}}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"Failed to list volumes via {ctx.config.docker_bin}: {exc}")
        sys.exit(exc.returncode)
    names = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith(f"{ctx.config.ledger_prefix}-")
    ]
    if not names:
        print("No Silicium ledger volumes found.")
        return
    print("Ledger volumes:")
    for name in names:
        print(f"  - {name}")


def configure_ledger_list(parser: argparse.ArgumentParser) -> None:
    pass


def cmd_ledger_wipe(args: argparse.Namespace, ctx: Context) -> None:
    if args.all:
        networks = list(LEDGER_SUFFIX.keys())
    else:
        selected: list[str] = []
        if args.network:
            selected.extend(args.network)
        if args.networks:
            selected.extend(args.networks)
        networks = list(dict.fromkeys(selected))
    if not networks:
        print("Specify networks (positional or --network) or use --all.")
        sys.exit(1)
    ledger_wipe(networks=networks, assume_yes=args.yes, ctx=ctx)


def configure_ledger_wipe(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-n",
        "--network",
        choices=sorted(LEDGER_SUFFIX.keys()),
        action="append",
        help="Network to wipe (repeatable).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Wipe all known ledger volumes.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    parser.add_argument(
        "networks",
        nargs="*",
        choices=LEDGER_NETWORKS,
        help="Network names to wipe (shortcut for repeated --network).",
    )


def ledger_export(target: str, dest: Path, ctx: Context) -> None:
    cmd = [
        ctx.config.docker_bin,
        "run",
        "--rm",
        "-v",
        f"{target}:/data:ro",
        "-v",
        f"{dest.parent}:/backup",
        "alpine",
        "sh",
        "-c",
        "cd /data && tar czf /backup/ledger.tar.gz .",
    ]
    run(cmd)


def ledger_import(target: str, src: Path, ctx: Context) -> None:
    if not src.exists():
        print(f"Archive not found: {src}")
        sys.exit(1)
    cmd = [
        ctx.config.docker_bin,
        "run",
        "--rm",
        "-v",
        f"{target}:/data",
        "-v",
        f"{src.parent}:/backup",
        "alpine",
        "sh",
        "-c",
        "rm -rf /data/* && tar xzf /backup/ledger.tar.gz -C /data",
    ]
    env = os.environ.copy()
    env["LEDGER_ARCHIVE"] = str(src)
    run(cmd, env=env)


def cmd_ledger_export(args: argparse.Namespace, ctx: Context) -> None:
    ensure_docker_healthy(ctx, retries=2, timeout_s=8.0)
    volume = ledger_volume_name(args.network, ctx)
    dest = Path(args.output or f"{volume}.tar.gz").resolve()
    if dest.exists() and not args.force:
        print(f"{dest} already exists. Use --force to overwrite.")
        sys.exit(1)
    print(colorize(f"Exporting {volume} -> {dest}", COLOR_YELLOW))
    cmd = [
        ctx.config.docker_bin,
        "run",
        "--rm",
        "-v",
        f"{volume}:/data:ro",
        "-v",
        f"{dest.parent}:/backup",
        "alpine",
        "sh",
        "-c",
        f"cd /data && tar czf /backup/{dest.name} .",
    ]
    run(cmd)


def configure_ledger_export(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "network",
        choices=LEDGER_NETWORKS,
        help="Which ledger to export.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output tar.gz path (default: <volume>.tar.gz).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite the output file if it exists.",
    )


def cmd_ledger_import(args: argparse.Namespace, ctx: Context) -> None:
    ensure_docker_healthy(ctx, retries=2, timeout_s=8.0)
    volume = ledger_volume_name(args.network, ctx)
    archive = Path(args.archive).resolve()
    if not archive.exists():
        print(f"Archive not found: {archive}")
        sys.exit(1)
    if not args.yes and not confirm(f"Overwrite volume {volume} from {archive}?"):
        print("Aborted.")
        return
    cmd = [
        ctx.config.docker_bin,
        "run",
        "--rm",
        "-v",
        f"{volume}:/data",
        "-v",
        f"{archive.parent}:/backup",
        "alpine",
        "sh",
        "-c",
        f"rm -rf /data/* && tar xzf /backup/{archive.name} -C /data",
    ]
    run(cmd)


def configure_ledger_import(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "network",
        choices=LEDGER_NETWORKS,
        help="Which ledger to import into.",
    )
    parser.add_argument(
        "--archive",
        required=True,
        help="Path to the tar.gz archive to restore.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
