"""MCP server access lists: tool and resource allowlists / denylists
(the denylist wins over the allowlist).
"""

import json
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
    _wait_ready,
    _write_exports,
)


def test_mcp_server_tool_access_lists(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    cmd = _mcp_server_cmd(
        port,
        "--enable-tools",
        "--tool-allowlist",
        "tools.silicium.get_health,tools.silicium.interrupt_action",
        "--tool-denylist",
        "tools.silicium.interrupt_action",
    )
    with _running_server(cmd, _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)

        code, body = _http_get(base + "/tools/list")
        assert code == 200
        payload = json.loads(body)
        tools = payload.get("tools", [])
        assert "tools.silicium.get_health" in tools
        assert "tools.silicium.interrupt_action" not in tools

        code, body = _http_post(base + "/tools", {"name": "tools.silicium.interrupt_action", "args": {}})
        assert code == 403
        assert json.loads(body)["error"] == "forbidden_tool"

        code, body = _http_post(base + "/tools", {"name": "tools.silicium.get_health", "args": {}})
        assert code == 200
        wrapped = json.loads(body)
        assert wrapped["ok"] is True


def test_mcp_server_resource_access_lists(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, {**DEFAULT_EXPORTS, "result.task_x.json": '{"value":123}'})

    port = _find_free_port()
    cmd = _mcp_server_cmd(
        port,
        "--resource-allowlist",
        "resources://silicium/results/by-task/*,resources://silicium/status/current",
        "--resource-denylist",
        "resources://silicium/status/current",
    )
    with _running_server(cmd, _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)

        code, body = _http_get(base + "/resources/list")
        assert code == 200
        payload = json.loads(body)
        resources = payload.get("resources", [])
        assert "resources://silicium/results/by-task/{task_id}" in resources
        assert "resources://silicium/status/current" not in resources
        assert "resources://silicium/reports/recent" not in resources

        code, _ = _http_get(base + "/resources?uri=resources://silicium/status/current")
        assert code == 403
        code, _ = _http_get(base + "/resources?uri=resources://silicium/reports/recent")
        assert code == 403

        code, body = _http_get(base + "/resources?uri=resources://silicium/results/by-task/task_x")
        assert code == 200
        assert json.loads(body)["value"] == 123
