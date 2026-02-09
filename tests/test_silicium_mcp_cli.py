import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SILICIUM = REPO_ROOT / "silicium"


def _find_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_health(url: str, token: str) -> None:
    deadline = time.time() + 5.0
    last = None
    while time.time() < deadline:
        req = urllib.request.Request(url + "/healthz", headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    return
                last = resp.status
        except Exception as exc:
            last = str(exc)
        time.sleep(0.05)
    raise AssertionError(f"server not ready: {last}")


def test_silicium_mcp_print_config_json(tmp_path: Path) -> None:
    port = _find_free_port()
    export_dir = tmp_path / "export"
    token_file = tmp_path / "token"
    cfg = {
        "mcp": {
            "bind": "127.0.0.1",
            "port": port,
            "export_dir": str(export_dir),
            "token_file": str(token_file),
            "enable_tools": False,
        }
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    env = os.environ.copy()
    env["SILICIUM_CONFIG"] = str(cfg_path)
    result = subprocess.run(
        [sys.executable, str(SILICIUM), "mcp", "print-config", "--format", "json"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["base_url"] == f"http://127.0.0.1:{port}"
    assert payload["export_dir"] == str(export_dir)
    assert token_file.exists()


def test_silicium_mcp_serve_starts_server(tmp_path: Path) -> None:
    port = _find_free_port()
    export_dir = tmp_path / "export"
    token_file = tmp_path / "token"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "mcp": {
                    "bind": "127.0.0.1",
                    "port": port,
                    "export_dir": str(export_dir),
                    "token_file": str(token_file),
                }
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["SILICIUM_CONFIG"] = str(cfg_path)

    proc = subprocess.Popen(
        [sys.executable, str(SILICIUM), "mcp", "serve"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 5.0
        while not token_file.exists() and time.time() < deadline:
            time.sleep(0.05)
        token = token_file.read_text(encoding="utf-8").strip()
        _wait_health(f"http://127.0.0.1:{port}", token)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
