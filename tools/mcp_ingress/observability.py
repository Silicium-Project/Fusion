"""Structured logging and the metrics/logger bundle shared by the server.

Logs go to stdout, either as one JSON object per line (``--log-format json``)
or as ``[mcp-http] <event> key='value' ...`` text lines. Events emitted:
``listen``, ``http_request`` and ``tool_call``.
"""

from __future__ import annotations

import sys
from typing import Any

from .metrics import McpMetrics
from .persistence import compact_json, utc_now


class McpLogger:
    """Writes one log line per event to stdout in ``text`` or ``json`` format."""

    def __init__(self, fmt: str) -> None:
        self._fmt = fmt

    def log(self, event: str, **fields: Any) -> None:
        """Emit ``event`` with its fields and flush immediately."""
        if self._fmt == "json":
            payload = {"ts": utc_now(), "event": event, **fields}
            sys.stdout.write(compact_json(payload) + "\n")
            sys.stdout.flush()
            return
        # Any other format value falls back to text.
        parts = [f"{k}={fields[k]!r}" for k in sorted(fields.keys())]
        sys.stdout.write("[mcp-http] " + event + (" " + " ".join(parts) if parts else "") + "\n")
        sys.stdout.flush()


class McpObservability:
    """Holds the metrics registry and the logger of one server instance."""

    def __init__(self, log_format: str) -> None:
        self.metrics = McpMetrics()
        self.logger = McpLogger(log_format)
