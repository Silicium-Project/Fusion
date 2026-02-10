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
    last = None
    while time.time() < deadline:
        code, body = _http_get(base_url + "/healthz", headers=headers)
        last = (code, body)
        if code == 200:
            return
        time.sleep(0.05)
    raise AssertionError(f"server not ready: {last}")


def test_mcp_server_reads_resources_and_tools(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "status.current.json").write_text('{"ok":true}', encoding="utf-8")
    (export_dir / "reports.recent.json").write_text('{"tasks":[]}', encoding="utf-8")
    (export_dir / "result.func_1_main.json").write_text('{"success":true}', encoding="utf-8")
    (export_dir / "logs.func_1_main.json").write_text('{"stdout":"hi"}', encoding="utf-8")

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
        # Without token -> unauthorized.
        code, _ = _http_get(base + "/healthz")
        assert code in (401, 403)

        headers = {"Authorization": "Bearer secret"}
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

        code, body = _http_get(base + "/metrics")
        assert code == 200

        m = re.search(r'mcp_http_requests_total\{method="GET",path="/healthz",status="200"\}\s+(\d+)', body)
        assert m is not None
        assert int(m.group(1)) >= 2

        m = re.search(r'mcp_tool_calls_total\{tool="tools\.silicium\.interrupt_action"\}\s+(\d+)', body)
        assert m is not None
        assert int(m.group(1)) >= 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


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
