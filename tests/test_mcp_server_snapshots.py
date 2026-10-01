"""MCP server resource snapshots (``--snapshot-dir``): persistence across a
restart, retention caps, and export from one server / import into another.
"""

import json
from pathlib import Path
from typing import Any

from tests.mcp_server_support import (
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


def test_mcp_server_snapshots_survive_restart(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    snapshot_dir = tmp_path / "snapshots"
    _write_exports(
        export_dir,
        {"status.current.json": '{"ok":true,"v":1}', "reports.recent.json": '{"tasks":[]}'},
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    port = _find_free_port()
    env = _server_env(export_dir)
    cmd = _mcp_server_cmd(port, "--snapshot-dir", str(snapshot_dir))

    with _running_server(cmd, env):
        base = _base_url(port)
        _wait_ready(base)
        code, body = _http_get(base + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        assert json.loads(body)["v"] == 1

    (export_dir / "status.current.json").unlink()
    with _running_server(cmd, env):
        base = _base_url(port)
        _wait_ready(base)
        code, body = _http_get(base + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        assert json.loads(body)["v"] == 1


def test_mcp_server_snapshot_retention_caps(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    snapshot_dir = tmp_path / "snapshots"
    _write_exports(
        export_dir,
        {
            "status.current.json": '{"ok":true}',
            "reports.recent.json": '{"tasks":[]}',
            "result.task_a.json": '{"payload":"AAAAAAAAAAAAAAAA"}',
            "result.task_b.json": '{"payload":"BBBBBBBBBBBBBBBB"}',
            "result.task_c.json": '{"payload":"CCCCCCCCCCCCCCCC"}',
        },
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    port = _find_free_port()
    cmd = _mcp_server_cmd(
        port,
        "--snapshot-dir",
        str(snapshot_dir),
        "--snapshot-max-files",
        "2",
        "--snapshot-max-bytes",
        "40",
    )
    with _running_server(cmd, _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)
        _http_get(base + "/resources?uri=resources://silicium/results/by-task/task_a")
        _http_get(base + "/resources?uri=resources://silicium/results/by-task/task_b")
        _http_get(base + "/resources?uri=resources://silicium/results/by-task/task_c")
        code, body = _http_get(base + "/snapshots/list")
        assert code == 200
        payload = json.loads(body)
        entries = payload.get("entries", [])
        assert isinstance(entries, list)
        assert len(entries) <= 2
        total = sum(int(e.get("size", 0)) for e in entries if isinstance(e, dict))
        assert total <= 40


def _export_snapshots_from_server_a(tmp_path: Path) -> dict[str, Any]:
    export_dir_a = tmp_path / "mcp-a"
    snapshot_dir_a = tmp_path / "snapshots-a"
    _write_exports(
        export_dir_a,
        {"status.current.json": '{"ok":true,"source":"a"}', "reports.recent.json": '{"tasks":[]}'},
    )
    snapshot_dir_a.mkdir(parents=True, exist_ok=True)

    port_a = _find_free_port()
    cmd = _mcp_server_cmd(port_a, "--snapshot-dir", str(snapshot_dir_a))
    with _running_server(cmd, _server_env(export_dir_a)):
        base_a = _base_url(port_a)
        _wait_ready(base_a)
        code, _ = _http_get(base_a + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        code, body = _http_get(base_a + "/snapshots/export")
        assert code == 200
        export_payload = json.loads(body)
        assert isinstance(export_payload.get("entries"), list)
    return export_payload


def test_mcp_server_snapshot_export_import(tmp_path: Path) -> None:
    export_payload = _export_snapshots_from_server_a(tmp_path)

    # Server B has no status.current.json: it can only come from the import.
    export_dir_b = tmp_path / "mcp-b"
    snapshot_dir_b = tmp_path / "snapshots-b"
    _write_exports(export_dir_b, {"reports.recent.json": '{"tasks":[]}'})
    snapshot_dir_b.mkdir(parents=True, exist_ok=True)

    port_b = _find_free_port()
    cmd = _mcp_server_cmd(port_b, "--snapshot-dir", str(snapshot_dir_b))
    with _running_server(cmd, _server_env(export_dir_b)):
        base_b = _base_url(port_b)
        _wait_ready(base_b)
        code, body = _http_post(base_b + "/snapshots/import", export_payload)
        assert code == 200
        assert json.loads(body)["ok"] is True

        code, body = _http_get(base_b + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        assert json.loads(body)["source"] == "a"
