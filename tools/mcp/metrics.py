"""In-memory Prometheus counters for the MCP server (served on ``/metrics``).

Counters are kept per process and reset on restart. ``render`` produces the
Prometheus text exposition format (version 0.0.4); metric names and labels are
scraped by monitoring and must stay stable.
"""

from __future__ import annotations

import threading


def prom_escape(value: str) -> str:
    """Escape a Prometheus label value."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _family_header(lines: list[str], name: str, help_text: str, kind: str) -> None:
    lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"])


class McpMetrics:
    """Thread-safe HTTP, JSON-RPC and tool counters."""

    def __init__(self) -> None:
        # NOTE: McpHttpApp.rotate_token also takes this lock (historical).
        self._lock = threading.Lock()
        self._http_requests: dict[tuple[str, str, str], int] = {}
        self._http_duration_sum_s: dict[tuple[str, str], float] = {}
        self._http_duration_count: dict[tuple[str, str], int] = {}
        self._jsonrpc_calls: dict[tuple[str, str], int] = {}
        self._tool_calls: dict[str, int] = {}
        self._tool_failures: dict[str, int] = {}
        self._tool_duration_sum_s: dict[str, float] = {}
        self._tool_duration_count: dict[str, int] = {}

    def inc_http(self, method: str, path: str, status: int, duration_s: float) -> None:
        """Count one HTTP request and its duration."""
        m = method.upper()
        p = path
        s = str(status)
        with self._lock:
            self._http_requests[(m, p, s)] = self._http_requests.get((m, p, s), 0) + 1
            self._http_duration_sum_s[(m, p)] = self._http_duration_sum_s.get((m, p), 0.0) + float(duration_s)
            self._http_duration_count[(m, p)] = self._http_duration_count.get((m, p), 0) + 1

    def inc_jsonrpc(self, method: str, ok: bool) -> None:
        """Count one JSON-RPC call on ``/mcp`` (label ``is_error``)."""
        key = (method, "false" if ok else "true")
        with self._lock:
            self._jsonrpc_calls[key] = self._jsonrpc_calls.get(key, 0) + 1

    def observe_tool_call(self, tool: str, ok: bool, duration_s: float) -> None:
        """Count one tool invocation, its duration and whether it failed."""
        with self._lock:
            self._tool_calls[tool] = self._tool_calls.get(tool, 0) + 1
            self._tool_duration_sum_s[tool] = self._tool_duration_sum_s.get(tool, 0.0) + float(duration_s)
            self._tool_duration_count[tool] = self._tool_duration_count.get(tool, 0) + 1
            if not ok:
                self._tool_failures[tool] = self._tool_failures.get(tool, 0) + 1

    def render(self) -> str:
        """Return all counters in the Prometheus text format."""
        lines: list[str] = []
        with self._lock:
            self._render_http(lines)
            self._render_jsonrpc(lines)
            self._render_tools(lines)
        return "\n".join(lines) + "\n"

    def _render_http(self, lines: list[str]) -> None:
        _family_header(
            lines, "mcp_http_requests_total", "Total HTTP requests served by the MCP server.", "counter"
        )
        for (method, path, status), value in sorted(self._http_requests.items()):
            lines.append(
                'mcp_http_requests_total{method="%s",path="%s",status="%s"} %d'
                % (prom_escape(method), prom_escape(path), prom_escape(status), value)
            )

        _family_header(
            lines, "mcp_http_request_duration_seconds", "HTTP request durations (sum/count).", "summary"
        )
        for (method, path), value in sorted(self._http_duration_sum_s.items()):
            lines.append(
                'mcp_http_request_duration_seconds_sum{method="%s",path="%s"} %.6f'
                % (prom_escape(method), prom_escape(path), float(value))
            )
        for (method, path), value in sorted(self._http_duration_count.items()):
            lines.append(
                'mcp_http_request_duration_seconds_count{method="%s",path="%s"} %d'
                % (prom_escape(method), prom_escape(path), value)
            )

    def _render_jsonrpc(self, lines: list[str]) -> None:
        _family_header(lines, "mcp_jsonrpc_calls_total", "Total JSON-RPC calls received on /mcp.", "counter")
        for (method, is_error), value in sorted(self._jsonrpc_calls.items()):
            lines.append(
                'mcp_jsonrpc_calls_total{method="%s",is_error="%s"} %d'
                % (prom_escape(method), prom_escape(is_error), value)
            )

    def _render_tools(self, lines: list[str]) -> None:
        _family_header(
            lines,
            "mcp_tool_calls_total",
            "Total tool invocations (HTTP /tools and MCP tools/call).",
            "counter",
        )
        for tool, value in sorted(self._tool_calls.items()):
            lines.append('mcp_tool_calls_total{tool="%s"} %d' % (prom_escape(tool), value))

        _family_header(lines, "mcp_tool_failures_total", "Total failed tool invocations.", "counter")
        for tool, value in sorted(self._tool_failures.items()):
            lines.append('mcp_tool_failures_total{tool="%s"} %d' % (prom_escape(tool), value))

        _family_header(
            lines, "mcp_tool_call_duration_seconds", "Tool invocation durations (sum/count).", "summary"
        )
        for tool, value in sorted(self._tool_duration_sum_s.items()):
            lines.append('mcp_tool_call_duration_seconds_sum{tool="%s"} %.6f' % (prom_escape(tool), float(value)))
        for tool, value in sorted(self._tool_duration_count.items()):
            lines.append('mcp_tool_call_duration_seconds_count{tool="%s"} %d' % (prom_escape(tool), value))
