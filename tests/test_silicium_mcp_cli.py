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
    deadline = time.time() + 10.0
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


def _fake_solana_bridge(path: Path) -> Path:
    path.write_text(
        """
let data = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => data += chunk);
process.stdin.on("end", () => {
  const request = JSON.parse(data || "{}");
  if (request.op === "create_job") {
    process.stdout.write(JSON.stringify({
      ok: true,
      op: request.op,
      signatures: ["sig-create-job"],
      accounts: { job: "job-pubkey", escrowAuth: "escrow-auth-pubkey" }
    }) + "\\n");
    return;
  }
  process.stdout.write(JSON.stringify({
    ok: true,
    op: request.op,
    signatures: ["sig-" + request.op],
    accounts: { worker: "worker-pubkey" }
  }) + "\\n");
});
""".strip(),
        encoding="utf-8",
    )
    return path


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


def test_silicium_node_submit_and_get_task(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"mcp": {"export_dir": str(export_dir), "enable_tools": True}}), encoding="utf-8")
    env = os.environ.copy()
    env["SILICIUM_CONFIG"] = str(cfg_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SILICIUM),
            "node",
            "submit-task",
            "--task-id",
            "cli_1",
            "--task",
            '{"kind":"storage","path":"object.bin"}',
            "--roles",
            "storage",
            "--p2p-ref",
            '{"protocol":"file","content_id":"/tmp/object.bin"}',
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    accepted = json.loads(result.stdout)
    assert accepted["task_id"] == "cli_1"

    result = subprocess.run(
        [sys.executable, str(SILICIUM), "node", "get-task", "cli_1"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    task = json.loads(result.stdout)
    assert task["required_roles"] == ["storage"]


def test_silicium_node_create_job_and_enqueue_task(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"mcp": {"export_dir": str(export_dir), "enable_tools": True}}), encoding="utf-8")
    bridge = _fake_solana_bridge(tmp_path / "fake_bridge.cjs")
    env = os.environ.copy()
    env["SILICIUM_CONFIG"] = str(cfg_path)
    env["SILICIUM_SOLANA_BRIDGE"] = str(bridge)

    result = subprocess.run(
        [
            sys.executable,
            str(SILICIUM),
            "node",
            "create-job",
            "--mint",
            "11111111111111111111111111111111",
            "--client-token",
            "11111111111111111111111111111111",
            "--escrow-keypair-path",
            str(tmp_path / "escrow.json"),
            "--job-id",
            "42",
            "--expected-fragments",
            "1",
            "--reward-per-fragment",
            "10",
            "--deadline-unix",
            "1893456000",
            "--task-id",
            "job_42",
            "--task",
            '{"kind":"compute"}',
            "--worker-token",
            "11111111111111111111111111111111",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["job"]["accounts"]["job"] == "job-pubkey"
    assert payload["task"]["task_id"] == "job_42"

    task = json.loads((export_dir / "tasks" / "job_42.json").read_text(encoding="utf-8"))
    assert task["on_chain"]["job"] == "job-pubkey"


def test_silicium_node_get_heartbeat_and_metrics(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "node.node-a.heartbeat.json").write_text('{"node_id":"node-a"}', encoding="utf-8")
    (export_dir / "node.node-a.metrics.json").write_text('{"handled":2}', encoding="utf-8")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"mcp": {"export_dir": str(export_dir)}}), encoding="utf-8")
    env = os.environ.copy()
    env["SILICIUM_CONFIG"] = str(cfg_path)

    heartbeat = subprocess.run(
        [sys.executable, str(SILICIUM), "node", "get-heartbeat", "--node-id", "node-a"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert heartbeat.returncode == 0, heartbeat.stderr
    assert json.loads(heartbeat.stdout)["node_id"] == "node-a"

    metrics = subprocess.run(
        [sys.executable, str(SILICIUM), "node", "get-metrics", "--node-id", "node-a"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert metrics.returncode == 0, metrics.stderr
    assert json.loads(metrics.stdout)["handled"] == 2


def test_silicium_node_get_peers(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "node.node-a.peers.json").write_text(
        '{"node_id":"node-a","count":2,"peers":[{"node_id":"node-a"},{"node_id":"node-b"}]}',
        encoding="utf-8",
    )
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"mcp": {"export_dir": str(export_dir)}}), encoding="utf-8")
    env = os.environ.copy()
    env["SILICIUM_CONFIG"] = str(cfg_path)

    peers = subprocess.run(
        [sys.executable, str(SILICIUM), "node", "get-peers", "--node-id", "node-a"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert peers.returncode == 0, peers.stderr
    assert json.loads(peers.stdout)["count"] == 2
