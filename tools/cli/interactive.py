"""Interactive shell (`silicium shell`): readline history and completion.
"""

from __future__ import annotations

import argparse
import atexit
import json
import shlex

from tools.cli.constants import (
    HISTORY_FILE,
    LEDGER_NETWORKS,
    LOG_CHOICES,
    PERF_BUDGET_FILE,
    SETUP_TARGET_CHOICES,
    START_CHOICES,
    SUBCOMMANDS,
    TOP_LEVEL_COMMANDS,
    TUI_CONNECTORS,
    TUI_FRONTENDS,
    WORKLOAD_TAXONOMY_CATEGORIES,
    WORKLOAD_TAXONOMY_COMPLEXITIES,
    WORKLOAD_TAXONOMY_DETERMINISM,
    WORKLOAD_TAXONOMY_DOMAINS,
    WORKLOAD_TAXONOMY_RESOURCE_PROFILES,
    WORKLOAD_TAXONOMY_TAGS,
)
from tools.cli.context import Context
from tools.cli.proc import COLOR_CYAN, COLOR_ENABLED, COLOR_GREEN, COLOR_RESET, colorize
from tools.cli.workload.manifest import workload_paths
from tools.i18n import set_runtime_locale, tr

try:
    import readline
except ImportError:  # pragma: no cover - windows fallback
    readline = None  # type: ignore[assignment]


def setup_readline(parser: argparse.ArgumentParser) -> None:
    if not readline:  # pragma: no cover - depends on platform
        return
    history_file = HISTORY_FILE
    try:
        history_file.touch(exist_ok=True)
    except OSError:
        history_file = None  # type: ignore
    else:
        try:
            readline.read_history_file(history_file)
        except OSError:
            pass
        def _save_history(file_path=history_file):
            try:
                readline.write_history_file(file_path)  # type: ignore[arg-type]
            except OSError as exc:
                print(f"Warning: unable to write history file: {exc}")

        atexit.register(_save_history)
    readline.set_history_length(1000)
    readline.parse_and_bind("tab: complete")

    def completer(text: str, state: int) -> str | None:
        buffer = readline.get_line_buffer()
        begidx = readline.get_begidx()
        prefix = buffer[:begidx]
        try:
            tokens = shlex.split(prefix)
        except ValueError:
            tokens = prefix.split()
        options = _completion_options(tokens, text)
        try:
            return options[state]
        except IndexError:
            return None

    readline.set_completer(completer)


