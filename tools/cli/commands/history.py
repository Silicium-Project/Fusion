"""`history show` and `history clear`: the interactive shell command history.

The history file is written by the interactive shell (`silicium shell`, see
`tools/cli/interactive.py`); these commands only read or reset it.
"""

from __future__ import annotations

import argparse

from tools.cli.constants import HISTORY_FILE
from tools.cli.context import Context
from tools.cli.interactive import readline


def cmd_history_show(args: argparse.Namespace, ctx: Context) -> None:
    """Print the history entries, optionally only the last `--tail` ones."""
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
    """Register the `history show` options."""
    parser.add_argument(
        "--tail",
        type=int,
        help="Show only the last N entries.",
    )


def cmd_history_clear(_: argparse.Namespace, ctx: Context) -> None:
    """Empty the history file and the in-memory readline history."""
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    HISTORY_FILE.touch()
    if readline:
        readline.clear_history()  # type: ignore[arg-type]
    print("History cleared.")


def configure_history_clear(parser: argparse.ArgumentParser) -> None:
    """`history clear` takes no option."""
    pass
