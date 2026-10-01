"""Request observability for the HTTP handler (mixin).

Replaces ``BaseHTTPRequestHandler``'s stderr access log with structured
``http_request`` / ``tool_call`` log events and Prometheus counters. Each
``do_GET``/``do_POST`` calls ``_obs_begin`` first and ``_obs_end`` in a
``finally`` block.
"""

from __future__ import annotations

import time
import uuid
from typing import Any


class ObservabilityMixin:
    """Tracks status, duration and MCP methods of the current request.

    Must come before ``BaseHTTPRequestHandler`` in the bases so that
    ``send_response`` is intercepted. Expects ``self._app`` (see handler.py).
    """

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:  # noqa: N802
        # Disable BaseHTTPRequestHandler access logging; we emit structured logs ourselves.
        return

    def log_message(self, fmt: str, *args: Any) -> None:
        # Disable BaseHTTPRequestHandler logging; see log_request override above.
        return

    def send_response(self, code: int, message: str | None = None) -> None:  # noqa: N802
        """Record the status code for the access log, then send it."""
        self._resp_status = int(code)
        super().send_response(code, message)

    def _obs_begin(self, path: str) -> None:
        self._req_id = uuid.uuid4().hex
        self._req_start = time.monotonic()
        self._req_path = path
        self._resp_status = 0
        self._mcp_methods: list[str] = []

    def _obs_end(self) -> None:
        # Observability must never break a response: swallow every error.
        try:
            start = getattr(self, "_req_start", None)
            path = getattr(self, "_req_path", "")
            if start is None:
                return
            duration_s = max(0.0, time.monotonic() - float(start))
            status = int(getattr(self, "_resp_status", 0) or 0)
            method = (self.command or "").upper()
            self._app.obs.metrics.inc_http(method, path, status, duration_s)
            self._app.obs.logger.log("http_request", **self._http_log_fields(method, path, status, duration_s))
        except Exception:
            return

    def _http_log_fields(self, method: str, path: str, status: int, duration_s: float) -> dict[str, Any]:
        client_address = self.client_address
        fields: dict[str, Any] = {
            "request_id": getattr(self, "_req_id", ""),
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": round(duration_s * 1000.0, 3),
            "client_ip": (client_address[0] if client_address else ""),
        }
        ua = (self.headers.get("User-Agent") or "").strip()
        if ua:
            fields["user_agent"] = ua[:200]
        mcp_methods = getattr(self, "_mcp_methods", None)
        if mcp_methods:
            fields["mcp_methods"] = mcp_methods[:20]
        return fields

    def _observe_tool_call(self, *, name: str, ok: bool, duration_s: float, transport: str, error: str = "") -> None:
        """Count and log one tool invocation (``transport`` names the entry point)."""
        self._app.obs.metrics.observe_tool_call(name, ok=ok, duration_s=duration_s)
        fields: dict[str, Any] = {
            "request_id": getattr(self, "_req_id", ""),
            "transport": transport,
            "tool": name,
            "ok": bool(ok),
            "duration_ms": round(max(0.0, float(duration_s)) * 1000.0, 3),
        }
        if error:
            fields["error"] = error
        self._app.obs.logger.log("tool_call", **fields)
