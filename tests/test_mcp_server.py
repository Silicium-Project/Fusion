import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


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

