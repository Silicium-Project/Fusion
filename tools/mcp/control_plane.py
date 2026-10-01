"""Out-of-process control requests for the network node.

The control tools (interrupt, runner mode selection) do not act directly: they
atomically (re)write ``control.request.json`` in the export directory, which
the node polls. Only the latest request is kept.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Mapping

from .persistence import atomic_write_text, compact_json, utc_now


class McpControlPlane:
    """
    Writes control requests into the export directory so a network node can
    consume them out-of-process.
    """

    def __init__(self, export_dir: Path) -> None:
        self._path = export_dir / "control.request.json"
        self._lock = threading.Lock()

    def request_interrupt(self) -> None:
        """Ask the node to interrupt the running action."""
        self._write({"kind": "interrupt", "timestamp_utc": utc_now()})

    def request_mode(self, mode: str) -> None:
        """Ask the node to switch to runner ``mode``."""
        self._write({"kind": "select_runner_mode", "mode": mode, "timestamp_utc": utc_now()})

    def _write(self, payload: Mapping[str, Any]) -> None:
        with self._lock:
            atomic_write_text(self._path, compact_json(payload))
