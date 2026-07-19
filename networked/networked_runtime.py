from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


NETWORK_ROOT = Path(__file__).resolve().parents[2]


def sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def find_openssl() -> Path | None:
    found = shutil.which("openssl")
    if found:
        return Path(found)
    if os.name != "nt":
        return None
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for candidate in [
        Path(program_files) / "OpenSSL-Win64" / "bin" / "openssl.exe",
        Path(program_files) / "OpenSSL-Win32" / "bin" / "openssl.exe",
        Path(program_files_x86) / "OpenSSL-Win32" / "bin" / "openssl.exe",
        Path(program_files) / "Git" / "usr" / "bin" / "openssl.exe",
        Path(program_files_x86) / "Git" / "usr" / "bin" / "openssl.exe",
    ]:
        if candidate.exists():
            return candidate
    return None


def node_environment() -> dict[str, str]:
    env = os.environ.copy()
    openssl = find_openssl()
    if openssl is not None:
        openssl_dir = str(openssl.parent)
        parts = [part for part in env.get("PATH", "").split(os.pathsep) if part]
        if openssl_dir not in parts:
            env["PATH"] = openssl_dir + os.pathsep + env.get("PATH", "")
    return env


def store_network_content(export_dir: Path, data: bytes, owner_node_id: str) -> dict[str, Any]:
    digest = sha256_bytes(data)
    target = export_dir / "p2p" / digest
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(data)
    return {
        "protocol": "silicium",
        "content_id": digest,
        "hash": "sha256:" + digest,
        "peer_id": owner_node_id,
    }


def store_network_file(export_dir: Path, path: Path, owner_node_id: str) -> dict[str, Any]:
    return store_network_content(export_dir, path.read_bytes(), owner_node_id)


def best_shared_ref(ref: dict[str, Any]) -> dict[str, Any]:
    shared = ref.get("shared_ref") if isinstance(ref, dict) else None
    if isinstance(shared, dict) and shared.get("protocol") == "silicium":
        return shared
    return ref


def _peer_snapshot(export_dir: Path, emitter_node_id: str) -> dict[str, Any]:
    return read_json(export_dir / f"node.{emitter_node_id}.peers.json", {"peers": []}) or {"peers": []}


def peer_url(export_dir: Path, emitter_node_id: str, peer_id: str) -> str:
    for peer in _peer_snapshot(export_dir, emitter_node_id).get("peers", []):
        if isinstance(peer, dict) and str(peer.get("node_id", "")) == peer_id:
            return str(peer.get("http_base_url", "")).rstrip("/")
    return ""


def fetch_network_content(export_dir: Path, emitter_node_id: str, ref: dict[str, Any], mesh_key: str) -> bytes:
    ref = best_shared_ref(ref)
    protocol = str(ref.get("protocol", "")).lower()
    content_id = str(ref.get("content_id", "")).strip()
    if protocol == "file":
        return Path(content_id).read_bytes()
    if protocol != "silicium":
        raise ValueError(f"unsupported_network_ref_protocol:{protocol}")
    local = export_dir / "p2p" / content_id
    if local.exists():
        return local.read_bytes()
    peer_id = str(ref.get("peer_id", "")).strip()
    base_url = str(ref.get("peer_url", "")).rstrip("/") or peer_url(export_dir, emitter_node_id, peer_id)
    if not base_url:
        raise ValueError(f"unknown_peer_for_content:{peer_id}")
    headers = {"Authorization": f"Bearer {mesh_key}"} if mesh_key else {}
    request = urllib.request.Request(base_url + "/p2p/" + urllib.request.quote(content_id, safe=""), headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def wait_for_result(export_dir: Path, task_id: str, timeout_s: float) -> dict[str, Any]:
    result_path = export_dir / f"result.{task_id}.json"
    dead_letters_path = export_dir / "dead_letters.ndjson"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() <= deadline:
        payload = read_json(result_path)
        if isinstance(payload, dict):
            return payload
        if dead_letters_path.exists():
            try:
                for line in dead_letters_path.read_text(encoding="utf-8").splitlines():
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict) and str(item.get("task_id", "")) == task_id:
                        raise RuntimeError(
                            "network task dead-lettered: "
                            + str(item.get("last_error", "unknown_error"))
                            + f" ({task_id})"
                        )
            except RuntimeError:
                raise
        time.sleep(0.25)
    raise TimeoutError(f"missing network result after {timeout_s:.1f}s: {result_path}")


class LocalNetworkEmitter:
    def __init__(
        self,
        *,
        export_dir: Path,
        state_dir: Path,
        node_id: str,
        bind: str,
        port: int,
        advertise_host: str,
        advertise_port: int,
        seed_peers: str,
        mesh_key: str,
        idle_ms: int = 250,
    ) -> None:
        self.export_dir = export_dir
        self.state_dir = state_dir
        self.node_id = node_id
        self.bind = bind
        self.port = port
        self.advertise_host = advertise_host
        self.advertise_port = advertise_port
        self.seed_peers = seed_peers
        self.mesh_key = mesh_key
        self.idle_ms = idle_ms
        self.process: subprocess.Popen[str] | None = None

    @property
    def public_url(self) -> str:
        host = self.advertise_host or "127.0.0.1"
        port = self.advertise_port or self.port
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self.process is not None:
            return
        if find_openssl() is None:
            raise RuntimeError("openssl_not_found_for_networked_node")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(NETWORK_ROOT / "silicium"),
            "node",
            "start",
            "--roles",
            "resource",
            "--node-id",
            self.node_id,
            "--export-dir",
            str(self.export_dir),
            "--state-dir",
            str(self.state_dir),
            "--idle-ms",
            str(self.idle_ms),
            "--peer-http-bind",
            self.bind,
            "--peer-http-port",
            str(self.port),
            "--peer-advertise-host",
            self.advertise_host,
            "--peer-advertise-port",
            str(self.advertise_port or self.port),
            "--seed-peers",
            self.seed_peers,
            "--mesh-key",
            self.mesh_key,
            "--remote-dispatch-enable",
            "--remote-dispatch-limit",
            "3",
        ]
        self.process = subprocess.Popen(
            command,
            cwd=str(NETWORK_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=node_environment(),
        )

    def stop(self) -> dict[str, Any]:
        if self.process is None:
            return {"started": False}
        proc = self.process
        self.process = None
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
        stopped_by_demo = proc.returncode is not None and proc.returncode != 0
        return {
            "started": True,
            "stopped_by_demo": stopped_by_demo,
            "ok": True,
            "returncode": proc.returncode,
            "stdout_tail": (stdout or "")[-2000:],
            "stderr_tail": (stderr or "")[-4000:],
            "public_url": self.public_url,
        }