def _completion_options(tokens: list[str], text: str) -> list[str]:
    if not tokens:
        return [cmd for cmd in TOP_LEVEL_COMMANDS if cmd.startswith(text)]
    first = tokens[0]
    subcommands = SUBCOMMANDS.get(first)
    if subcommands:
        if len(tokens) == 1:
            return [cmd for cmd in subcommands if cmd.startswith(text)]
    if first == "ledger":
        if len(tokens) == 1:
            return [cmd for cmd in SUBCOMMANDS["ledger"] if cmd.startswith(text)]
        sub = tokens[1]
        if sub == "wipe":
            opts = ["--network", "-n", "--all", "--yes", "-y"]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            if tokens[-1] in {"--network", "-n"}:
                return [net for net in LEDGER_NETWORKS if net.startswith(text)]
            return [net for net in LEDGER_NETWORKS if net.startswith(text)]
        if sub == "export":
            opts = ["--output", "-o", "--force"]
            if len(tokens) <= 2:
                return [net for net in LEDGER_NETWORKS if net.startswith(text)]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            if tokens[-1] in opts:
                return []
            return [net for net in LEDGER_NETWORKS if net.startswith(text)]
        if sub == "import":
            opts = ["--archive", "-y", "--yes"]
            if len(tokens) <= 2:
                return [net for net in LEDGER_NETWORKS if net.startswith(text)]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            if tokens[-1] == "--archive":
                return []
            return [net for net in LEDGER_NETWORKS if net.startswith(text)]
        return []
    if first == "clean":
        if len(tokens) == 1:
            return [cmd for cmd in SUBCOMMANDS["clean"] if cmd.startswith(text)]
        flags = ["-y", "--yes", "--ledgers"]
        return [flag for flag in flags if flag.startswith(text)]
    if first == "setup":
        if len(tokens) == 1:
            return [cmd for cmd in SUBCOMMANDS["setup"] if cmd.startswith(text)]
        sub = tokens[1]
        if sub == "up":
            flags = ["--target", "--full", "--no-proxy", "--json"]
            if text.startswith("-"):
                return [flag for flag in flags if flag.startswith(text)]
            if tokens[-1] == "--target":
                return [opt for opt in SETUP_TARGET_CHOICES if opt.startswith(text)]
            return [opt for opt in SETUP_TARGET_CHOICES if opt.startswith(text)]
        if sub == "down":
            flags = ["--target", "-v", "--volumes", "--remove", "--json"]
            if text.startswith("-"):
                return [flag for flag in flags if flag.startswith(text)]
            if tokens[-1] == "--target":
                return [opt for opt in SETUP_TARGET_CHOICES if opt.startswith(text)]
            return [opt for opt in SETUP_TARGET_CHOICES if opt.startswith(text)]
        return []
    if first == "check":
        flags = [
            "--full",
            "--docker",
            "--no-docker",
            "--require-docker",
            "--python",
        ]
        return [flag for flag in flags if flag.startswith(text)]
    if first == "doctor":
        return []
    if first == "budget":
        flags = [
            "--budget-file",
            "--profile",
            "--all",
            "--strict",
            "--output",
            "--list",
        ]
        if text.startswith("-"):
            return [flag for flag in flags if flag.startswith(text)]
        if tokens[-1] == "--profile" and PERF_BUDGET_FILE.exists():
            try:
                raw = json.loads(PERF_BUDGET_FILE.read_text(encoding="utf-8"))
                profiles = raw.get("profiles", {})
                if isinstance(profiles, dict):
                    return [str(key) for key in profiles.keys() if str(key).startswith(text)]
            except Exception:
                return []
        return []
    if first == "history":
        if len(tokens) == 1:
            return [cmd for cmd in SUBCOMMANDS["history"] if cmd.startswith(text)]
        if tokens[1] == "show":
            return [flag for flag in ["--tail"] if flag.startswith(text)]
        return []
    if first == "start":
        if len(tokens) == 1:
            return [opt for opt in START_CHOICES if opt.startswith(text)]
        return []
    if first == "stop":
        choices = START_CHOICES + ["all"]
        if len(tokens) == 1:
            return [opt for opt in choices if opt.startswith(text)]
        return [flag for flag in ["-v", "--volumes", "--remove"] if flag.startswith(text)]
    if first == "workload":
        if len(tokens) == 1:
            return [cmd for cmd in SUBCOMMANDS["workload"] if cmd.startswith(text)]
        sub = tokens[1]
        taxonomy_flags = [
            "--category",
            "--domain",
            "--complexity",
            "--resource-profile",
            "--determinism",
            "--tag",
        ]
        if sub == "list":
            if text.startswith("-"):
                return [
                    flag
                    for flag in (["--tree", "--details", "--json"] + taxonomy_flags)
                    if flag.startswith(text)
                ]
            if tokens[-1] == "--category":
                return [value for value in WORKLOAD_TAXONOMY_CATEGORIES if value.startswith(text)]
            if tokens[-1] == "--domain":
                return [value for value in WORKLOAD_TAXONOMY_DOMAINS if value.startswith(text)]
            if tokens[-1] == "--complexity":
                return [value for value in WORKLOAD_TAXONOMY_COMPLEXITIES if value.startswith(text)]
            if tokens[-1] == "--resource-profile":
                return [value for value in WORKLOAD_TAXONOMY_RESOURCE_PROFILES if value.startswith(text)]
            if tokens[-1] == "--determinism":
                return [value for value in WORKLOAD_TAXONOMY_DETERMINISM if value.startswith(text)]
            if tokens[-1] == "--tag":
                return [value for value in WORKLOAD_TAXONOMY_TAGS if value.startswith(text)]
            return []
        if sub == "show":
            if text.startswith("-"):
                return [
                    flag
                    for flag in (["--readme", "--meta", "--dry-run", "--preset"] + taxonomy_flags)
                    if flag.startswith(text)
                ]
            if tokens[-1] == "--category":
                return [value for value in WORKLOAD_TAXONOMY_CATEGORIES if value.startswith(text)]
            if tokens[-1] == "--domain":
                return [value for value in WORKLOAD_TAXONOMY_DOMAINS if value.startswith(text)]
            if tokens[-1] == "--complexity":
                return [value for value in WORKLOAD_TAXONOMY_COMPLEXITIES if value.startswith(text)]
            if tokens[-1] == "--resource-profile":
                return [value for value in WORKLOAD_TAXONOMY_RESOURCE_PROFILES if value.startswith(text)]
            if tokens[-1] == "--determinism":
                return [value for value in WORKLOAD_TAXONOMY_DETERMINISM if value.startswith(text)]
            if tokens[-1] == "--tag":
                return [value for value in WORKLOAD_TAXONOMY_TAGS if value.startswith(text)]
            paths = workload_paths()
            return [p for p in paths if p.startswith(text)]
        if sub == "queue":
            opts = ["--summary", "--output"]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            return []
        if sub == "lint":
            opts = ["--root", "--schema", "--json"]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            return []
        if sub == "fixtures":
            opts = ["--json"]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            return []
        if sub == "alignment":
            opts = ["--json", "--strict"]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            return []
        if sub == "golden":
            opts = ["--corpus", "--json", "--strict"]
            if text.startswith("-"):
                return [opt for opt in opts if opt.startswith(text)]
            return []
        return []
    if first == "logs":
        if len(tokens) == 1:
            return [opt for opt in LOG_CHOICES if opt.startswith(text)]
        return [flag for flag in ["-f", "--follow"] if flag.startswith(text)]
    if first == "exec":
        if len(tokens) == 1:
            return [opt for opt in LOG_CHOICES if opt.startswith(text)]
        return [flag for flag in ["-u", "--user"] if flag.startswith(text)]
    if first == "tui":
        flags = [
            "--tui-frontend",
            "--tui-connector",
            "--smoke",
            "--strict-frontend",
            "--headless-script",
            "--headless-timeout",
            "--headless-json",
        ]
        if text.startswith("-"):
            return [flag for flag in flags if flag.startswith(text)]
        if tokens[-1] == "--tui-frontend":
            return [opt for opt in sorted(TUI_FRONTENDS) if opt.startswith(text)]
        if tokens[-1] == "--tui-connector":
            return [opt for opt in sorted(TUI_CONNECTORS) if opt.startswith(text)]
        return [opt for opt in sorted(TUI_FRONTENDS) if opt.startswith(text)]
    return []


def get_prompt() -> str:
    base = tr("cli.shell.name")
    if COLOR_ENABLED:
        return f"{COLOR_CYAN}{base}{COLOR_RESET} {colorize('>', COLOR_GREEN)} "
    return f"{base}> "


def launch_shell(ctx: Context) -> None:
    # Imported here: the registry itself registers the `shell` command below.
    from tools.cli.registry import build_parser

    parser = build_parser(ctx)
    setup_readline(parser)
    print(
        colorize(
            tr("cli.shell.banner"),
            COLOR_CYAN,
        )
    )
    prompt = get_prompt()
    while True:
        try:
            line = input(prompt).strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue
        if not line:
            continue
        if line in {"exit", "quit"}:
            break
        if line in {"help", "?"}:
            parser.print_help()
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            print(tr("cli.shell.parse_error", str(exc)))
            continue
        try:
            args = parser.parse_args(tokens)
            set_runtime_locale(getattr(args, "locale", None))
            args.func(args)
        except SystemExit:
            continue


def cmd_shell(_: argparse.Namespace, ctx: Context) -> None:
    launch_shell(ctx)


def configure_shell(parser: argparse.ArgumentParser) -> None:
    pass
