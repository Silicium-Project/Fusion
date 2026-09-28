"""Legacy runtime helpers: attach P2P content blobs to task envelopes and run a local resource node.

Part of the Python runtime that crates/ replaces; see docs/architecture/rust-migration.md.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# This module lives in Network/networked, so the Network checkout is its
# immediate parent. Keeping this path anchored here is important for the
# embedded emitter: it must launch Network/silicium, not a repository-level
# path that may not exist.
NETWORK_ROOT = Path(__file__).resolve().parents[1]
MAX_INLINE_CONTENT_BLOB_TOTAL_BYTES = 16 * 1024 * 1024


class RpcTaskEventListener:
    """Best-effort task wake-up channel for a network workload.

    The filesystem journal/result remains the source of truth.  This listener
    merely replaces needless sleep/poll cycles while a task is remote.  It is
    optional so an older scheduler or a standalone node keeps the exact
    historical behaviour.
    """

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = str(endpoint or os.environ.get("SILICIUM_RPC_EVENTS_CONNECT", "")).strip()
        self._context: Any = None
        self._socket: Any = None
        if not self.endpoint:
            return
        try:
            import zmq

            self._context = zmq.Context()
            self._socket = self._context.socket(zmq.SUB)
            self._socket.setsockopt(zmq.LINGER, 0)
            self._socket.setsockopt(zmq.SUBSCRIBE, b"task.")
            self._socket.connect(self.endpoint)
        except Exception:
            self.close()

    @property
    def enabled(self) -> bool:
        return self._socket is not None

    def wait(self, timeout_s: float = 0.1) -> bool:
        """Wait for a task transition, returning false on timeout/unavailable."""
        if self._socket is None:
            time.sleep(max(0.0, timeout_s))
            return False
        try:
            if not self._socket.poll(max(0, int(timeout_s * 1000))):
                return False
            self._socket.recv_multipart(flags=0)
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close(0)
            except Exception:
                pass
        self._socket = None
        if self._context is not None:
            try:
                self._context.term()
            except Exception:
                pass
        self._context = None


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


def find_openssl() -> "Path | None":
    """Locate openssl binary, needed by some native tools on Windows."""
    import shutil

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
    """Return a copy of the environment with OpenSSL prepended to PATH when found.

    The node process uses the ``cryptography`` library for Ed25519 (no openssl
    subprocess required), but other native tooling bundled with a worker binary
    may still rely on an openssl binary being on PATH.  Injecting it here keeps
    that transparent to callers.
    """
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


def attach_network_content_blobs(export_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach bounded, hash-verified Silicium inputs to a dispatched envelope.

    P2P remains the primary content transport. These blobs make task delivery
    resilient when a NATed origin cannot accept the worker's immediate fetch.
    """
    content_ids: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            protocol = str(value.get("protocol", "")).lower()
            content_id = str(value.get("content_id", "")).strip().lower()
            if protocol == "silicium" and len(content_id) == 64 and content_id not in content_ids:
                content_ids.append(content_id)
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(payload)
    blobs: list[dict[str, str]] = []
    total_bytes = 0
    for content_id in content_ids:
        path = export_dir / "p2p" / content_id
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if total_bytes + len(data) > MAX_INLINE_CONTENT_BLOB_TOTAL_BYTES or sha256_bytes(data) != content_id:
            continue
        blobs.append({"content_id": content_id, "data_b64": base64.b64encode(data).decode("ascii")})
        total_bytes += len(data)
    dispatched = dict(payload)
    if blobs:
        dispatched["content_blobs"] = blobs
    return dispatched


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


def _identity_headers(export_dir: Path, node_id: str, method: str, path: str, body: bytes) -> dict[str, str]:
    """Build production peer-auth headers from the emitter's local identity."""
    key_candidates = [
        export_dir.parent / "state" / "peer_identity_ed25519.pem",
        export_dir.parent / "_emitter_state" / "peer_identity_ed25519.pem",
    ]
    private_path = next((item for item in key_candidates if item.exists()), None)
    if private_path is None:
        return {}
    from cryptography.hazmat.primitives import serialization
    public_path = private_path.with_suffix(".pub.pem")
    if not public_path.exists():
        return {}
    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    public_pem = public_path.read_bytes()
    identity_id = sha256_bytes(public_pem)[:32]
    public_b64 = base64.b64encode(public_pem).decode("ascii")
    timestamp = str(int(time.time()))
    body_hash = sha256_bytes(body)
    signing_payload = "\n".join([method.upper(), path, timestamp, body_hash, node_id, identity_id]).encode("utf-8")
    return {
        "X-Silicium-Node-Id": node_id,
        "X-Silicium-Identity-Id": identity_id,
        "X-Silicium-Public-Key": public_b64,
        "X-Silicium-Timestamp": timestamp,
        "X-Silicium-Body-Hash": body_hash,
        "X-Silicium-Signature": private_key.sign(signing_payload).hex(),
    }


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
    # A worker can advertise a private/NAT address in its result reference.
    # Prefer every known endpoint and let the scheduler/relay copy win when
    # the result was already returned with an attached content blob.
    base_urls: list[str] = []
    for candidate in (
        str(ref.get("peer_url", "")).rstrip("/"),
        peer_url(export_dir, emitter_node_id, peer_id),
        str(os.environ.get("SILICIUM_ORCHESTRATOR_URL", "")).rstrip("/"),
        str(os.environ.get("SILICIUM_PEER_ADVERTISE_URL", "")).rstrip("/"),
        *[item.strip().rstrip("/") for item in str(os.environ.get("SILICIUM_SEED_PEERS", "")).split(",")],
    ):
        if candidate and candidate not in base_urls:
            base_urls.append(candidate)
    if not base_urls:
        raise ValueError(f"unknown_peer_for_content:{peer_id}")
    headers = {"Authorization": f"Bearer {mesh_key}"} if mesh_key else {}
    # Production peers disable bearer-only development auth. Sign GETs with
    # the emitter identity when the bundled state key is available.
    try:
        headers.update(_identity_headers(export_dir, emitter_node_id, "GET", "/p2p/" + urllib.request.quote(content_id, safe=""), b""))
    except Exception:
        pass
    last_error: Exception | None = None
    path = "/p2p/" + urllib.request.quote(content_id, safe="")
    for base_url in base_urls:
        # Keep a failed NAT/private endpoint from blocking the entire job for
        # 30 seconds. A returned result is retried briefly, then other peers
        # and the central scheduler are attempted.
        for attempt in range(2):
            try:
                request = urllib.request.Request(base_url + path, headers=headers)
                with urllib.request.urlopen(request, timeout=6) as response:
                    data = response.read()
                if sha256_bytes(data) != content_id:
                    raise ValueError(f"content_hash_mismatch:{content_id}")
                return data
            except Exception as error:  # noqa: BLE001 - continue to next transport endpoint
                last_error = error
                if attempt == 0:
                    time.sleep(0.15)
    raise urllib.error.URLError(f"content_fetch_failed:{content_id}:{last_error}")


