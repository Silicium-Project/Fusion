"""MCP server HTTP API: resources, tools, task and request queues, and the
streamable-HTTP MCP transport (``/mcp``). Each test runs a real server process.
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


def test_mcp_server_reads_resources_and_tools(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(
        export_dir,
        {
            **DEFAULT_EXPORTS,
            "result.func_1_main.json": '{"success":true}',
            "logs.func_1_main.json": '{"stdout":"hi"}',
            "node.node-a.heartbeat.json": '{"node_id":"node-a","roles":["compute"]}',
            "node.node-a.metrics.json": '{"handled":1}',
            "node.node-a.peers.json": '{"node_id":"node-a","count":2}',
        },
    )

    port = _find_free_port()
    with _running_server(_mcp_server_cmd(port, "--enable-tools"), _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)

        code, body = _http_get(base + "/resources/list")
        assert code == 200
        payload = json.loads(body)
        assert "resources" in payload

        code, body = _http_get(base + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        assert json.loads(body)["ok"] is True

        code, body = _http_get(base + "/resources?uri=resources://silicium/nodes/heartbeat/node-a")
        assert code == 200
        assert json.loads(body)["node_id"] == "node-a"

        code, body = _http_get(base + "/resources?uri=resources://silicium/nodes/peers/node-a")
        assert code == 200
        assert json.loads(body)["count"] == 2

        code, body = _http_post(
            base + "/tools",
            {"name": "tools.silicium.run_action", "args": {"action": "read_task_result", "task_id": "func_1_main"}},
        )
        assert code == 200
        wrapped = json.loads(body)
        assert wrapped["ok"] is True
        assert json.loads(wrapped["result_json"])["success"] is True

        code, _ = _http_post(base + "/tools", {"name": "tools.silicium.interrupt_action", "args": {}})
        assert code == 200
        assert (export_dir / "control.request.json").exists()


def test_mcp_server_submits_and_reads_tasks(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    with _running_server(_mcp_server_cmd(port, "--enable-tools"), _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)

        code, body = _http_post(
            base + "/tasks",
            {
                "task_id": "render:tile/1",
                "task": {"kind": "render", "partition_id": "tile_1"},
                "excluded_peer_ids": ["render-worker"],
                "on_chain": {"job": "job-pubkey", "fragment_index": 1, "worker_token": "token-account"},
            },
        )
        assert code == 202
        accepted = json.loads(body)
        assert accepted["ok"] is True
        assert accepted["task_id"] == "render_tile_1"
        assert (export_dir / "tasks.queue.ndjson").exists()

        code, body = _http_get(base + "/tasks/render_tile_1")
        assert code == 200
        task = json.loads(body)
        assert task["status"] == "queued"
        assert task["task"]["partition_id"] == "tile_1"
        assert task["required_roles"] == ["compute"]
        assert task["excluded_peer_ids"] == ["render-worker"]
        assert task["on_chain"]["job"] == "job-pubkey"

        code, body = _http_post(
            base + "/tools",
            {"name": "tools.silicium.get_task", "args": {"task_id": "render_tile_1"}},
        )
        assert code == 200
        wrapped = json.loads(body)
        assert json.loads(wrapped["result_json"])["task"]["kind"] == "render"

        code, body = _http_get(base + "/tasks?limit=10")
        assert code == 200
        listed = json.loads(body)
        assert listed["tasks"][0]["task_id"] == "render_tile_1"

        code, body = _http_post(base + "/tasks/render_tile_1/cancel", {})
        assert code == 200
        assert json.loads(body)["task"]["status"] == "cancelled"
        code, body = _http_get(base + "/tasks/render_tile_1")
        assert code == 200
        assert json.loads(body)["status"] == "cancelled"


def test_mcp_server_submits_role_aware_requests(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    with _running_server(_mcp_server_cmd(port, "--enable-tools"), _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)

        code, body = _http_post(
            base + "/requests",
            {
                "request_id": "audit/job-1/frag-0",
                "kind": "audit",
                "priority": "urgent",
                "target_roles": ["audit", "verify"],
                "job_id": "job-1",
                "fragment_id": "job-1:0",
                "p2p_ref": {"protocol": "ipfs", "cid": "bafybeiaudit", "hash": "sha256:abc"},
                "request": {"sample": "full"},
                "on_chain": {"job": "job-pubkey", "fragment": "fragment-pubkey", "escrow": "escrow-pubkey", "worker_token": "token-account"},
            },
        )
        assert code == 202
        accepted = json.loads(body)
        assert accepted["ok"] is True
        assert accepted["request_id"] == "audit_job-1_frag-0"
        assert accepted["target_roles"] == ["audit", "verify"]
        assert (export_dir / "requests.queue.ndjson").exists()
        assert (export_dir / "requests.urgent.ndjson").exists()
        assert (export_dir / "requests.audit.queue.ndjson").exists()
        assert (export_dir / "requests.verify.queue.ndjson").exists()

        code, body = _http_get(base + "/requests/audit_job-1_frag-0")
        assert code == 200
        request = json.loads(body)
        assert request["kind"] == "audit"
        assert request["priority_rank"] == 100
        assert request["p2p_ref"]["content_id"] == "bafybeiaudit"
        assert request["on_chain"]["fragment"] == "fragment-pubkey"

        code, body = _http_post(
            base + "/tools",
            {"name": "tools.silicium.get_request", "args": {"request_id": "audit_job-1_frag-0"}},
        )
        assert code == 200
        wrapped = json.loads(body)
        assert json.loads(wrapped["result_json"])["target_roles"] == ["audit", "verify"]


def test_mcp_streamable_http_initialize(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    with _running_server(_mcp_server_cmd(port), _server_env(export_dir, token="secret")):
        base = _base_url(port)
        headers = {"Authorization": "Bearer secret"}
        _wait_ready(base, headers=headers)

        code, body = _http_post(
            base + "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "pytest", "version": "0"}},
            },
            headers=headers,
        )
        assert code == 200
        payload = json.loads(body)
        assert payload["jsonrpc"] == "2.0"
        assert payload["id"] == 1
        assert payload["result"]["serverInfo"]["name"] == "silicium-mcp"

        code, body = _http_post(base + "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, headers=headers)
        assert code == 200
        payload = json.loads(body)
        assert payload["id"] == 2
        assert isinstance(payload["result"]["tools"], list)
        assert any(t.get("name") == "tools.silicium.get_health" for t in payload["result"]["tools"])
