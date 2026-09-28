"""Entry point used by the `silicium` script.
"""

from __future__ import annotations

import sys

from tools.cli.commands.tui import run_tui_frontend
from tools.cli.context import build_context
from tools.cli.registry import execute
from tools.i18n import set_runtime_locale


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    ctx = build_context()
    if not argv:
        run_tui_frontend(None, None, ctx)
        return
    locale_only = None
    if len(argv) == 1 and argv[0].startswith("--locale="):
        locale_only = argv[0].split("=", 1)[1]
    elif len(argv) == 2 and argv[0] == "--locale":
        locale_only = argv[1]
    if locale_only is not None:
        set_runtime_locale(locale_only)
        run_tui_frontend(None, None, ctx)
        return
    try:
        execute(argv, ctx)
    except KeyboardInterrupt:
        print()
        sys.exit(1)