def dispatch_task_to_scheduler(
    task: dict[str, Any],
    seed_peers: str,
    mesh_key: str,
    *,
    export_dir: Path | None = None,
    node_id: str = "",
) -> dict[str, Any]:
    """Submit a workload envelope to a scheduler that pull-based workers poll."""
    payload = json.dumps(task, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if mesh_key:
        headers["Authorization"] = f"Bearer {mesh_key}"
    attempts: list[dict[str, Any]] = []
    for raw_seed in str(seed_peers or "").split(","):
        base_url = raw_seed.strip().rstrip("/")
        if not base_url:
            continue
        url = base_url + "/tasks/dispatch"
        try:
            request_headers = dict(headers)
            if export_dir is not None and node_id:
                request_headers.update(_identity_headers(export_dir, node_id, "POST", "/tasks/dispatch", payload))
            request = urllib.request.Request(url, data=payload, method="POST", headers=request_headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                status = int(response.status)
                attempts.append({"target": base_url, "http_status": status, "ok": status in {200, 202}})
                if status in {200, 202}:
                    return {"status": "dispatched", "target": base_url, "attempts": attempts}
        except urllib.error.HTTPError as error:
            attempts.append({"target": base_url, "http_status": int(error.code), "error": str(error.reason or error), "ok": False})
        except Exception as error:
            attempts.append({"target": base_url, "error": f"{type(error).__name__}:{error}", "ok": False})
    return {"status": "dispatch_failed", "attempts": attempts}


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
        self._public_url = ""

    @property
    def public_url(self) -> str:
        if self._public_url:
            return self._public_url
        heartbeat = read_json(self.export_dir / f"node.{self.node_id}.heartbeat.json", {})
        if isinstance(heartbeat, dict):
            advertised = str(heartbeat.get("peer_public_base_url", "")).strip()
            if advertised:
                self._public_url = advertised.rstrip("/")
                return self._public_url
        host = self.advertise_host or "127.0.0.1"
        port = self.advertise_port or self.port
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self.process is not None:
            return
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
            "--identity-dev-mesh-auth",
        ]
        heartbeat_path = self.export_dir / f"node.{self.node_id}.heartbeat.json"
        if heartbeat_path.exists():
            heartbeat_path.unlink()
        self.process = subprocess.Popen(
            command,
            cwd=str(NETWORK_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=node_environment(),
        )
        # Bootstrap refreshes peer and reputation data before the node writes its
        # first heartbeat.  On a cold network this routinely exceeds a few
        # seconds, so do not kill a healthy emitter before it becomes ready.
        startup_timeout_s = 30.0
        deadline = time.monotonic() + startup_timeout_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate(timeout=2)
                self.process = None
                detail = (stderr or stdout or "").strip()[-4000:]
                raise RuntimeError(f"network_emitter_start_failed:{detail or 'process_exited'}")
            heartbeat = read_json(heartbeat_path, {})
            if isinstance(heartbeat, dict):
                advertised = str(heartbeat.get("peer_public_base_url", "")).strip()
                if advertised:
                    self._public_url = advertised.rstrip("/")
                    return
            time.sleep(0.1)

        if self.process.poll() is None:
            self.process.terminate()
            try:
                stdout, stderr = self.process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                stdout, stderr = self.process.communicate(timeout=3)
            self.process = None
            detail = (stderr or stdout or "").strip()[-4000:]
            raise RuntimeError(
                f"network_emitter_start_timeout:waited_s={startup_timeout_s}:"
                f"{detail or heartbeat_path}"
            )

    def wait_for_heartbeat(self, timeout_s: float = 30.0) -> bool:
        """Wait until the node's HTTP /healthz endpoint responds OK.

        Complements the file-based startup poll in ``start()`` by confirming
        that the peer HTTP server is actually accepting connections before
        callers dispatch tasks.  Returns True when healthy, False on timeout.
        """
        base_url = self.public_url
        deadline = time.monotonic() + max(0.0, timeout_s)
        mesh_key = self.mesh_key
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                return False
            try:
                headers = {"Authorization": f"Bearer {mesh_key}"} if mesh_key else {}
                req = urllib.request.Request(base_url + "/healthz", headers=headers)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if int(resp.status) in {200, 204}:
                        return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

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
