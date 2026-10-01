"""MCP server observability: Prometheus metrics counters (``/metrics``) and
structured JSON logs (``--log-format json``) for HTTP and tool events.
"""

import json
import re
import subprocess
from pathlib import Path

from tests.mcp_server_support import (
    DEFAULT_EXPORTS,
    _base_url,
    _find_free_port,
    _http_get,
    _http_post,
    _mcp_server_cmd,
    _running_server,
    _server_env,
    _start_server,
    _wait_ready,
    _write_exports,
)


def test_mcp_server_metrics_counters(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    cmd = _mcp_server_cmd(port, "--enable-tools", "--log-format", "json")
    with _running_server(cmd, _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)

        _http_get(base + "/healthz")
        _http_get(base + "/healthz")
        _http_post(base + "/tools", {"name": "tools.silicium.interrupt_action", "args": {}})
        _http_post(base + "/tools", {"name": "tools.silicium.run_action", "args": {}})

        code, body = _http_get(base + "/metrics")
        assert code == 200

        m = re.search(r'mcp_http_requests_total\{method="GET",path="/healthz",status="200"\}\s+(\d+)', body)
        assert m is not None
        assert int(m.group(1)) >= 2

        m = re.search(r'mcp_tool_calls_total\{tool="tools\.silicium\.interrupt_action"\}\s+(\d+)', body)
        assert m is not None
        assert int(m.group(1)) >= 1

        m = re.search(r'mcp_tool_failures_total\{tool="tools\.silicium\.run_action"\}\s+(\d+)', body)
        assert m is not None
        assert int(m.group(1)) >= 1

        m = re.search(r'mcp_tool_call_duration_seconds_count\{tool="tools\.silicium\.interrupt_action"\}\s+(\d+)', body)
        assert m is not None
        assert int(m.group(1)) >= 1


def _stop_and_collect_stdout(proc: subprocess.Popen) -> str:
    # The logs are read from stdout, so the process is drained with
    # communicate() instead of the plain wait() of `_running_server`.
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=3)
    return out


def _json_events(out: str) -> list[dict]:
    events = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def test_mcp_server_json_logs_include_http_and_tool_events(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    proc = _start_server(_mcp_server_cmd(port, "--enable-tools", "--log-format", "json"), _server_env(export_dir))
    try:
        base = _base_url(port)
        _wait_ready(base)
        _http_get(base + "/healthz")
        _http_post(base + "/tools", {"name": "tools.silicium.interrupt_action", "args": {}})
        _http_post(base + "/tools", {"name": "tools.silicium.run_action", "args": {}})
    finally:
        out = _stop_and_collect_stdout(proc)

    events = _json_events(out)

    assert any(evt.get("event") == "listen" for evt in events)

    http_events = [evt for evt in events if evt.get("event") == "http_request"]
    assert http_events
    assert any(
        evt.get("path") == "/healthz"
        and evt.get("method") == "GET"
        and isinstance(evt.get("duration_ms"), (int, float))
        for evt in http_events
    )

    tool_events = [evt for evt in events if evt.get("event") == "tool_call"]
    assert tool_events
    assert any(
        evt.get("tool") == "tools.silicium.interrupt_action"
        and evt.get("transport") == "http_tools"
        and evt.get("ok") is True
        for evt in tool_events
    )
    assert any(
        evt.get("tool") == "tools.silicium.run_action"
        and evt.get("ok") is False
        and evt.get("error") == "ValueError"
        for evt in tool_events
    )
