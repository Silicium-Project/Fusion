"""Subprocess helpers and terminal colours.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.cli.constants import REPO_ROOT

try:
    from colorama import Fore, Style
    from colorama import init as colorama_init
except ImportError:  # pragma: no cover
    colorama_init = None
    Fore = Style = None  # type: ignore


COLOR_ENABLED = False


if colorama_init:
    colorama_init()
    COLOR_ENABLED = True
    COLOR_CYAN = Fore.CYAN
    COLOR_GREEN = Fore.GREEN
    COLOR_YELLOW = Fore.YELLOW
    COLOR_RESET = Style.RESET_ALL
else:  # pragma: no cover
    COLOR_CYAN = COLOR_GREEN = COLOR_YELLOW = COLOR_RESET = ""


def colorize(text: str, color: str) -> str:
    if not COLOR_ENABLED:
        return text
    return f"{color}{text}{COLOR_RESET}"


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict | None = None,
    allow_failure: bool = False,
    timeout_s: float | None = None,
) -> int:
    pretty = " ".join(cmd)
    print(colorize(f">> {pretty}", COLOR_GREEN))
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env=env,
        check=not allow_failure,
        timeout=timeout_s,
    )
    if allow_failure and result.returncode:
        print(colorize(f"[WARN] Command failed but ignored (code {result.returncode})", COLOR_YELLOW))
    return result.returncode


def _decode_output(raw: bytes) -> str:
    if not raw:
        return ""
    if b"\x00" in raw:
        for encoding in ("utf-16-le", "utf-16"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def run_capture(cmd: list[str], *, timeout_s: float = 8.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            check=False,
            timeout=timeout_s,
        )
        return result.returncode, _decode_output(result.stdout), _decode_output(result.stderr)
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout_s}s"
    except OSError as exc:
        return 127, "", str(exc)
