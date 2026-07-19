import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import re
from pathlib import Path
from typing import Any


def _find_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _http_get(url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _http_post(url: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, str]:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _wait_ready(base_url: str, headers: dict[str, str] | None = None) -> None:
    deadline = time.time() + 5.0
    last: Any = None
    while time.time() < deadline:
        try:
            code, body = _http_get(base_url + "/healthz", headers=headers)
            last = (code, body)
            if code == 200:
                return
        except urllib.error.URLError as exc:
            last = f"url_error: {exc}"
        time.sleep(0.05)
    raise AssertionError(f"server not ready: {last}")


def test_mcp_server_reads_resources_and_tools(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")
    (export_dir / "result.func_1_main.json").write_text('{"success":true}', encoding="utf-8")
    (export_dir / "logs.func_1_main.json").write_text('{"stdout":"hi"}', encoding="utf-8")
    (export_dir / "node.node-a.heartbeat.json").write_text('{"node_id":"node-a","roles":["compute"]}', encoding="utf-8")
    (export_dir / "node.node-a.metrics.json").write_text('{"handled":1}', encoding="utf-8")
    (export_dir / "node.node-a.peers.json").write_text('{"node_id":"node-a","count":2}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port), "--enable-tools"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_submits_and_reads_tasks(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port), "--enable-tools"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(base)

        code, body = _http_post(
            base + "/tasks",
            {
                "task_id": "render:tile/1",
                "task": {"kind": "render", "partition_id": "tile_1"},
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
        assert task["on_chain"]["job"] == "job-pubkey"

        code, body = _http_post(
            base + "/tools",
            {"name": "tools.silicium.get_task", "args": {"task_id": "render_tile_1"}},
        )
        assert code == 200
        wrapped = json.loads(body)
        assert json.loads(wrapped["result_json"])["task"]["kind"] == "render"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_submits_role_aware_requests(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port), "--enable-tools"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_token_auth(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    env["SILICIUM_MCP_TOKEN"] = "secret"
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        headers = {"Authorization": "Bearer secret"}
        _wait_ready(base, headers=headers)

        # Without token -> unauthorized.
        code, _ = _http_get(base + "/healthz")
        assert code in (401, 403)

        code, body = _http_get(base + "/.well-known/oauth-authorization-server")
        assert code == 200
        payload = json.loads(body)
        assert payload["oauth_supported"] is False

        _wait_ready(base, headers=headers)
        code, body = _http_get(base + "/healthz", headers=headers)
        assert code == 200
        assert json.loads(body)["ok"] is True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_oauth_discovery_paths(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(base)

        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-authorization-server/mcp",
            "/mcp/.well-known/oauth-authorization-server",
        ):
            code, body = _http_get(base + path)
            assert code == 200
            payload = json.loads(body)
            assert payload["oauth_supported"] is False
            assert payload["path"] == path
            assert payload["mcp_endpoint"] == "/mcp"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_silicium_mcp_serve_no_auth_overrides_token_env(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    env["SILICIUM_MCP_TOKEN"] = "secret"
    proc = subprocess.Popen(
        [sys.executable, "silicium", "mcp", "serve", "--port", str(port), "--no-auth"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(base)
        code, body = _http_get(base + "/healthz")
        assert code == 200
        assert json.loads(body)["ok"] is True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_streamable_http_initialize(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    env["SILICIUM_MCP_TOKEN"] = "secret"
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_metrics_counters(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port), "--enable-tools", "--log-format", "json"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_json_logs_include_http_and_tool_events(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port), "--enable-tools", "--log-format", "json"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(base)
        _http_get(base + "/healthz")
        _http_post(base + "/tools", {"name": "tools.silicium.interrupt_action", "args": {}})
        _http_post(base + "/tools", {"name": "tools.silicium.run_action", "args": {}})
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate(timeout=3)

    events = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

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


def test_mcp_server_snapshots_survive_restart(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    snapshot_dir = tmp_path / "snapshots"
    export_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true,"v":1}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    cmd = [sys.executable, "tools/mcp_server.py", "--port", str(port), "--snapshot-dir", str(snapshot_dir)]

    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(base)
        code, body = _http_get(base + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        assert json.loads(body)["v"] == 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    (export_dir / "status.current.json").unlink()
    proc2 = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_ready(base)
        code, body = _http_get(base + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        assert json.loads(body)["v"] == 1
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc2.kill()


def test_mcp_server_snapshot_retention_caps(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    snapshot_dir = tmp_path / "snapshots"
    export_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")
    (export_dir / "result.task_a.json").write_text('{"payload":"AAAAAAAAAAAAAAAA"}', encoding="utf-8")
    (export_dir / "result.task_b.json").write_text('{"payload":"BBBBBBBBBBBBBBBB"}', encoding="utf-8")
    (export_dir / "result.task_c.json").write_text('{"payload":"CCCCCCCCCCCCCCCC"}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [
            sys.executable,
            "tools/mcp_server.py",
            "--port",
            str(port),
            "--snapshot-dir",
            str(snapshot_dir),
            "--snapshot-max-files",
            "2",
            "--snapshot-max-bytes",
            "40",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_snapshot_export_import(tmp_path: Path) -> None:
    export_dir_a = tmp_path / "mcp-a"
    snapshot_dir_a = tmp_path / "snapshots-a"
    export_dir_a.mkdir(parents=True, exist_ok=True)
    snapshot_dir_a.mkdir(parents=True, exist_ok=True)
    (export_dir_a / "status.current.json").write_text('{"ok":true,"source":"a"}', encoding="utf-8")
    (export_dir_a / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    env_a = os.environ.copy()
    env_a["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir_a)
    port_a = _find_free_port()
    proc_a = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port_a), "--snapshot-dir", str(snapshot_dir_a)],
        env=env_a,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    export_payload: dict[str, Any] = {}
    try:
        base_a = f"http://127.0.0.1:{port_a}"
        _wait_ready(base_a)
        code, _ = _http_get(base_a + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        code, body = _http_get(base_a + "/snapshots/export")
        assert code == 200
        export_payload = json.loads(body)
        assert isinstance(export_payload.get("entries"), list)
    finally:
        proc_a.terminate()
        try:
            proc_a.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc_a.kill()

    export_dir_b = tmp_path / "mcp-b"
    snapshot_dir_b = tmp_path / "snapshots-b"
    export_dir_b.mkdir(parents=True, exist_ok=True)
    snapshot_dir_b.mkdir(parents=True, exist_ok=True)
    (export_dir_b / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")
    env_b = os.environ.copy()
    env_b["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir_b)
    port_b = _find_free_port()
    proc_b = subprocess.Popen(
        [sys.executable, "tools/mcp_server.py", "--port", str(port_b), "--snapshot-dir", str(snapshot_dir_b)],
        env=env_b,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base_b = f"http://127.0.0.1:{port_b}"
        _wait_ready(base_b)
        code, body = _http_post(base_b + "/snapshots/import", export_payload)
        assert code == 200
        assert json.loads(body)["ok"] is True

        code, body = _http_get(base_b + "/resources?uri=resources://silicium/status/current")
        assert code == 200
        assert json.loads(body)["source"] == "a"
    finally:
        proc_b.terminate()
        try:
            proc_b.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc_b.kill()


def test_mcp_server_tool_access_lists(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [
            sys.executable,
            "tools/mcp_server.py",
            "--port",
            str(port),
            "--enable-tools",
            "--tool-allowlist",
            "tools.silicium.get_health,tools.silicium.interrupt_action",
            "--tool-denylist",
            "tools.silicium.interrupt_action",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_server_resource_access_lists(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")
    (export_dir / "result.task_x.json").write_text('{"value":123}', encoding="utf-8")

    port = _find_free_port()
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    proc = subprocess.Popen(
        [
            sys.executable,
            "tools/mcp_server.py",
            "--port",
            str(port),
            "--resource-allowlist",
            "resources://silicium/results/by-task/*,resources://silicium/status/current",
            "--resource-denylist",
            "resources://silicium/status/current",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
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
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
