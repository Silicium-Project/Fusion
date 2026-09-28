"""Local services: `setup up/down`, `start`, `stop`, `status`, `logs`, `exec`,
`alias` and `history`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from tools.cli.constants import (
    HISTORY_FILE,
    SETUP_DEFAULT_TARGETS,
    SETUP_TARGET_CHOICES,
    START_CHOICES,
    START_TARGETS,
)
from tools.cli.context import Context
from tools.cli.docker import (
    compose_base,
    compose_command,
    compose_down,
    compose_stop,
    compose_up,
    docker_health,
    resolve_service,
)
from tools.cli.framework import _emit_cli_event
from tools.cli.interactive import readline
from tools.cli.proc import COLOR_YELLOW, colorize, run, run_capture


def cmd_history_show(args: argparse.Namespace, ctx: Context) -> None:
    if not HISTORY_FILE.exists():
        print("No history entries yet.")
        return
    lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    tail = args.tail
    if tail:
        lines = lines[-tail:]
    for line in lines:
        print(line)


def configure_history_show(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tail",
        type=int,
        help="Show only the last N entries.",
    )


def cmd_history_clear(_: argparse.Namespace, ctx: Context) -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    HISTORY_FILE.touch()
    if readline:
        readline.clear_history()  # type: ignore[arg-type]
    print("History cleared.")


def configure_history_clear(parser: argparse.ArgumentParser) -> None:
    pass


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


def _emit_setup_summary(summary: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    action = summary.get("action", "setup")
    print(colorize(f"==> {action}", COLOR_YELLOW))
    preflight = summary.get("preflight", {})
    docker_state = preflight.get("docker", {})
    compose_state = preflight.get("compose", {})
    if docker_state:
        print(f"Docker preflight: {docker_state.get('status', 'unknown')}")
        if docker_state.get("reason"):
            print(f"  reason: {docker_state.get('reason')}")
    if compose_state:
        print(f"Compose preflight: {compose_state.get('status', 'unknown')}")
        if compose_state.get("reason"):
            print(f"  reason: {compose_state.get('reason')}")
    for key in ("started", "stopped", "failed", "skipped"):
        rows = summary.get(key, [])
        if rows:
            print(f"{key.capitalize()}:")
            for row in rows:
                profile = row.get("profile") or "-"
                reason = row.get("reason", "")
                code = row.get("exit_code", "")
                extra = f" profile={profile}"
                if code != "":
                    extra += f" exit={code}"
                if reason:
                    extra += f" reason={reason}"
                print(f"  - {row.get('target', '?')} ({row.get('service', '?')}){extra}")
    print("Summary JSON:")
    print(json.dumps(summary, indent=2, sort_keys=True))


def cmd_setup_up(args: argparse.Namespace, ctx: Context) -> None:
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
    if not health.ok:
        summary["preflight"]["docker"] = {
            "status": "failed",
            "error_code": health.error_code,
            "reason": health.message,
        }
        if os.name == "nt":
            summary["preflight"]["hint"] = "Run `python silicium doctor` for WSL integration hints."
        _emit_setup_summary(summary, as_json=args.json)
        sys.exit(1)
    summary["preflight"]["docker"] = {"status": "ok", "detail": health.detail}

    try:
        compose_command(ctx)
    except SystemExit:
        summary["preflight"]["compose"] = {
            "status": "failed",
            "reason": "Docker Compose not available",
        }
        _emit_setup_summary(summary, as_json=args.json)
        sys.exit(1)
    summary["preflight"]["compose"] = {"status": "ok"}

    for target in targets:
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
        cmd = compose_base(ctx)
        if profile:
            cmd += ["--profile", profile]
        cmd += ["up", "-d", service]
        code = run(cmd, allow_failure=True)
        record = {"target": target, "service": service, "profile": profile or "", "exit_code": code}
        if code == 0:
            summary["started"].append(record)
        else:
            record["reason"] = "compose up failed"
            summary["failed"].append(record)

    ps_cmd = compose_base(ctx) + ["ps"]
    code, out, err = run_capture(ps_cmd, timeout_s=20.0)
    summary["status"] = {"exit_code": code}
    if out.strip():
        summary["status"]["stdout"] = out.strip()
    if err.strip():
        summary["status"]["stderr"] = err.strip()

    _emit_setup_summary(summary, as_json=args.json)
    if summary["failed"]:
        sys.exit(1)


def configure_setup_up(parser: argparse.ArgumentParser) -> None:
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
    if not health.ok:
        summary["preflight"]["docker"] = {
            "status": "failed",
            "error_code": health.error_code,
            "reason": health.message,
        }
        _emit_setup_summary(summary, as_json=args.json)
        sys.exit(1)
    summary["preflight"]["docker"] = {"status": "ok", "detail": health.detail}

    if not targets:
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
    else:
        for target in targets:
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
            cmd = compose_base(ctx)
            if profile:
                cmd += ["--profile", profile]
            cmd += ["stop", service]
            code = run(cmd, allow_failure=True)
            record = {"target": target, "service": service, "profile": profile or "", "exit_code": code}
            if code == 0:
                if args.remove:
                    rm_cmd = compose_base(ctx)
                    if profile:
                        rm_cmd += ["--profile", profile]
                    rm_cmd += ["rm", "-f", service]
                    rm_code = run(rm_cmd, allow_failure=True)
                    record["remove_exit_code"] = rm_code
                    if rm_code != 0:
                        record["reason"] = "compose rm failed"
                        summary["failed"].append(record)
                        continue
                summary["stopped"].append(record)
            else:
                record["reason"] = "compose stop failed"
                summary["failed"].append(record)

    ps_cmd = compose_base(ctx) + ["ps"]
    code, out, err = run_capture(ps_cmd, timeout_s=20.0)
    summary["status"] = {"exit_code": code}
    if out.strip():
        summary["status"]["stdout"] = out.strip()
    if err.strip():
        summary["status"]["stderr"] = err.strip()

    _emit_setup_summary(summary, as_json=args.json)
    if summary["failed"]:
        sys.exit(1)


def configure_setup_down(parser: argparse.ArgumentParser) -> None:
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


def cmd_start(args: argparse.Namespace, ctx: Context) -> None:
    service, profile = START_TARGETS[args.target]
    compose_up(service, profile, ctx, target=args.target)


def configure_start(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        choices=START_CHOICES,
        help="Which service to start.",
    )


def cmd_stop(args: argparse.Namespace, ctx: Context) -> None:
    target = args.target or "all"
    if target == "all":
        compose_down(ctx, volumes=args.volumes)
    else:
        service, profile = START_TARGETS[target]
        compose_stop(service, profile, ctx, remove=args.remove, target=target)


def configure_stop(parser: argparse.ArgumentParser) -> None:
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
    cmd = compose_base(ctx) + ["ps"]
    run(cmd)


def configure_status(parser: argparse.ArgumentParser) -> None:
    pass


def cmd_logs(args: argparse.Namespace, ctx: Context) -> None:
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


def cmd_alias(args: argparse.Namespace, ctx: Context) -> None:
    shell = args.shell or "bash"
    function = '''silicium() {
    local cmd=$1
    shift
    case "$cmd" in
        test|smoke|clean|shell)
            ./silicium "$cmd" "$@"
            ;;
        ledger)
            ./silicium ledger "$@"
            ;;
        history)
            ./silicium history "$@"
            ;;
        start)
            ./silicium start "$@"
            ;;
        stop)
            ./silicium stop "$@"
            ;;
        start-local)
            ./silicium start localnet "$@"
            ;;
        start-dev)
            ./silicium start devnet "$@"
            ;;
        start-test)
            ./silicium start testnet "$@"
            ;;
        start-main)
            ./silicium start mainnet "$@"
            ;;
        *)
            ./silicium "$cmd" "$@"
            ;;
    esac
}'''
    alias_snippet = f"""
# Silicium helper function
{function}
alias sl='silicium ledger list'
alias st='silicium test'
alias ss='silicium smoke'
alias sc='silicium clean cache'
alias sca='silicium clean all -y'
alias shist='silicium history show --tail 20'
alias sstart='silicium start localnet'
alias sstop='silicium stop'
"""

    rc_map = {
        "bash": "~/.bashrc",
        "zsh": "~/.zshrc",
        "fish": "~/.config/fish/config.fish",
    }
    path = args.path or rc_map.get(shell)
    if not path:
        print("Unsupported shell; provide --path to append manually.")
        return
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write("\n" + alias_snippet + "\n")
    print(f"Aliases appended to {target}")


def configure_alias(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--shell",
        choices=["bash", "zsh", "fish"],
        help="Shell type for auto-detection (default bash).",
    )
    parser.add_argument(
        "--path",
        help="Custom rc file to append aliases.",
    )
