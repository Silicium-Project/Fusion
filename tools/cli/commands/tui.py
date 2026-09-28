"""`tui` command: terminal front-ends and connectors (from `tools/dev/tui`).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from tools.cli.constants import REPO_ROOT, TUI_CONNECTORS, TUI_FRONTENDS
from tools.cli.context import Context
from tools.cli.interactive import launch_shell
from tools.cli.proc import COLOR_YELLOW, colorize
from tools.i18n import tr


def resolve_tui_frontend(requested: str | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    env_frontend = os.environ.get("SILICIUM_TUI_FRONTEND", "").strip().lower()
    candidate = (requested or env_frontend or "textual").strip().lower()
    if candidate not in TUI_FRONTENDS:
        warnings.append(
            f"Unsupported TUI frontend '{candidate}', falling back to textual "
            "(supported: textual, curses, headless)."
        )
        candidate = "textual"
    return candidate, warnings


def resolve_tui_connector(requested: str | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    env_connector = os.environ.get("SILICIUM_TUI_CONNECTOR", "").strip().lower()
    candidate = (requested or env_connector or "inprocess").strip().lower()
    if candidate not in TUI_CONNECTORS:
        warnings.append(
            f"Unsupported TUI connector '{candidate}', falling back to inprocess "
            "(supported: inprocess, stdio, http)."
        )
        candidate = "inprocess"
    return candidate, warnings


def run_tui_frontend(
    requested: str | None,
    requested_connector: str | None,
    ctx: Context,
    *,
    smoke: bool = False,
    strict_frontend: bool = False,
    headless_script: str | None = None,
    headless_timeout: float = 120.0,
    headless_json: str | None = None,
) -> None:
    from tools.dev.tui.connectors import build_connector_registry
    from tools.dev.tui.frontends import FrontendRunConfig, build_frontend_registry

    frontend, warnings = resolve_tui_frontend(requested)
    connector_name, connector_warnings = resolve_tui_connector(requested_connector)
    warnings.extend(connector_warnings)
    registry = build_frontend_registry()
    connector_registry = build_connector_registry()
    connector = connector_registry[connector_name]
    for warning in warnings:
        print(colorize(f"[WARN] {warning}", COLOR_YELLOW))

    if smoke:
        print(tr("cli.tui.probe_requested", frontend))
        if frontend == "headless":
            print(tr("cli.tui.frontend_ok", "headless"))
            return
        if frontend == "curses":
            ok, reason = registry["curses"].probe()
            if ok:
                print(tr("cli.tui.frontend_ok", "curses"))
                return
            print(colorize(f"[WARN] {tr('cli.tui.frontend_unavailable', 'curses', reason)}", COLOR_YELLOW))
            if strict_frontend:
                sys.exit(1)
            print(tr("cli.tui.trying_fallback", "textual"))
            frontend = "textual"
        ok, reason = registry["textual"].probe()
        if ok:
            print(tr("cli.tui.frontend_ok", "textual"))
            return
        print(colorize(f"[WARN] {tr('cli.tui.frontend_unavailable', 'textual', reason)}", COLOR_YELLOW))
        if strict_frontend:
            sys.exit(1)
        print(tr("cli.tui.fallback_ok", "headless"))
        return

    if frontend == "headless":
        script_path = Path(headless_script).expanduser() if headless_script else None
        if script_path and not script_path.is_absolute():
            script_path = (REPO_ROOT / script_path).resolve()
        output_path = Path(headless_json).expanduser() if headless_json else None
        if output_path and not output_path.is_absolute():
            output_path = (REPO_ROOT / output_path).resolve()
        result = registry["headless"].run(
            FrontendRunConfig(
                headless_script=script_path,
                headless_timeout=headless_timeout,
                headless_json=output_path,
                connector=connector,
            )
        )
        if output_path and result.ok and not result.fallback_to_shell:
            print(tr("cli.tui.headless_report_written", str(output_path)))
        if result.fallback_to_shell:
            print(tr("cli.tui.using_headless_shell"))
            launch_shell(ctx)
            return
        if not result.ok:
            print(colorize(f"[FAIL] {result.reason}", COLOR_YELLOW))
            sys.exit(1)
        if result.reason:
            print(result.reason)
        return

    if frontend == "curses":
        result = registry["curses"].run(FrontendRunConfig())
        if result.ok:
            return
        print(colorize(f"[WARN] {tr('cli.tui.falling_back', result.reason, 'textual')}", COLOR_YELLOW))

    result = registry["textual"].run(FrontendRunConfig(connector=connector))
    if result.ok:
        return

    if frontend == "textual":
        print(colorize(f"[WARN] {tr('cli.tui.falling_back', result.reason, 'headless')}", COLOR_YELLOW))
    else:
        print(colorize(f"[WARN] {tr('cli.tui.textual_unavailable_fallback_shell')}", COLOR_YELLOW))
    print(tr("cli.tui.install_textual"))
    launch_shell(ctx)


def cmd_tui(args: argparse.Namespace, ctx: Context) -> None:
    run_tui_frontend(
        args.tui_frontend,
        args.tui_connector,
        ctx,
        smoke=args.smoke,
        strict_frontend=args.strict_frontend,
        headless_script=args.headless_script,
        headless_timeout=args.headless_timeout,
        headless_json=args.headless_json,
    )


def configure_tui(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tui-frontend",
        help="Frontend selection: textual, curses, headless (or SILICIUM_TUI_FRONTEND).",
    )
    parser.add_argument(
        "--tui-connector",
        help="Connector selection: inprocess, stdio, http (or SILICIUM_TUI_CONNECTOR).",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Probe frontend availability and exit without opening interactive UI.",
    )
    parser.add_argument(
        "--strict-frontend",
        action="store_true",
        help="With --smoke, fail if requested frontend is not directly available.",
    )
    parser.add_argument(
        "--headless-script",
        help="Path to a headless TUI script (JSON steps) when using --tui-frontend headless.",
    )
    parser.add_argument(
        "--headless-timeout",
        type=float,
        default=120.0,
        help="Max seconds for headless script completion (default: 120).",
    )
    parser.add_argument(
        "--headless-json",
        help="Optional output path for headless execution snapshot JSON.",
    )
