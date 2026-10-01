"""Rendering of the `setup up` / `setup down` run summary.

The summary is a plain dict built by `setup.py` and filled in by the setup
steps (preflight results, one record per target). It is printed either as
JSON only (`--json`) or as a human-readable report followed by the same JSON.
"""

from __future__ import annotations

import json
from typing import Any

from tools.cli.proc import COLOR_YELLOW, colorize


def _print_preflight(summary: dict[str, Any]) -> None:
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


def _print_target_rows(summary: dict[str, Any]) -> None:
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


def _emit_setup_summary(summary: dict[str, Any], as_json: bool) -> None:
    """Print the summary (JSON only when `as_json`, else report + JSON)."""
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    action = summary.get("action", "setup")
    print(colorize(f"==> {action}", COLOR_YELLOW))
    _print_preflight(summary)
    _print_target_rows(summary)
    print("Summary JSON:")
    print(json.dumps(summary, indent=2, sort_keys=True))
