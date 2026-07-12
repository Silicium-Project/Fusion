#!/usr/bin/env python3
"""
Role-aware Silicium network node daemon.

This daemon consumes the MCP/HTTP ingress queues produced by tools/mcp_server.py.
It is intentionally service-shaped: a node has roles, prioritizes urgent
post-job requests, exchanges larger payloads through P2P/content references, and
publishes stable result/log resources back into the export directory.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.server
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse


DEFAULT_EXPORT_DIR = Path(".silicium/mcp/export")
RAYTRACER_COMPUTE_WORKLOAD = "calcul/rendering/raytracer"
RAYTRACER_VERIFY_WORKLOAD = "verification/rendering/raytracer"
RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD = "calcul/rendering/raytracer-fragment"
RAYTRACER_FRAGMENT_VERIFY_WORKLOAD = "verification/rendering/raytracer-fragment"
NETWORK_ROLES = frozenset({"compute", "verify", "storage", "audit", "resource"})
REQUEST_ROLES = frozenset({"audit", "resource", "verify", "storage", "compute"})
WORLD_DEFAULT_GOSSIP_PORT = 46000
WORLD_DEFAULT_PEER_HTTP_PORT = 46001
WORLD_DEFAULT_PEER_SYNC_INTERVAL_S = 10
WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S = 15


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.:-" else "_" for ch in value.strip())
    return cleaned or uuid.uuid4().hex


def find_openssl_command() -> str:
    configured = os.environ.get("SILICIUM_OPENSSL_BIN", "").strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return str(configured_path)
    found = shutil.which("openssl")
    if found:
        return found
    if os.name != "nt":
        return "openssl"
    network_root = Path(__file__).resolve().parents[1]
    runtime_root = network_root.parent
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for candidate in [
        runtime_root / "tools" / "openssl" / "bin" / "openssl.exe",
        runtime_root / "tools" / "openssl" / "openssl.exe",
        network_root / "tools" / "openssl" / "bin" / "openssl.exe",
        network_root / "tools" / "openssl" / "openssl.exe",
        Path(program_files) / "OpenSSL-Win64" / "bin" / "openssl.exe",
        Path(program_files) / "OpenSSL-Win32" / "bin" / "openssl.exe",
        Path(program_files_x86) / "OpenSSL-Win32" / "bin" / "openssl.exe",
        Path(program_files) / "Git" / "usr" / "bin" / "openssl.exe",
        Path(program_files_x86) / "Git" / "usr" / "bin" / "openssl.exe",
    ]:
        if candidate.exists():
            return str(candidate)
    return "openssl"


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def merge_csv(*values: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in split_csv(value):
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return ",".join(merged)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(stable_json(value).encode("utf-8"))


def guess_world_advertise_host() -> str:
    for env_name in ("SILICIUM_WORLD_ADVERTISE_HOST", "TAILSCALE_IP", "TS_IP"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate:
            return candidate
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if family != socket.AF_INET:
                continue
            host = str(sockaddr[0]).strip()
            if host and not host.startswith("127."):
                return host
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            host = str(sock.getsockname()[0]).strip()
            if host and not host.startswith("127."):
                return host
    except OSError:
        pass
    return "127.0.0.1"


def derive_world_mesh_key(world_name: str) -> str:
    normalized = str(world_name or "").strip().lower()
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"world:{normalized}:{digest}"


def fragment_status_name(fragment_account: dict[str, Any] | Any) -> str:
    status = fragment_account.get("status") if isinstance(fragment_account, dict) else getattr(fragment_account, "status", None)
    if isinstance(status, dict) and status:
        return str(next(iter(status.keys())))
    return str(status or "unknown")


def reputation_value(account: dict[str, Any] | Any, field: str) -> float:
    value: Any
    if isinstance(account, dict):
        value = account.get(field)
    else:
        value = getattr(account, field, None)
    if value is None:
        return 0.0
    if hasattr(value, "toString"):
        try:
            value = value.toString()
        except Exception:
            pass
    try:
        return float(value)
    except Exception:
        return 0.0


def read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
    last_error: Exception | None = None
    for _ in range(8):
        try:
            tmp.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
    try:
        if tmp.exists():
            tmp.unlink()
    finally:
        if last_error is not None:
            raise last_error


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n")


@dataclass
class NodeConfig:
    export_dir: Path
    roles: set[str]
    node_id: str
    idle_ms: int
    once: bool
    max_items: int
    p2p_gateway: str
    state_dir: Path
    solana_enable: bool
    solana_rpc: str
    solana_program_id: str
    solana_wallet: str
    solana_bridge: Path
    solana_timeout_s: int
    max_retries: int
    worker_binary: str
    worker_mode: str
    bootstrap_worker: bool
    gossip_enable: bool
    gossip_bind: str
    gossip_port: int
    peer_http_bind: str
    peer_http_port: int
    peer_advertise_host: str
    peer_advertise_port: int
    gossip_advertise_host: str
    gossip_advertise_port: int
    seed_peers: list[str]
    mesh_key: str
    peer_sync_interval_s: int
    peer_event_limit: int
    peer_stale_after_s: int
    relay_enable: bool
    relay_hops: int
    identity_key_path: str
    reputation_score: float
    replication_factor: int
    replication_quorum: int
    discovery_seeds: list[str]
    discovery_sync_interval_s: int
    remote_dispatch_enable: bool
    remote_dispatch_limit: int
    pull_tasks_enable: bool
    pull_tasks_interval_s: int
    nat_punch_enable: bool
    solana_reputation_enable: bool
    solana_reputation_refresh_s: int
    scheduler_onchain_weight: float
    scheduler_offchain_weight: float
    scheduler_capacity_weight: float


def build_capacity_snapshot(config: NodeConfig) -> dict[str, Any]:
    disk = shutil.disk_usage(config.export_dir)
    return {
        "node_id": config.node_id,
        "roles": sorted(config.roles),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "solana_enabled": config.solana_enable,
        "worker_binary": config.worker_binary,
        "worker_mode": config.worker_mode,
    }


def _peer_constraints(body: Mapping[str, Any] | None, envelope: Mapping[str, Any] | None = None) -> dict[str, float]:
    body = body or {}
    envelope = envelope or {}
    on_chain = envelope.get("on_chain") if isinstance(envelope.get("on_chain"), dict) else {}
    if not isinstance(on_chain, dict):
        on_chain = {}

    def _float_value(*keys: str) -> float:
        for source in (body, envelope, on_chain):
            for key in keys:
                if key in source and source.get(key) not in (None, ""):
                    try:
                        return float(source.get(key))
                    except Exception:
                        continue
        return 0.0

    return {
        "min_global_reputation": _float_value("min_global_reputation", "required_global_reputation", "global_reputation_threshold"),
        "min_compute_reputation": _float_value("min_compute_reputation", "required_compute_reputation", "compute_reputation_threshold"),
        "min_verify_reputation": _float_value("min_verify_reputation", "required_verify_reputation", "verify_reputation_threshold"),
        "min_storage_reputation": _float_value("min_storage_reputation", "required_storage_reputation", "storage_reputation_threshold"),
        "min_stake_amount": _float_value("min_stake_amount", "required_stake", "stake_threshold"),
    }


class NodeIdentity:
    HMAC_PUBLIC_PREFIX = b"SILICIUM-HMAC-SHA256:"

    def __init__(self, config: NodeConfig) -> None:
        default_key = config.state_dir / "peer_identity_ed25519.pem"
        self.private_key_path = Path(config.identity_key_path).expanduser() if str(config.identity_key_path).strip() else default_key
        self.public_key_path = self.private_key_path.with_suffix(".pub.pem")
        self.hmac_key_path = self.private_key_path.with_suffix(".hmac.key")
        self.openssl = find_openssl_command()
        self.private_key_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_keypair()
        public_pem = self.public_key_path.read_bytes()
        self.public_key_b64 = base64.b64encode(public_pem).decode("ascii")
        self.identity_id = sha256_bytes(public_pem)[:32]

    def sign_bytes(self, data: bytes) -> str:
        if self.hmac_key_path.exists():
            return self._sign_hmac(data, self.hmac_key_path.read_text(encoding="ascii").strip())
        with tempfile.TemporaryDirectory(prefix="silicium-sign-") as tmpdir:
            msg_path = Path(tmpdir) / "message.bin"
            sig_path = Path(tmpdir) / "signature.bin"
            msg_path.write_bytes(data)
            try:
                completed = subprocess.run(
                    [self.openssl, "pkeyutl", "-sign", "-rawin", "-inkey", str(self.private_key_path), "-in", str(msg_path), "-out", str(sig_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                self._ensure_hmac_keypair()
                return self._sign_hmac(data, self.hmac_key_path.read_text(encoding="ascii").strip())
            if completed.returncode != 0:
                self._ensure_hmac_keypair()
                return self._sign_hmac(data, self.hmac_key_path.read_text(encoding="ascii").strip())
            return sig_path.read_bytes().hex()

    @staticmethod
    def verify_bytes(data: bytes, signature_hex: str, public_key_b64: str) -> bool:
        if not signature_hex or not public_key_b64:
            return False
        try:
            public_pem = base64.b64decode(public_key_b64.encode("ascii"))
            signature = bytes.fromhex(signature_hex)
        except Exception:
            return False
        if public_pem.startswith(NodeIdentity.HMAC_PUBLIC_PREFIX):
            secret_hex = public_pem[len(NodeIdentity.HMAC_PUBLIC_PREFIX) :].decode("ascii", errors="ignore")
            expected = NodeIdentity._sign_hmac(data, secret_hex)
            return hmac.compare_digest(expected, signature_hex)
        identity_id = sha256_bytes(public_pem)[:32]
        with tempfile.TemporaryDirectory(prefix=f"silicium-verify-{identity_id}-") as tmpdir:
            msg_path = Path(tmpdir) / "message.bin"
            sig_path = Path(tmpdir) / "signature.bin"
            pub_path = Path(tmpdir) / "public.pem"
            msg_path.write_bytes(data)
            sig_path.write_bytes(signature)
            pub_path.write_bytes(public_pem)
            openssl = find_openssl_command()
            try:
                completed = subprocess.run(
                    [openssl, "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(pub_path), "-in", str(msg_path), "-sigfile", str(sig_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError:
                return False
            return completed.returncode == 0

    @staticmethod
    def identity_id_for_key(public_key_b64: str) -> str:
        try:
            public_pem = base64.b64decode(public_key_b64.encode("ascii"))
        except Exception:
            return ""
        return sha256_bytes(public_pem)[:32]

    def _ensure_keypair(self) -> None:
        if self.hmac_key_path.exists():
            self._ensure_hmac_keypair()
            return
        if not self.private_key_path.exists():
            try:
                completed = subprocess.run(
                    [self.openssl, "genpkey", "-algorithm", "Ed25519", "-out", str(self.private_key_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError:
                self._ensure_hmac_keypair()
                return
            if completed.returncode != 0:
                self._ensure_hmac_keypair()
                return
        if not self.public_key_path.exists():
            try:
                completed = subprocess.run(
                    [self.openssl, "pkey", "-in", str(self.private_key_path), "-pubout", "-out", str(self.public_key_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError:
                self._ensure_hmac_keypair()
                return
            if completed.returncode != 0:
                self._ensure_hmac_keypair()
                return

    @staticmethod
    def _sign_hmac(data: bytes, secret_hex: str) -> str:
        try:
            secret = bytes.fromhex(secret_hex)
        except ValueError:
            secret = secret_hex.encode("utf-8")
        return hmac.new(secret, data, hashlib.sha256).hexdigest()

    def _ensure_hmac_keypair(self) -> None:
        if not self.hmac_key_path.exists():
            self.hmac_key_path.write_text(os.urandom(32).hex(), encoding="ascii")
        secret_hex = self.hmac_key_path.read_text(encoding="ascii").strip()
        self.public_key_path.write_bytes(self.HMAC_PUBLIC_PREFIX + secret_hex.encode("ascii"))


class QueueState:
    def __init__(self, state_dir: Path) -> None:
        self._state_path = state_dir / "queue_state.json"
        self._processed_path = state_dir / "processed.json"
        self._offsets: dict[str, int] = read_json(self._state_path, {})
        self._processed: dict[str, str] = read_json(self._processed_path, {})

    def offset_for(self, path: Path) -> int:
        return int(self._offsets.get(str(path), 0) or 0)

    def set_offset(self, path: Path, offset: int) -> None:
        self._offsets[str(path)] = max(0, int(offset))

    def seen(self, key: str) -> bool:
        return key in self._processed

    def mark_seen(self, key: str) -> None:
        self._processed[key] = utc_now()

    def save(self) -> None:
        atomic_write_json(self._state_path, self._offsets)
        # Keep the state bounded while preserving recent idempotency.
        items = list(self._processed.items())[-5000:]
        atomic_write_json(self._processed_path, dict(items))


class ReputationStore:
    def __init__(self, path: Path, initial_score: float = 0.0) -> None:
        self._path = path
        self._lock = threading.Lock()
        loaded = read_json(path, {})
        self._payload = loaded if isinstance(loaded, dict) else {}
        self._payload.setdefault("schema_version", 1)
        self._payload.setdefault("local_score", float(initial_score))
        self._payload.setdefault("peer_scores", {})
        self._payload.setdefault("history", [])
        self.save()

    def local_score(self) -> float:
        with self._lock:
            return float(self._payload.get("local_score", 0.0) or 0.0)

    def peer_score(self, node_id: str, default: float = 0.0) -> float:
        with self._lock:
            peers = self._payload.get("peer_scores", {})
            if not isinstance(peers, dict):
                return float(default)
            return float(peers.get(node_id, default) or default)

    def adjust_local(self, delta: float, reason: str) -> float:
        with self._lock:
            score = float(self._payload.get("local_score", 0.0) or 0.0) + float(delta)
            self._payload["local_score"] = score
            history = self._payload.get("history", [])
            if not isinstance(history, list):
                history = []
            history.append({"timestamp_utc": utc_now(), "delta": float(delta), "reason": reason})
            self._payload["history"] = history[-512:]
        self.save()
        return score

    def set_peer_score(self, node_id: str, score: float) -> None:
        if not node_id:
            return
        with self._lock:
            peers = self._payload.get("peer_scores", {})
            if not isinstance(peers, dict):
                peers = {}
            peers[node_id] = float(score)
            self._payload["peer_scores"] = peers
        self.save()

    def peer_dispatch_stats(self, node_id: str) -> dict[str, Any]:
        with self._lock:
            stats = self._payload.get("peer_dispatch_stats", {})
            if not isinstance(stats, dict):
                return {}
            value = stats.get(node_id, {})
            return dict(value) if isinstance(value, dict) else {}

    def record_peer_dispatch(self, node_id: str, role: str, item_id: str) -> dict[str, Any]:
        if not node_id:
            return {}
        with self._lock:
            stats = self._payload.get("peer_dispatch_stats", {})
            if not isinstance(stats, dict):
                stats = {}
            current = stats.get(node_id, {})
            if not isinstance(current, dict):
                current = {}
            inflight = max(0, int(current.get("inflight", 0) or 0)) + 1
            total = max(0, int(current.get("total_dispatched", 0) or 0)) + 1
            by_role = current.get("by_role", {})
            if not isinstance(by_role, dict):
                by_role = {}
            by_role[role] = max(0, int(by_role.get(role, 0) or 0)) + 1
            current.update(
                {
                    "inflight": inflight,
                    "total_dispatched": total,
                    "by_role": by_role,
                    "last_role": role,
                    "last_item_id": item_id,
                    "last_dispatched_utc": utc_now(),
                }
            )
            stats[node_id] = current
            self._payload["peer_dispatch_stats"] = stats
        self.save()
        return dict(current)

    def record_peer_result(self, node_id: str, ok: bool) -> dict[str, Any]:
        if not node_id:
            return {}
        with self._lock:
            stats = self._payload.get("peer_dispatch_stats", {})
            if not isinstance(stats, dict):
                stats = {}
            current = stats.get(node_id, {})
            if not isinstance(current, dict):
                current = {}
            current["inflight"] = max(0, int(current.get("inflight", 0) or 0) - 1)
            key = "completed" if ok else "failed"
            current[key] = max(0, int(current.get(key, 0) or 0)) + 1
            current["last_result_ok"] = bool(ok)
            current["last_result_utc"] = utc_now()
            stats[node_id] = current
            self._payload["peer_dispatch_stats"] = stats
        self.save()
        return dict(current)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._payload, separators=(",", ":"), ensure_ascii=True))

    def save(self) -> None:
        atomic_write_json(self._path, self.snapshot())


class P2PClient:
    def __init__(self, gateway: str, export_dir: Path, peer_network: "PeerNetwork | None" = None) -> None:
        self.gateway = gateway.rstrip("/")
        self.export_dir = export_dir
        self.peer_network = peer_network

    def fetch(self, p2p_ref: Any) -> tuple[bytes, dict[str, Any]]:
        if not p2p_ref:
            return b"", {"source": "none"}
        if not isinstance(p2p_ref, dict):
            raise ValueError("p2p_ref_not_object")
        shared_ref = p2p_ref.get("shared_ref")
        if isinstance(shared_ref, dict) and str(shared_ref.get("protocol", "")).lower() == "silicium":
            p2p_ref = shared_ref

        protocol = str(p2p_ref.get("protocol", "ipfs")).lower()
        content_id = str(p2p_ref.get("content_id") or p2p_ref.get("cid") or p2p_ref.get("url") or "").strip()
        if not content_id:
            raise ValueError("missing_p2p_content_id")

        if protocol == "file":
            path = Path(content_id).expanduser()
            data = path.read_bytes()
            return data, {"source": "file", "path": str(path), "size_bytes": len(data)}

        if protocol == "silicium":
            if self.peer_network is None:
                raise ValueError("peer_network_not_configured")
            data, peer_meta = self.peer_network.fetch_content(content_id, str(p2p_ref.get("peer_id", "")).strip())
            meta = {
                "source": "silicium-peer",
                "content_id": content_id,
                "peer_id": peer_meta.get("node_id", ""),
                "peer_url": peer_meta.get("http_base_url", ""),
                "size_bytes": len(data),
            }
            if peer_meta.get("relayed_via"):
                meta["relayed_via"] = peer_meta.get("relayed_via", "")
            return data, meta

        if protocol in {"http", "https"}:
            with urllib.request.urlopen(content_id, timeout=15) as response:
                data = response.read()
            return data, {"source": protocol, "url": content_id, "size_bytes": len(data)}

        if protocol == "ipfs":
            if content_id.startswith("ipfs://"):
                content_id = content_id[len("ipfs://") :]
            url = f"{self.gateway}/api/v0/cat?arg={content_id}"
            try:
                with urllib.request.urlopen(url, timeout=15) as response:
                    data = response.read()
                return data, {"source": "ipfs", "cid": content_id, "size_bytes": len(data)}
            except urllib.error.URLError:
                local = self.export_dir / "p2p" / content_id
                if local.exists():
                    data = local.read_bytes()
                    return data, {"source": "local-p2p-cache", "cid": content_id, "size_bytes": len(data)}
                raise

        # Unknown P2P protocols remain content-addressed references for now.
        return stable_json(p2p_ref).encode("utf-8"), {"source": protocol, "content_id": content_id}

    def put_local(
        self,
        data: bytes,
        *,
        replication_factor: int = 0,
        replication_quorum: int = 0,
        replication_roles: Iterable[str] | None = None,
        constraints: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        digest = sha256_bytes(data)
        path = self.export_dir / "p2p" / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        shared_ref = {"protocol": "silicium", "content_id": digest, "hash": "sha256:" + digest}
        replication: dict[str, Any] = {"attempted": 0, "stored": 0, "quorum": 0, "satisfied": True, "peers": []}
        if self.peer_network is not None:
            shared_ref["peer_id"] = self.peer_network.node_id
            self.peer_network.publish(
                "content_available",
                {"content_id": digest, "hash": "sha256:" + digest, "size_bytes": len(data)},
            )
            target_factor = max(0, int(replication_factor or 0))
            target_quorum = max(0, int(replication_quorum or 0))
            if target_factor > 0:
                replication = self.peer_network.replicate_content(
                    digest,
                    data,
                    target_factor=target_factor,
                    required_quorum=target_quorum or target_factor,
                    required_roles=replication_roles or {"storage"},
                    constraints=constraints,
                )
                shared_ref["replication"] = replication
        return {
            "protocol": "file",
            "content_id": str(path),
            "hash": "sha256:" + digest,
            "size_bytes": len(data),
            "shared_ref": shared_ref,
            "replication": replication,
        }

    def pin(self, p2p_ref: Any) -> dict[str, Any]:
        data, meta = self.fetch(p2p_ref)
        stored = self.put_local(data)
        return {"source": meta, "stored_ref": stored}

    def unpin(self, p2p_ref: Any) -> dict[str, Any]:
        if not isinstance(p2p_ref, dict):
            raise ValueError("p2p_ref_not_object")
        content_id = str(p2p_ref.get("content_id") or p2p_ref.get("cid") or "").strip()
        path = self.export_dir / "p2p" / content_id
        existed = path.exists()
        if existed:
            path.unlink()
        return {"content_id": content_id, "removed": existed}


class RoleRuntime:
    def __init__(self, config: NodeConfig, p2p: P2PClient) -> None:
        self.config = config
        self.p2p = p2p

    def raytracer_entrypoint(self, name: str) -> Path:
        script = Path(__file__).resolve().parents[1] / "workloads" / "raytracer" / f"{name}.py"
        if not script.exists():
            raise FileNotFoundError(f"raytracer_workload_entrypoint_not_found:{script}")
        return script

    def capacity(self) -> dict[str, Any]:
        return build_capacity_snapshot(self.config)

    def run_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        roles = {str(role).lower() for role in envelope.get("required_roles", [])}
        task_kind = str(task.get("kind", task.get("type", ""))).strip().lower()
        if "storage" in roles or task_kind in {"storage", "store", "pin", "replicate"}:
            return self.run_storage_task(envelope, task, p2p_data, p2p_meta)
        if "verify" in roles or task_kind in {"verify", "verification"}:
            return self.run_verify_task(envelope, task, p2p_data, p2p_meta)
        if "resource" in roles or task_kind in {"resource", "health", "capacity"}:
            return self.run_resource_task(envelope, task, p2p_data, p2p_meta)
        return self.run_compute_task(envelope, task, p2p_data, p2p_meta)

    def run_compute_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        if str(task.get("workload", "")).strip() == RAYTRACER_COMPUTE_WORKLOAD:
            return self.run_raytracer_compute_task(envelope, task, p2p_data, p2p_meta)
        if str(task.get("workload", "")).strip() == RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD:
            return self.run_raytracer_fragment_compute_task(envelope, task, p2p_data, p2p_meta)
        worker_result = self.try_worker_binary(task)
        material = {
            "task": task,
            "p2p_hash": sha256_bytes(p2p_data),
            "worker_result": worker_result,
        }
        return {
            "role_result": "compute",
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            "compute": worker_result,
            "result_hash": sha256_json(material),
        }

    def run_raytracer_compute_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        if not p2p_data:
            raise ValueError("raytracer_missing_scene_payload")
        script = self.raytracer_entrypoint("compute")
        timeout_s = int(task.get("timeout_s", 300) or 300)
        with tempfile.TemporaryDirectory(prefix="silicium-raytracer-") as tmpdir:
            tmp = Path(tmpdir)
            scene_path = tmp / "scene.cfg"
            output_path = tmp / "render.ppm"
            result_path = tmp / "result.json"
            scene_path.write_bytes(p2p_data)
            cmd = [
                sys.executable,
                str(script),
                "--scene",
                str(scene_path),
                "--output",
                str(output_path),
                "--result-json",
                str(result_path),
                "--timeout-s",
                str(timeout_s),
            ]
            completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s + 30, check=False)
            if completed.returncode != 0:
                raise RuntimeError(f"raytracer_worker_failed:{completed.stderr[-2048:]}")
            result = read_json(result_path, {})
            if not isinstance(result, dict):
                raise RuntimeError("raytracer_worker_bad_result")
            output_bytes = output_path.read_bytes()
            output_ref = self.p2p.put_local(output_bytes, replication_roles={"storage"})
        result_hash = str(result.get("result_sha256") or sha256_bytes(output_bytes))
        expected = str(task.get("expected_result_sha256") or "").removeprefix("sha256:")
        return {
            "role_result": "compute",
            "workload": RAYTRACER_COMPUTE_WORKLOAD,
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            "result_hash": result_hash,
            "expected_result_hash": expected,
            "expected_match": (not expected) or expected == result_hash,
            "output_ref": output_ref,
            "output_format": result.get("result_format", "ppm/p6"),
            "renderer": {
                "mode": "raytracer",
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4096:],
                "stderr": completed.stderr[-4096:],
            },
        }

    def _raytracer_fragment_spec(self, task: dict[str, Any], p2p_data: bytes) -> dict[str, Any]:
        spec: dict[str, Any] = {}
        if p2p_data:
            parsed = json.loads(p2p_data.decode("utf-8"))
            if isinstance(parsed, dict):
                spec.update(parsed)
        spec.update({key: value for key, value in task.items() if key in {"fragment_index", "fragment_count", "y_start", "y_end", "scene_p2p_ref"}})
        if "scene_p2p_ref" not in spec:
            raise ValueError("raytracer_fragment_missing_scene_ref")
        return spec

    def run_raytracer_fragment_compute_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        spec = self._raytracer_fragment_spec(task, p2p_data)
        scene_data, scene_meta = self.p2p.fetch(spec.get("scene_p2p_ref"))
        script = self.raytracer_entrypoint("compute")
        timeout_s = int(task.get("timeout_s", 300) or 300)
        y_start = int(spec.get("y_start", 0) or 0)
        y_end = int(spec.get("y_end", 0) or 0)
        with tempfile.TemporaryDirectory(prefix="silicium-raytracer-fragment-") as tmpdir:
            tmp = Path(tmpdir)
            scene_path = tmp / "scene.cfg"
            output_path = tmp / "fragment.ppm"
            result_path = tmp / "result.json"
            scene_path.write_bytes(scene_data)
            cmd = [
                sys.executable,
                str(script),
                "--scene",
                str(scene_path),
                "--output",
                str(output_path),
                "--result-json",
                str(result_path),
                "--timeout-s",
                str(timeout_s),
                "--y-start",
                str(y_start),
                "--y-end",
                str(y_end),
            ]
            completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s + 30, check=False)
            if completed.returncode != 0:
                raise RuntimeError(f"raytracer_fragment_worker_failed:{completed.stderr[-2048:]}")
            result = read_json(result_path, {})
            if not isinstance(result, dict):
                raise RuntimeError("raytracer_fragment_worker_bad_result")
            output_bytes = output_path.read_bytes()
            output_ref = self.p2p.put_local(output_bytes, replication_roles={"storage"})
        result_hash = str(result.get("result_sha256") or sha256_bytes(output_bytes))
        expected = str(task.get("expected_result_sha256") or spec.get("expected_result_sha256") or "").removeprefix("sha256:")
        return {
            "role_result": "compute",
            "workload": RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD,
            "input": p2p_meta,
            "scene_input": scene_meta,
            "input_hash": sha256_bytes(p2p_data),
            "fragment_index": int(spec.get("fragment_index", 0) or 0),
            "fragment_count": int(spec.get("fragment_count", 1) or 1),
            "y_start": y_start,
            "y_end": y_end,
            "result_hash": result_hash,
            "expected_result_hash": expected,
            "expected_match": (not expected) or expected == result_hash,
            "output_ref": output_ref,
            "output_format": result.get("result_format", "ppm/p6"),
            "renderer": {
                "mode": "raytracer-fragment",
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4096:],
                "stderr": completed.stderr[-4096:],
            },
        }

    def try_worker_binary(self, task: dict[str, Any]) -> dict[str, Any]:
        summary = str(task.get("summary") or task.get("summary_path") or "").strip()
        partition = str(task.get("partition_id") or task.get("task_id") or "").strip()
        if not summary:
            return {"mode": "deterministic-local", "executed": False, "reason": "missing_summary"}
        binary = Path(str(task.get("worker_binary") or self.config.worker_binary)).expanduser()
        if not binary.exists():
            return {"mode": "deterministic-local", "executed": False, "reason": "worker_binary_missing", "path": str(binary)}
        cmd = [str(binary), "--summary", summary, "--mode", str(task.get("mode") or self.config.worker_mode), "--output", "json"]
        if partition:
            cmd.extend(["--task", partition])
        inputs = (task.get("inputs") or {}) if isinstance(task.get("inputs"), dict) else {}
        for key, value in inputs.items():
            cmd.extend(["--input", f"{key}={value}"])
        completed = subprocess.run(cmd, text=True, capture_output=True, timeout=int(task.get("timeout_s", 120)), check=False)
        parsed: Any
        try:
            parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
        except json.JSONDecodeError:
            parsed = {"stdout": completed.stdout}
        return {
            "mode": "worker-binary",
            "executed": completed.returncode == 0,
            "returncode": completed.returncode,
            "command": cmd,
            "stdout": parsed,
            "stderr": completed.stderr[-4096:],
        }

    def run_storage_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        replication_factor = int(task.get("replication_factor", self.config.replication_factor) or self.config.replication_factor)
        replication_quorum = int(task.get("replication_quorum", self.config.replication_quorum) or self.config.replication_quorum)
        stored_ref = self.p2p.put_local(
            p2p_data if p2p_data else stable_json(task).encode("utf-8"),
            replication_factor=replication_factor,
            replication_quorum=replication_quorum,
            replication_roles={"storage"},
            constraints=_peer_constraints(task, envelope),
        )
        manifest = {
            "task_id": envelope.get("task_id", ""),
            "kind": "storage",
            "source": p2p_meta,
            "stored_ref": stored_ref,
            "replication_factor": replication_factor,
            "replication_quorum": replication_quorum,
        }
        manifest_ref = self.p2p.put_local(stable_json(manifest).encode("utf-8"))
        return {
            "role_result": "storage",
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            "stored_ref": stored_ref,
            "replication": stored_ref.get("replication", {}),
            "manifest_ref": manifest_ref,
            "manifest_hash": sha256_json(manifest),
            "result_hash": sha256_json({"stored_ref": stored_ref, "manifest_ref": manifest_ref}),
        }

    def run_verify_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        if str(task.get("workload", "")).strip() == RAYTRACER_VERIFY_WORKLOAD:
            return self.run_raytracer_verify_task(envelope, task, p2p_data, p2p_meta)
        if str(task.get("workload", "")).strip() == RAYTRACER_FRAGMENT_VERIFY_WORKLOAD:
            return self.run_raytracer_fragment_verify_task(envelope, task, p2p_data, p2p_meta)
        actual = sha256_bytes(p2p_data)
        expected = str(task.get("expected_hash") or envelope.get("expected_hash") or "").removeprefix("sha256:")
        passed = not expected or expected == actual
        return {
            "role_result": "verify",
            "input": p2p_meta,
            "input_hash": actual,
            "expected_hash": expected,
            "verified": passed,
            "choice": passed,
            "result_hash": sha256_json({"verified": passed, "actual": actual, "expected": expected}),
        }

    def run_raytracer_verify_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        if not p2p_data:
            raise ValueError("raytracer_missing_result_payload")
        scene_ref = task.get("scene_p2p_ref") or envelope.get("scene_p2p_ref")
        if not isinstance(scene_ref, dict):
            raise ValueError("raytracer_missing_scene_ref")
        scene_data, scene_meta = self.p2p.fetch(scene_ref)
        script = self.raytracer_entrypoint("verify")
        timeout_s = int(task.get("timeout_s", 300) or 300)
        with tempfile.TemporaryDirectory(prefix="silicium-raytracer-verify-") as tmpdir:
            tmp = Path(tmpdir)
            scene_path = tmp / "scene.cfg"
            result_path = tmp / "verify.json"
            result_input_path = tmp / "result.ppm"
            scene_path.write_bytes(scene_data)
            result_input_path.write_bytes(p2p_data)
            cmd = [
                sys.executable,
                str(script),
                "--scene",
                str(scene_path),
                "--result",
                str(result_input_path),
                "--expected-hash",
                str(task.get("expected_hash") or envelope.get("expected_hash") or ""),
                "--result-json",
                str(result_path),
                "--timeout-s",
                str(timeout_s),
            ]
            completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s + 30, check=False)
            if completed.returncode not in (0, 2):
                raise RuntimeError(f"raytracer_verify_worker_failed:{completed.stderr[-2048:]}")
            verify_payload = read_json(result_path, {})
        actual = sha256_bytes(p2p_data)
        recomputed = str(verify_payload.get("recomputed_hash") or "")
        declared = str(task.get("expected_hash") or envelope.get("expected_hash") or "").removeprefix("sha256:")
        passed = bool(verify_payload.get("verified", False))
        return {
            "role_result": "verify",
            "workload": RAYTRACER_VERIFY_WORKLOAD,
            "input": p2p_meta,
            "scene": scene_meta,
            "input_hash": actual,
            "recomputed_hash": recomputed,
            "expected_hash": declared,
            "verified": passed,
            "choice": passed,
            "result_hash": sha256_json({"verified": passed, "actual": actual, "recomputed": recomputed, "expected": declared}),
            "renderer": {
                "mode": "raytracer-verify",
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4096:],
                "stderr": completed.stderr[-4096:],
            },
        }

    def run_raytracer_fragment_verify_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        if not p2p_data:
            raise ValueError("raytracer_fragment_missing_result_payload")
        scene_ref = task.get("scene_p2p_ref") or envelope.get("scene_p2p_ref")
        if not isinstance(scene_ref, dict):
            raise ValueError("raytracer_fragment_missing_scene_ref")
        scene_data, scene_meta = self.p2p.fetch(scene_ref)
        script = self.raytracer_entrypoint("verify")
        timeout_s = int(task.get("timeout_s", 300) or 300)
        y_start = int(task.get("y_start", 0) or 0)
        y_end = int(task.get("y_end", 0) or 0)
        with tempfile.TemporaryDirectory(prefix="silicium-raytracer-fragment-verify-") as tmpdir:
            tmp = Path(tmpdir)
            scene_path = tmp / "scene.cfg"
            result_path = tmp / "verify.json"
            result_input_path = tmp / "fragment.ppm"
            scene_path.write_bytes(scene_data)
            result_input_path.write_bytes(p2p_data)
            cmd = [
                sys.executable,
                str(script),
                "--scene",
                str(scene_path),
                "--result",
                str(result_input_path),
                "--expected-hash",
                str(task.get("expected_hash") or envelope.get("expected_hash") or ""),
                "--result-json",
                str(result_path),
                "--timeout-s",
                str(timeout_s),
                "--y-start",
                str(y_start),
                "--y-end",
                str(y_end),
            ]
            completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s + 30, check=False)
            if completed.returncode not in (0, 2):
                raise RuntimeError(f"raytracer_fragment_verify_worker_failed:{completed.stderr[-2048:]}")
            verify_payload = read_json(result_path, {})
        actual = sha256_bytes(p2p_data)
        recomputed = str(verify_payload.get("recomputed_hash") or "")
        declared = str(task.get("expected_hash") or envelope.get("expected_hash") or "").removeprefix("sha256:")
        passed = bool(verify_payload.get("verified", False))
        return {
            "role_result": "verify",
            "workload": RAYTRACER_FRAGMENT_VERIFY_WORKLOAD,
            "input": p2p_meta,
            "scene": scene_meta,
            "fragment_index": int(task.get("fragment_index", 0) or 0),
            "fragment_count": int(task.get("fragment_count", 1) or 1),
            "y_start": y_start,
            "y_end": y_end,
            "input_hash": actual,
            "recomputed_hash": recomputed,
            "expected_hash": declared,
            "verified": passed,
            "choice": passed,
            "result_hash": sha256_json({"verified": passed, "actual": actual, "recomputed": recomputed, "expected": declared}),
            "renderer": {
                "mode": "raytracer-fragment-verify",
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4096:],
                "stderr": completed.stderr[-4096:],
            },
        }

    def run_resource_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        capacity = self.capacity()
        return {
            "role_result": "resource",
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            "capacity": capacity,
            "result_hash": sha256_json(capacity),
        }

    def run_request(self, envelope: dict[str, Any], request: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        kind = str(envelope.get("kind", request.get("kind", "request"))).lower()
        if kind in {"health", "resource"}:
            return {"request_result": kind, "capacity": self.capacity(), "choice": True}
        if kind in {"pin", "replicate"}:
            storage = self.p2p.pin(envelope.get("p2p_ref") or request.get("p2p_ref"))
            return {"request_result": kind, "storage": storage, "choice": True}
        if kind == "unpin":
            return {"request_result": kind, "storage": self.p2p.unpin(envelope.get("p2p_ref") or request.get("p2p_ref")), "choice": True}
        if kind == "retrieve":
            stored = self.p2p.put_local(
                p2p_data,
                replication_factor=self.config.replication_factor,
                replication_quorum=self.config.replication_quorum,
                replication_roles={"storage"},
                constraints=_peer_constraints(request, envelope),
            )
            return {"request_result": kind, "retrieved_ref": stored, "choice": True}
        expected = str(request.get("expected_hash") or envelope.get("expected_hash") or "").removeprefix("sha256:")
        actual = sha256_bytes(p2p_data)
        choice = not expected or expected == actual
        return {
            "request_result": kind,
            "input_hash": actual,
            "expected_hash": expected,
            "choice": choice,
            "audit": {"passed": choice, "source": p2p_meta},
        }


class PeerNetwork:
    def __init__(self, config: NodeConfig, export_dir: Path) -> None:
        self.config = config
        self.export_dir = export_dir
        self.node_id = safe_id(config.node_id)
        self.identity = NodeIdentity(config)
        self.peers_path = export_dir / f"node.{self.node_id}.peers.json"
        self.gossip_events_path = export_dir / "gossip.events.ndjson"
        self.discovery_registry_path = export_dir / "mesh.discovery.json"
        self._peers: dict[str, dict[str, Any]] = {}
        self._seen_events: set[str] = set()
        self._lock = threading.Lock()
        self._http_server: http.server.ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._udp_socket: socket.socket | None = None
        self._udp_thread: threading.Thread | None = None
        self._sync_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._peer_score_sink: Any = None
        self._scheduler_store: ReputationStore | None = None
        self.http_base_url = ""
        self.advertised_http_base_url = ""
        self.gossip_target = ""
        self.mesh_post_url = ""
        self.local_capacity = build_capacity_snapshot(config)
        self.local_reputation_score = float(config.reputation_score)
        self.local_onchain_reputation = 0.0
        self.local_onchain_global_reputation = 0.0
        self.local_onchain_compute_reputation = 0.0
        self.local_onchain_verify_reputation = 0.0
        self.local_onchain_storage_reputation = 0.0
        self.local_onchain_stake_amount = 0.0
        self.local_onchain_status = ""
        self.local_solana_owner = ""
        self.local_solana_worker = ""

    def start(self) -> None:
        self._start_http_server()
        if self.config.gossip_enable:
            self._start_udp_listener()
        self._load_persisted_peers()
        self._record_self_peer()
        if self.config.peer_sync_interval_s > 0:
            self._start_sync_loop()
        self.announce()
        self.sync_once()

    def stop(self) -> None:
        self._stop_event.set()
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
        if self._http_thread is not None:
            self._http_thread.join(timeout=1)
            self._http_thread = None
        if self._udp_socket is not None:
            try:
                self._udp_socket.close()
            except OSError:
                pass
            self._udp_socket = None
        if self._udp_thread is not None:
            self._udp_thread.join(timeout=1)
            self._udp_thread = None
        if self._sync_thread is not None:
            self._sync_thread.join(timeout=1)
            self._sync_thread = None

    def peers_snapshot(self) -> dict[str, Any]:
        self._prune_stale_peers()
        with self._lock:
            peers = sorted(self._peers.values(), key=lambda item: str(item.get("node_id", "")))
        payload = {"schema_version": 1, "node_id": self.node_id, "count": len(peers), "peers": peers, "updated_utc": utc_now()}
        atomic_write_json(self.peers_path, payload)
        atomic_write_json(self.discovery_registry_path, payload)
        return payload

    def set_local_profile(
        self,
        *,
        capacity: dict[str, Any] | None = None,
        reputation_score: float | None = None,
        onchain_reputation: float | None = None,
        onchain_global_reputation: float | None = None,
        onchain_compute_reputation: float | None = None,
        onchain_verify_reputation: float | None = None,
        onchain_storage_reputation: float | None = None,
        onchain_stake_amount: float | None = None,
        onchain_status: str | None = None,
        solana_owner: str | None = None,
        solana_worker: str | None = None,
    ) -> None:
        if capacity is not None:
            self.local_capacity = capacity
        if reputation_score is not None:
            self.local_reputation_score = float(reputation_score)
        if onchain_reputation is not None:
            self.local_onchain_reputation = float(onchain_reputation)
        if onchain_global_reputation is not None:
            self.local_onchain_global_reputation = float(onchain_global_reputation)
        if onchain_compute_reputation is not None:
            self.local_onchain_compute_reputation = float(onchain_compute_reputation)
        if onchain_verify_reputation is not None:
            self.local_onchain_verify_reputation = float(onchain_verify_reputation)
        if onchain_storage_reputation is not None:
            self.local_onchain_storage_reputation = float(onchain_storage_reputation)
        if onchain_stake_amount is not None:
            self.local_onchain_stake_amount = float(onchain_stake_amount)
        if onchain_status is not None:
            self.local_onchain_status = str(onchain_status)
        if solana_owner is not None:
            self.local_solana_owner = str(solana_owner)
        if solana_worker is not None:
            self.local_solana_worker = str(solana_worker)
        self._record_self_peer()

    def set_peer_score_sink(self, callback: Any) -> None:
        self._peer_score_sink = callback

    def set_scheduler_store(self, store: ReputationStore) -> None:
        self._scheduler_store = store

    def update_peer_metadata(self, node_id: str, updates: dict[str, Any]) -> None:
        if not node_id:
            return
        with self._lock:
            current = dict(self._peers.get(node_id, {}))
            current.update(dict(updates))
            current.setdefault("node_id", node_id)
            current.setdefault("last_seen_unix", int(time.time()))
            current.setdefault("updated_utc", utc_now())
            self._peers[node_id] = current
        self.peers_snapshot()

    def remove_peer(self, node_id: str) -> bool:
        node_id = safe_id(str(node_id or ""))
        if not node_id or node_id == self.node_id:
            return False
        with self._lock:
            removed = self._peers.pop(node_id, None) is not None
        if removed:
            self.peers_snapshot()
        return removed

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        message = {
            "message_type": "gossip_event",
            "event_id": uuid.uuid4().hex,
            "node_id": self.node_id,
            "topic": topic,
            "payload": payload,
            "timestamp_utc": utc_now(),
            "hops": 0,
        }
        self._sign_message(message)
        self._record_event(message)
        self._broadcast(message)

    def announce(self) -> None:
        message = {
            "message_type": "peer_announce",
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "roles": sorted(self.config.roles),
            "http_base_url": self.advertised_http_base_url,
            "mesh_post_url": self.mesh_post_url,
            "gossip_bind": self._advertised_gossip_host(),
            "gossip_port": self._advertised_gossip_port(),
            "relay_capable": bool(self.config.relay_enable),
            "capacity": self.local_capacity,
            "reputation_score": self.local_reputation_score,
            "onchain_reputation": self.local_onchain_reputation,
            "onchain_global_reputation": self.local_onchain_global_reputation,
            "onchain_compute_reputation": self.local_onchain_compute_reputation,
            "onchain_verify_reputation": self.local_onchain_verify_reputation,
            "onchain_storage_reputation": self.local_onchain_storage_reputation,
            "onchain_stake_amount": self.local_onchain_stake_amount,
            "onchain_status": self.local_onchain_status,
            "solana_owner": self.local_solana_owner,
            "solana_worker": self.local_solana_worker,
            "timestamp_utc": utc_now(),
        }
        self._sign_message(message)
        self._record_self_peer()
        self._broadcast(message)

    def fetch_content(self, content_id: str, preferred_peer_id: str = "") -> tuple[bytes, dict[str, Any]]:
        peers = self.peers_snapshot().get("peers", [])
        candidates = []
        if preferred_peer_id:
            candidates.extend([peer for peer in peers if str(peer.get("node_id", "")) == preferred_peer_id])
        candidates.extend([peer for peer in peers if str(peer.get("node_id", "")) != preferred_peer_id])
        for peer in candidates:
            data = self._fetch_direct_from_peer(peer, content_id)
            if data is not None:
                return data, peer
        if preferred_peer_id:
            self.request_udp_punch(preferred_peer_id)
            time.sleep(0.1)
            for peer in candidates:
                if str(peer.get("node_id", "")) != preferred_peer_id:
                    continue
                data = self._fetch_direct_from_peer(peer, content_id)
                if data is not None:
                    return data, peer
        relayed = self._fetch_via_relays(content_id, preferred_peer_id, candidates)
        if relayed is not None:
            return relayed
        raise FileNotFoundError(f"peer_content_not_found:{content_id}")

    def _record_self_peer(self) -> None:
        with self._lock:
            self._peers[self.node_id] = {
                "node_id": self.node_id,
                "identity_id": self.identity.identity_id,
                "public_key": self.identity.public_key_b64,
                "roles": sorted(self.config.roles),
                "http_base_url": self.advertised_http_base_url,
                "mesh_post_url": self.mesh_post_url,
                "gossip_bind": self._advertised_gossip_host(),
                "gossip_port": self._advertised_gossip_port(),
                "relay_capable": bool(self.config.relay_enable),
                "capacity": self.local_capacity,
                "reputation_score": self.local_reputation_score,
                "onchain_reputation": self.local_onchain_reputation,
                "onchain_global_reputation": self.local_onchain_global_reputation,
                "onchain_compute_reputation": self.local_onchain_compute_reputation,
                "onchain_verify_reputation": self.local_onchain_verify_reputation,
                "onchain_storage_reputation": self.local_onchain_storage_reputation,
                "onchain_stake_amount": self.local_onchain_stake_amount,
                "onchain_status": self.local_onchain_status,
                "solana_owner": self.local_solana_owner,
                "solana_worker": self.local_solana_worker,
                "last_seen_unix": int(time.time()),
                "updated_utc": utc_now(),
                "self": True,
            }
        self.peers_snapshot()

    def _record_peer(self, message: dict[str, Any]) -> bool:
        node_id = safe_id(str(message.get("node_id", "")))
        if not node_id:
            return False
        changed = False
        with self._lock:
            current = dict(self._peers.get(node_id, {}))
            merged = {
                "node_id": node_id,
                "identity_id": str(message.get("identity_id", "")),
                "public_key": str(message.get("public_key", "")),
                "roles": list(message.get("roles", [])),
                "http_base_url": str(message.get("http_base_url", "")),
                "mesh_post_url": str(message.get("mesh_post_url", "")),
                "gossip_bind": str(message.get("gossip_bind", "")),
                "gossip_port": int(message.get("gossip_port", 0) or 0),
                "relay_capable": bool(message.get("relay_capable", False)),
                "capacity": message.get("capacity", {}) if isinstance(message.get("capacity"), dict) else {},
                "reputation_score": float(message.get("reputation_score", 0.0) or 0.0),
                "onchain_reputation": float(message.get("onchain_reputation", 0.0) or 0.0),
                "onchain_global_reputation": float(message.get("onchain_global_reputation", 0.0) or 0.0),
                "onchain_compute_reputation": float(message.get("onchain_compute_reputation", 0.0) or 0.0),
                "onchain_verify_reputation": float(message.get("onchain_verify_reputation", 0.0) or 0.0),
                "onchain_storage_reputation": float(message.get("onchain_storage_reputation", 0.0) or 0.0),
                "onchain_stake_amount": float(message.get("onchain_stake_amount", 0.0) or 0.0),
                "onchain_status": str(message.get("onchain_status", "")),
                "solana_owner": str(message.get("solana_owner", "")),
                "solana_worker": str(message.get("solana_worker", "")),
                "updated_utc": str(message.get("timestamp_utc", utc_now())),
                "last_seen_unix": int(time.time()),
                "self": node_id == self.node_id,
            }
            changed = any(current.get(key) != value for key, value in merged.items() if key not in {"updated_utc", "last_seen_unix"})
            current.update(merged)
            self._peers[node_id] = current
        self.peers_snapshot()
        if node_id != self.node_id and self._peer_score_sink is not None:
            try:
                self._peer_score_sink(node_id, float(merged.get("reputation_score", 0.0) or 0.0))
            except Exception:
                pass
        return changed

    def _record_event(self, message: dict[str, Any]) -> bool:
        event_id = str(message.get("event_id", "")).strip()
        if not event_id:
            return False
        with self._lock:
            if event_id in self._seen_events:
                return False
            self._seen_events.add(event_id)
        append_jsonl(self.gossip_events_path, message)
        return True

    def _broadcast(self, message: dict[str, Any], exclude: str = "") -> None:
        udp_targets: set[str] = set()
        http_targets: set[str] = set()
        for seed in self.config.seed_peers:
            host, port = self._parse_udp_target(seed)
            if host and port > 0:
                udp_targets.add(f"{host}:{port}")
                continue
            http_base = self._normalize_http_target(seed)
            if http_base:
                http_targets.add(http_base)
        with self._lock:
            for peer in self._peers.values():
                bind = str(peer.get("gossip_bind", "")).strip()
                port = int(peer.get("gossip_port", 0) or 0)
                if bind and port:
                    udp_targets.add(f"{bind}:{port}")
                http_base = str(peer.get("http_base_url", "")).strip()
                if http_base:
                    http_targets.add(http_base)
        for target in sorted(udp_targets):
            host, _, port_raw = target.partition(":")
            try:
                port = int(port_raw)
            except ValueError:
                continue
            if not host or port <= 0:
                continue
            if exclude and target == exclude:
                continue
            self._send_udp(target, host, port, message)
        for base_url in sorted(http_targets):
            if not base_url or base_url == self.advertised_http_base_url:
                continue
            if exclude and base_url == exclude:
                continue
            self._send_http(base_url, message)

    def _send_udp(self, target: str, host: str, port: int, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(payload, (host, port))
        finally:
            sock.close()

    def _send_http(self, base_url: str, message: dict[str, Any]) -> None:
        url = base_url.rstrip("/") + "/mesh"
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers=self._signed_headers("POST", "/mesh", data, {"Content-Type": "application/json"}))
        try:
            with urllib.request.urlopen(req, timeout=5):
                return
        except (TimeoutError, OSError, urllib.error.URLError):
            return

    def _fetch_direct_from_peer(self, peer: dict[str, Any], content_id: str) -> bytes | None:
        base_url = str(peer.get("http_base_url", "")).rstrip("/")
        if not base_url:
            return None
        path = f"/p2p/{quote(content_id, safe='')}"
        request = urllib.request.Request(base_url + path, headers=self._signed_headers("GET", path, b""))
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.read()
        except (TimeoutError, OSError, urllib.error.URLError):
            return None

    def _fetch_via_relays(self, content_id: str, preferred_peer_id: str, candidates: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]] | None:
        target_peer_id = preferred_peer_id or str(next((peer.get("node_id", "") for peer in candidates if peer.get("node_id")), ""))
        if not target_peer_id:
            return None
        for relay in self.select_peers(required_roles=set(), limit=max(1, self.config.relay_hops), require_relay=True, exclude={target_peer_id}):
            relay_url = str(relay.get("http_base_url", "")).rstrip("/")
            if not relay_url:
                continue
            path = f"/relay/fetch?peer_id={quote(target_peer_id, safe='')}&content_id={quote(content_id, safe='')}"
            request = urllib.request.Request(relay_url + path, headers=self._signed_headers("GET", path, b""))
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.read(), {"node_id": target_peer_id, "http_base_url": relay_url, "relayed_via": relay.get("node_id", "")}
            except (TimeoutError, OSError, urllib.error.URLError):
                continue
        return None

    def replicate_content(
        self,
        content_id: str,
        data: bytes,
        *,
        target_factor: int,
        required_quorum: int,
        required_roles: Iterable[str] | None = None,
        constraints: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        peers = self.select_peers(
            required_roles=set(required_roles or {"storage"}),
            limit=max(0, target_factor),
            exclude={self.node_id},
            constraints=constraints,
        )
        report = {"attempted": 0, "stored": 0, "quorum": max(0, required_quorum), "satisfied": True, "peers": []}
        for peer in peers:
            report["attempted"] += 1
            ok = self._push_replica(peer, content_id, data)
            report["peers"].append({"node_id": peer.get("node_id", ""), "ok": ok})
            if ok:
                report["stored"] += 1
        report["satisfied"] = report["stored"] >= max(0, required_quorum)
        if report["stored"] > 0:
            self.publish("content_replicated", {"content_id": content_id, "stored": report["stored"], "quorum": report["quorum"]})
        return report

    def request_udp_punch(self, target_peer_id: str) -> bool:
        if not self.config.nat_punch_enable:
            return False
        for relay in self.select_peers(required_roles=set(), limit=max(1, self.config.relay_hops), require_relay=True, exclude={target_peer_id}):
            relay_url = str(relay.get("http_base_url", "")).rstrip("/")
            if not relay_url:
                continue
            payload = {"target_peer_id": target_peer_id}
            raw = stable_json(payload).encode("utf-8")
            path = "/relay/punch"
            request = urllib.request.Request(
                relay_url + path,
                data=raw,
                method="POST",
                headers=self._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status == 200
            except (TimeoutError, OSError, urllib.error.URLError):
                continue
        return False

    def select_peers(
        self,
        *,
        required_roles: set[str] | None = None,
        limit: int = 0,
        require_relay: bool = False,
        exclude: set[str] | None = None,
        constraints: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        exclude_ids = exclude or set()
        required_roles = required_roles or set()
        constraints = constraints or {}
        candidates: list[dict[str, Any]] = []
        for peer in self.peers_snapshot().get("peers", []):
            node_id = str(peer.get("node_id", ""))
            if not node_id or node_id in exclude_ids or peer.get("self"):
                continue
            peer_roles = {str(role).lower() for role in peer.get("roles", [])}
            if required_roles and not required_roles.intersection(peer_roles):
                continue
            if require_relay and not bool(peer.get("relay_capable", False)):
                continue
            if not self._peer_meets_constraints(peer, required_roles, constraints):
                continue
            candidates.append(peer)
        candidates.sort(key=lambda peer: self._peer_score(peer, required_roles), reverse=True)
        if limit > 0:
            return candidates[:limit]
        return candidates

    def _peer_meets_constraints(self, peer: dict[str, Any], required_roles: set[str], constraints: dict[str, float]) -> bool:
        status = str(peer.get("onchain_status", "")).strip().lower()
        if status and status not in {"active", "1", "workerstatus.active"}:
            return False
        local_reputation = float(peer.get("reputation_score", 0.0) or 0.0)
        global_reputation = float(peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0)) or 0.0)
        compute_reputation = float(peer.get("onchain_compute_reputation", 0.0) or 0.0)
        verify_reputation = float(peer.get("onchain_verify_reputation", 0.0) or 0.0)
        storage_reputation = float(peer.get("onchain_storage_reputation", 0.0) or 0.0)
        if not self.config.solana_reputation_enable:
            global_reputation = global_reputation or local_reputation
            compute_reputation = compute_reputation or local_reputation
            verify_reputation = verify_reputation or local_reputation
            storage_reputation = storage_reputation or local_reputation
        checks = {
            "min_global_reputation": global_reputation,
            "min_compute_reputation": compute_reputation,
            "min_verify_reputation": verify_reputation,
            "min_storage_reputation": storage_reputation,
            "min_stake_amount": float(peer.get("onchain_stake_amount", 0.0) or 0.0),
        }
        if "compute" in required_roles and checks["min_compute_reputation"] <= 0 and self.config.solana_reputation_enable:
            return False
        if "verify" in required_roles and checks["min_verify_reputation"] <= 0 and self.config.solana_reputation_enable:
            return False
        if "storage" in required_roles and checks["min_storage_reputation"] <= 0 and self.config.solana_reputation_enable:
            return False
        for key, actual in checks.items():
            minimum = float(constraints.get(key, 0.0) or 0.0)
            if minimum > 0 and actual < minimum:
                return False
        return True

    def _role_reputation_field(self, required_roles: set[str]) -> str:
        if "verify" in required_roles:
            return "onchain_verify_reputation"
        if "storage" in required_roles:
            return "onchain_storage_reputation"
        return "onchain_compute_reputation"

    def _peer_score_components(self, peer: dict[str, Any], required_roles: set[str]) -> dict[str, float]:
        capacity = peer.get("capacity", {}) if isinstance(peer.get("capacity"), dict) else {}
        reputation = float(peer.get("reputation_score", 0.0) or 0.0)
        role_field = self._role_reputation_field(required_roles)
        onchain_reputation = float(peer.get(role_field, peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0))) or 0.0)
        cpu = float(capacity.get("cpu_count", 0) or 0)
        disk_free = float(capacity.get("disk_free_bytes", 0) or 0)
        dispatch_stats = self._scheduler_store.peer_dispatch_stats(str(peer.get("node_id", ""))) if self._scheduler_store is not None else {}
        inflight = float(dispatch_stats.get("inflight", 0) or 0)
        total_dispatched = float(dispatch_stats.get("total_dispatched", 0) or 0)
        onchain_component = onchain_reputation * max(0.0, float(self.config.scheduler_onchain_weight))
        offchain_component = reputation * max(0.0, float(self.config.scheduler_offchain_weight))
        capacity_component = (cpu + (disk_free / max(1.0, 1024.0 * 1024.0 * 1024.0))) * max(
            0.0, float(self.config.scheduler_capacity_weight)
        )
        raw_score = onchain_component + offchain_component + capacity_component
        fairness_unit = max(1.0, raw_score)
        load_penalty = inflight * fairness_unit * 0.75 + total_dispatched * fairness_unit * 0.20
        total = raw_score - load_penalty
        return {
            "total": float(total),
            "raw": float(raw_score),
            "onchain": float(onchain_component),
            "offchain": float(offchain_component),
            "capacity": float(capacity_component),
            "load_penalty": float(load_penalty),
            "inflight": float(inflight),
            "total_dispatched": float(total_dispatched),
            "role_reputation": float(onchain_reputation),
            "local_reputation": float(reputation),
        }

    def _peer_score(self, peer: dict[str, Any], required_roles: set[str]) -> tuple[float, float, float, float, str]:
        components = self._peer_score_components(peer, required_roles)
        return (
            components["total"],
            components["role_reputation"],
            components["local_reputation"],
            components["capacity"],
            str(peer.get("node_id", "")),
        )

    def _push_replica(self, peer: dict[str, Any], content_id: str, data: bytes) -> bool:
        base_url = str(peer.get("http_base_url", "")).rstrip("/")
        if not base_url:
            return False
        path = f"/p2p/ingest?content_id={quote(content_id, safe='')}"
        request = urllib.request.Request(
            base_url + path,
            data=data,
            method="POST",
            headers=self._signed_headers("POST", path, data, {"Content-Type": "application/octet-stream"}),
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
        except (TimeoutError, OSError, urllib.error.URLError):
            return False

    def _start_udp_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.config.gossip_bind, self.config.gossip_port))
        sock.settimeout(0.5)
        self._udp_socket = sock
        self.config.gossip_port = int(sock.getsockname()[1])

        def _loop() -> None:
            while self._udp_socket is sock:
                try:
                    payload, addr = sock.recvfrom(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    message = json.loads(payload.decode("utf-8"))
                except Exception:
                    continue
                self._handle_udp_message(message, f"{addr[0]}:{addr[1]}")

        self._udp_thread = threading.Thread(target=_loop, name=f"silicium-gossip-{self.node_id}", daemon=True)
        self._udp_thread.start()

    def _handle_network_message(self, message: dict[str, Any], sender: str) -> None:
        if not self._verify_message(message):
            return
        message_type = str(message.get("message_type", ""))
        if message_type == "peer_announce":
            changed = self._record_peer(message)
            if changed and safe_id(str(message.get("node_id", ""))) != self.node_id:
                self.announce()
            return
        if message_type == "punch_probe":
            target_host = str(message.get("target_host", "")).strip()
            target_port = int(message.get("target_port", 0) or 0)
            if target_host and target_port > 0:
                probe = {
                    "message_type": "peer_announce",
                    "node_id": self.node_id,
                    "identity_id": self.identity.identity_id,
                    "public_key": self.identity.public_key_b64,
                    "roles": sorted(self.config.roles),
                    "http_base_url": self.advertised_http_base_url,
                    "mesh_post_url": self.mesh_post_url,
                    "gossip_bind": self._advertised_gossip_host(),
                    "gossip_port": self._advertised_gossip_port(),
                    "relay_capable": bool(self.config.relay_enable),
                    "capacity": self.local_capacity,
                    "reputation_score": self.local_reputation_score,
                    "timestamp_utc": utc_now(),
                }
                self._sign_message(probe)
                self._send_udp(f"{target_host}:{target_port}", target_host, target_port, probe)
            return
        if message_type != "gossip_event":
            return
        if not self._record_event(message):
            return
        hops = int(message.get("hops", 0) or 0)
        if hops >= 2:
            return
        forwarded = dict(message)
        forwarded["hops"] = hops + 1
        self._broadcast(forwarded, exclude=sender)

    def _handle_udp_message(self, message: dict[str, Any], sender: str) -> None:
        self._handle_network_message(message, sender)

    def _start_sync_loop(self) -> None:
        def _loop() -> None:
            while not self._stop_event.wait(max(1, self.config.peer_sync_interval_s)):
                self.sync_once()

        self._sync_thread = threading.Thread(target=_loop, name=f"silicium-peer-sync-{self.node_id}", daemon=True)
        self._sync_thread.start()

    def sync_once(self) -> None:
        self._prune_stale_peers()
        self.announce()
        targets = self._sync_targets()
        for base_url in targets:
            self._sync_peer_table(base_url)
            self._sync_recent_events(base_url)
        self._sync_discovery()

    def recent_events(self, limit: int) -> list[dict[str, Any]]:
        if limit <= 0 or not self.gossip_events_path.exists():
            return []
        try:
            lines = self.gossip_events_path.read_text(encoding="utf-8").splitlines()[-limit:]
        except Exception:
            return []
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events

    def _load_persisted_peers(self) -> None:
        snapshot = read_json(self.peers_path, {})
        peers = snapshot.get("peers") if isinstance(snapshot, dict) else None
        if not isinstance(peers, list):
            return
        now = int(time.time())
        with self._lock:
            for peer in peers:
                if not isinstance(peer, dict):
                    continue
                node_id = safe_id(str(peer.get("node_id", "")))
                if not node_id or node_id == self.node_id:
                    continue
                loaded = dict(peer)
                loaded["node_id"] = node_id
                loaded["last_seen_unix"] = int(peer.get("last_seen_unix", now))
                self._peers[node_id] = loaded

    def _sync_discovery(self) -> None:
        seeds = [seed for seed in self.config.discovery_seeds if seed.strip()]
        for seed in seeds:
            base_url = self._normalize_http_target(seed)
            if not base_url:
                continue
            self._register_with_discovery(base_url)
            self._fetch_discovery_snapshot(base_url)

    def _register_with_discovery(self, base_url: str) -> None:
        payload = {
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "roles": sorted(self.config.roles),
            "http_base_url": self.advertised_http_base_url,
            "mesh_post_url": self.mesh_post_url,
            "gossip_bind": self._advertised_gossip_host(),
            "gossip_port": self._advertised_gossip_port(),
            "relay_capable": bool(self.config.relay_enable),
            "capacity": self.local_capacity,
            "reputation_score": self.local_reputation_score,
            "timestamp_utc": utc_now(),
        }
        raw = stable_json(payload).encode("utf-8")
        path = "/discovery/register"
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=raw,
            method="POST",
            headers=self._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        try:
            with urllib.request.urlopen(request, timeout=5):
                return
        except Exception:
            return

    def _fetch_discovery_snapshot(self, base_url: str) -> None:
        path = "/discovery/snapshot"
        request = urllib.request.Request(base_url.rstrip("/") + path, headers=self._signed_headers("GET", path, b""))
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        peers = payload.get("peers") if isinstance(payload, dict) else None
        if not isinstance(peers, list):
            return
        for peer in peers:
            if isinstance(peer, dict):
                self._record_peer(peer)

    def _sync_targets(self) -> list[str]:
        targets: set[str] = set()
        for seed in self.config.seed_peers:
            http_base = self._normalize_http_target(seed)
            if http_base:
                targets.add(http_base)
        with self._lock:
            for peer in self._peers.values():
                http_base = str(peer.get("http_base_url", "")).strip()
                if http_base:
                    targets.add(http_base)
        targets.discard("")
        targets.discard(self.advertised_http_base_url)
        return sorted(targets)

    def _sync_peer_table(self, base_url: str) -> None:
        path = "/peers"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(base_url.rstrip("/") + path, headers=self._signed_headers("GET", path, b"")), timeout=5
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        peers = payload.get("peers") if isinstance(payload, dict) else None
        if not isinstance(peers, list):
            return
        for peer in peers:
            if isinstance(peer, dict):
                self._record_peer(peer)

    def _sync_recent_events(self, base_url: str) -> None:
        path = f"/events/recent?limit={max(1, self.config.peer_event_limit)}"
        url = f"{base_url.rstrip('/')}{path}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=self._signed_headers("GET", path, b"")), timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return
        for event in events:
            if isinstance(event, dict):
                self._handle_network_message(event, base_url)

    def _prune_stale_peers(self) -> None:
        if self.config.peer_stale_after_s <= 0:
            return
        cutoff = int(time.time()) - int(self.config.peer_stale_after_s)
        removed = False
        with self._lock:
            for node_id in list(self._peers.keys()):
                peer = self._peers[node_id]
                if peer.get("self"):
                    continue
                if int(peer.get("last_seen_unix", 0) or 0) < cutoff:
                    self._peers.pop(node_id, None)
                    removed = True
        if removed:
            atomic_write_json(self.peers_path, {"schema_version": 1, "node_id": self.node_id, "count": len(self._peers), "peers": list(self._peers.values()), "updated_utc": utc_now()})

    def _advertised_http_host(self) -> str:
        return str(self.config.peer_advertise_host or "").strip() or urlparse(self.http_base_url).hostname or "127.0.0.1"

    def _advertised_http_port(self) -> int:
        if self.config.peer_advertise_port > 0:
            return int(self.config.peer_advertise_port)
        parsed = urlparse(self.http_base_url)
        return int(parsed.port or 0)

    def _advertised_gossip_host(self) -> str:
        return str(self.config.gossip_advertise_host or "").strip() or str(self.config.gossip_bind)

    def _advertised_gossip_port(self) -> int:
        if self.config.gossip_advertise_port > 0:
            return int(self.config.gossip_advertise_port)
        return int(self.config.gossip_port)

    def _normalize_http_target(self, target: str) -> str:
        value = str(target or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return ""

    def _parse_udp_target(self, target: str) -> tuple[str, int]:
        value = str(target or "").strip()
        if not value:
            return "", 0
        if value.startswith("udp://"):
            value = value[len("udp://") :]
        if "://" in value:
            return "", 0
        host, _, port_raw = value.partition(":")
        try:
            port = int(port_raw)
        except ValueError:
            return "", 0
        return host.strip(), port

    def _signed_headers(self, method: str, path: str, body: bytes, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self.config.mesh_key:
            headers["Authorization"] = f"Bearer {self.config.mesh_key}"
        timestamp = str(int(time.time()))
        body_hash = sha256_bytes(body)
        signing_payload = "\n".join([method.upper(), path, timestamp, body_hash, self.node_id, self.identity.identity_id]).encode("utf-8")
        headers.update(
            {
                "X-Silicium-Node-Id": self.node_id,
                "X-Silicium-Identity-Id": self.identity.identity_id,
                "X-Silicium-Public-Key": self.identity.public_key_b64,
                "X-Silicium-Timestamp": timestamp,
                "X-Silicium-Body-Hash": body_hash,
                "X-Silicium-Signature": self.identity.sign_bytes(signing_payload),
            }
        )
        return headers

    def _sign_message(self, message: dict[str, Any]) -> None:
        unsigned = dict(message)
        unsigned["identity_id"] = self.identity.identity_id
        unsigned["public_key"] = self.identity.public_key_b64
        unsigned["node_id"] = self.node_id
        if self.config.mesh_key:
            unsigned.pop("mesh_mac", None)
            unsigned["mesh_mac"] = hmac.new(self.config.mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
        unsigned.pop("mesh_mac", None)
        unsigned.pop("signature", None)
        message.update(unsigned)
        message["signature"] = self.identity.sign_bytes(stable_json(unsigned).encode("utf-8"))
        if self.config.mesh_key:
            message["mesh_mac"] = hmac.new(self.config.mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()

    def _verify_message(self, message: dict[str, Any]) -> bool:
        public_key = str(message.get("public_key", "")).strip()
        signature = str(message.get("signature", "")).strip()
        identity_id = str(message.get("identity_id", "")).strip()
        if public_key and signature:
            if NodeIdentity.identity_id_for_key(public_key) != identity_id:
                return False
            unsigned = dict(message)
            unsigned.pop("signature", None)
            unsigned.pop("mesh_mac", None)
            if not NodeIdentity.verify_bytes(stable_json(unsigned).encode("utf-8"), signature, public_key):
                if not self.config.mesh_key:
                    return False
        elif self.config.mesh_key:
            return False
        if self.config.mesh_key:
            received = str(message.get("mesh_mac", "")).strip()
            if not received:
                return False
            unsigned = dict(message)
            unsigned.pop("signature", None)
            unsigned.pop("mesh_mac", None)
            expected = hmac.new(self.config.mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(received, expected):
                return False
        return True

    def _authorize_peer_request(self, handler: http.server.BaseHTTPRequestHandler, body: bytes = b"") -> bool:
        if self.config.mesh_key:
            auth = str(handler.headers.get("Authorization", "")).strip()
            if auth == f"Bearer {self.config.mesh_key}":
                return True
        public_key = str(handler.headers.get("X-Silicium-Public-Key", "")).strip()
        signature = str(handler.headers.get("X-Silicium-Signature", "")).strip()
        identity_id = str(handler.headers.get("X-Silicium-Identity-Id", "")).strip()
        timestamp = str(handler.headers.get("X-Silicium-Timestamp", "")).strip()
        body_hash = str(handler.headers.get("X-Silicium-Body-Hash", "")).strip()
        node_id = str(handler.headers.get("X-Silicium-Node-Id", "")).strip()
        if not public_key or not signature or not identity_id or not timestamp or not node_id:
            return False
        if NodeIdentity.identity_id_for_key(public_key) != identity_id:
            return False
        try:
            ts = int(timestamp)
        except ValueError:
            return False
        if abs(int(time.time()) - ts) > 300:
            return False
        if body_hash != sha256_bytes(body):
            return False
        signing_payload = "\n".join([handler.command.upper(), handler.path, timestamp, body_hash, node_id, identity_id]).encode("utf-8")
        return NodeIdentity.verify_bytes(signing_payload, signature, public_key)

    def _start_http_server(self) -> None:
        peer_network = self

        class _PeerHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/healthz":
                    raw = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/peers":
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    raw = stable_json(peer_network.peers_snapshot()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/discovery/snapshot":
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    raw = stable_json(read_json(peer_network.discovery_registry_path, peer_network.peers_snapshot())).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path.startswith("/events/recent"):
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    query = parse_qs(urlparse(self.path).query)
                    try:
                        limit = int((query.get("limit") or [str(peer_network.config.peer_event_limit)])[0])
                    except ValueError:
                        limit = peer_network.config.peer_event_limit
                    raw = stable_json({"schema_version": 1, "node_id": peer_network.node_id, "events": peer_network.recent_events(limit)}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path.startswith("/p2p/"):
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    content_id = unquote(self.path[len("/p2p/") :]).strip()
                    target = peer_network.export_dir / "p2p" / content_id
                    if not target.exists():
                        self.send_error(404)
                        return
                    raw = target.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path.startswith("/relay/fetch"):
                    if not peer_network.config.relay_enable or not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    query = parse_qs(urlparse(self.path).query)
                    peer_id = str((query.get("peer_id") or [""])[0]).strip()
                    content_id = str((query.get("content_id") or [""])[0]).strip()
                    if not peer_id or not content_id:
                        self.send_error(400)
                        return
                    target_peer = peer_network._peers.get(peer_id)
                    if not isinstance(target_peer, dict):
                        self.send_error(404)
                        return
                    data = peer_network._fetch_direct_from_peer(target_peer, content_id)
                    if data is None:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                try:
                    size = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    size = 0
                raw = self.rfile.read(max(0, size))
                if not peer_network._authorize_peer_request(self, raw):
                    self.send_error(403)
                    return
                if self.path == "/mesh":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    peer_network._handle_network_message(payload, self.client_address[0])
                    body = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/discovery/register":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    peer_network._record_peer(payload)
                    body = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/peers/leave":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    removed = peer_network.remove_peer(str(payload.get("node_id", "")))
                    body = stable_json({"ok": True, "removed": removed}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.startswith("/p2p/ingest"):
                    query = parse_qs(urlparse(self.path).query)
                    content_id = str((query.get("content_id") or [""])[0]).strip() or sha256_bytes(raw)
                    target = peer_network.export_dir / "p2p" / content_id
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_bytes(raw)
                    peer_network.publish("content_available", {"content_id": content_id, "hash": "sha256:" + sha256_bytes(raw), "size_bytes": len(raw)})
                    body = stable_json({"ok": True, "content_id": content_id}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/tasks/dispatch":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    enqueue_task_envelope(peer_network.export_dir, payload)
                    body = b'{"ok":true}'
                    self.send_response(202)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/tasks/claim":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    try:
                        result = peer_network.node.claim_task_for_peer(payload)
                    except Exception:
                        self.send_error(400)
                        return
                    body = stable_json(result).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/requests/dispatch":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    enqueue_request_envelope(peer_network.export_dir, payload)
                    body = b'{"ok":true}'
                    self.send_response(202)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/results/dispatch":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    try:
                        peer_network.node.ingest_dispatched_result(payload)
                    except Exception:
                        self.send_error(400)
                        return
                    body = b'{"ok":true}'
                    self.send_response(202)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.startswith("/relay/mesh"):
                    if not peer_network.config.relay_enable:
                        self.send_error(403)
                        return
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    target_peer_id = str(payload.get("peer_id", "")).strip()
                    message = payload.get("message")
                    target_peer = peer_network._peers.get(target_peer_id)
                    if not target_peer_id or not isinstance(message, dict) or not isinstance(target_peer, dict):
                        self.send_error(400)
                        return
                    peer_network._send_http(str(target_peer.get("http_base_url", "")).rstrip("/"), message)
                    body = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/relay/punch":
                    if not peer_network.config.relay_enable:
                        self.send_error(403)
                        return
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    target_peer_id = str(payload.get("target_peer_id", "")).strip()
                    requester_peer = peer_network._peers.get(str(self.headers.get("X-Silicium-Node-Id", "")).strip(), {})
                    target_peer = peer_network._peers.get(target_peer_id, {})
                    if not isinstance(requester_peer, dict) or not isinstance(target_peer, dict):
                        self.send_error(404)
                        return
                    requester_host = str(requester_peer.get("gossip_bind", "")).strip()
                    requester_port = int(requester_peer.get("gossip_port", 0) or 0)
                    target_host = str(target_peer.get("gossip_bind", "")).strip()
                    target_port = int(target_peer.get("gossip_port", 0) or 0)
                    if requester_host and requester_port > 0 and target_host and target_port > 0:
                        probe_to_target = {
                            "message_type": "punch_probe",
                            "node_id": peer_network.node_id,
                            "identity_id": peer_network.identity.identity_id,
                            "public_key": peer_network.identity.public_key_b64,
                            "target_host": requester_host,
                            "target_port": requester_port,
                            "timestamp_utc": utc_now(),
                        }
                        peer_network._sign_message(probe_to_target)
                        peer_network._send_udp(f"{target_host}:{target_port}", target_host, target_port, probe_to_target)
                        probe_to_requester = {
                            "message_type": "punch_probe",
                            "node_id": peer_network.node_id,
                            "identity_id": peer_network.identity.identity_id,
                            "public_key": peer_network.identity.public_key_b64,
                            "target_host": target_host,
                            "target_port": target_port,
                            "timestamp_utc": utc_now(),
                        }
                        peer_network._sign_message(probe_to_requester)
                        peer_network._send_udp(f"{requester_host}:{requester_port}", requester_host, requester_port, probe_to_requester)
                    body = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_error(404)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

        server = http.server.ThreadingHTTPServer((self.config.peer_http_bind, self.config.peer_http_port), _PeerHandler)
        self._http_server = server
        bind_host, bind_port = server.server_address[:2]
        local_host = "127.0.0.1" if bind_host in {"0.0.0.0", ""} else str(bind_host)
        self.http_base_url = f"http://{local_host}:{bind_port}"
        self.advertised_http_base_url = f"http://{self._advertised_http_host()}:{self._advertised_http_port()}"
        self.mesh_post_url = self.advertised_http_base_url.rstrip("/") + "/mesh"
        self.gossip_target = f"{self._advertised_gossip_host()}:{self._advertised_gossip_port()}" if self._advertised_gossip_port() > 0 else ""

        self._http_thread = threading.Thread(target=server.serve_forever, name=f"silicium-peer-http-{self.node_id}", daemon=True)
        self._http_thread.start()


class SolanaBridge:
    def __init__(self, config: NodeConfig) -> None:
        self.config = config

    def call(self, op: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.config.solana_enable:
            return {"ok": True, "enabled": False, "skipped": True, "op": op, "reason": "solana_disabled"}
        if not self.config.solana_program_id:
            raise ValueError("missing_solana_program_id")
        if not self.config.solana_wallet:
            raise ValueError("missing_solana_wallet")
        if not self.config.solana_bridge.exists():
            raise ValueError(f"missing_solana_bridge:{self.config.solana_bridge}")

        request = {
            "op": op,
            "rpc_url": self.config.solana_rpc,
            "program_id": self.config.solana_program_id,
            "wallet_path": self.config.solana_wallet,
            "params": params,
        }
        completed = subprocess.run(
            ["node", str(self.config.solana_bridge)],
            input=json.dumps(request, separators=(",", ":"), ensure_ascii=True),
            text=True,
            capture_output=True,
            timeout=max(1, self.config.solana_timeout_s),
            check=False,
        )
        raw = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"solana_bridge_bad_json:{completed.stdout}:{completed.stderr}") from exc
        if completed.returncode != 0 or payload.get("ok") is False:
            message = payload.get("error") or completed.stderr.strip() or "solana_bridge_failed"
            raise RuntimeError(str(message))
        return payload


def enqueue_task_envelope(export_dir: Path, envelope: dict[str, Any]) -> None:
    task_id = safe_id(str(envelope.get("task_id", "")))
    if not task_id:
        raise ValueError("missing_task_id")
    payload = dict(envelope)
    payload["task_id"] = task_id
    payload["envelope_kind"] = "task"
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    tasks_dir = export_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    final_path = tasks_dir / f"{task_id}.json"
    tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
    tmp_path.write_text(encoded, encoding="utf-8")
    tmp_path.replace(final_path)
    with (export_dir / "tasks.queue.ndjson").open("a", encoding="utf-8") as queue:
        queue.write(encoded + "\n")
    roles = envelope.get("required_roles", ["compute"])
    if isinstance(roles, list) and roles:
        with (export_dir / f"tasks.{str(roles[0]).lower()}.queue.ndjson").open("a", encoding="utf-8") as queue:
            queue.write(encoded + "\n")


def enqueue_request_envelope(export_dir: Path, envelope: dict[str, Any]) -> None:
    request_id = safe_id(str(envelope.get("request_id", "")))
    if not request_id:
        raise ValueError("missing_request_id")
    payload = dict(envelope)
    payload["request_id"] = request_id
    payload["envelope_kind"] = "request"
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    requests_dir = export_dir / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    final_path = requests_dir / f"{request_id}.json"
    tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
    tmp_path.write_text(encoded, encoding="utf-8")
    tmp_path.replace(final_path)
    with (export_dir / "requests.queue.ndjson").open("a", encoding="utf-8") as queue:
        queue.write(encoded + "\n")
    priority = str(envelope.get("priority", "normal")).lower()
    if priority in {"high", "urgent"}:
        with (export_dir / "requests.urgent.ndjson").open("a", encoding="utf-8") as queue:
            queue.write(encoded + "\n")
    roles = envelope.get("target_roles", ["resource"])
    if isinstance(roles, list):
        for role in roles:
            with (export_dir / f"requests.{str(role).lower()}.queue.ndjson").open("a", encoding="utf-8") as queue:
                queue.write(encoded + "\n")


class NetworkNode:
    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.state = QueueState(config.state_dir)
        self.reputation = ReputationStore(config.export_dir / f"node.{safe_id(config.node_id)}.reputation.json", initial_score=config.reputation_score)
        self.config.reputation_score = self.reputation.local_score()
        self.peer_network = PeerNetwork(config, config.export_dir)
        self.peer_network.node = self
        self.peer_network.set_peer_score_sink(self.reputation.set_peer_score)
        self.peer_network.set_scheduler_store(self.reputation)
        self.p2p = P2PClient(config.p2p_gateway, config.export_dir, self.peer_network)
        self.solana = SolanaBridge(config)
        self.runtime = RoleRuntime(config, self.p2p)
        self.events_path = config.export_dir / "node.events.ndjson"
        self.heartbeat_path = config.export_dir / f"node.{safe_id(config.node_id)}.heartbeat.json"
        self.metrics_path = config.export_dir / f"node.{safe_id(config.node_id)}.metrics.json"
        self.metrics = read_json(
            self.metrics_path,
            {"schema_version": 1, "handled": 0, "failed": 0, "retried": 0, "dead_lettered": 0, "dispatched": 0, "dispatch_failed": 0},
        )
        self._claim_lock = threading.Lock()
        self._last_pull_unix = 0.0
        self._last_reputation_refresh_unix = 0.0
        self._last_peer_reputation_refresh_unix = 0.0
        self._solana_owner = ""
        self._solana_worker = ""
        self._solana_onchain_reputation = 0.0
        self._solana_onchain_compute_reputation = 0.0
        self._solana_onchain_verify_reputation = 0.0
        self._solana_onchain_storage_reputation = 0.0
        self._solana_onchain_stake_amount = 0.0
        self._solana_onchain_status = ""
        self.peer_network.set_local_profile(capacity=self.runtime.capacity(), reputation_score=self.reputation.local_score())

    def run(self) -> None:
        self.peer_network.start()
        try:
            self.bootstrap()
            self.refresh_local_onchain_profile(force=True)
            while True:
                self.write_heartbeat()
                pulled = self.pull_remote_task()
                handled = self.sweep()
                self.state.save()
                self.write_metrics()
                self.write_heartbeat()
                if self.config.once:
                    return
                if handled == 0 and not pulled:
                    time.sleep(max(0, self.config.idle_ms) / 1000.0)
        finally:
            self.peer_network.stop()

    def bootstrap(self) -> None:
        if not self.config.bootstrap_worker:
            return
        result = self.solana.call("register_worker", {})
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "bootstrap",
                "ok": bool(result.get("ok", True)),
                "solana": result,
            },
        )

    def solana_owner_pubkey(self) -> str:
        if self._solana_owner:
            return self._solana_owner
        try:
            secret = json.loads(Path(self.config.solana_wallet).expanduser().read_text(encoding="utf-8"))
            completed = subprocess.run(
                [
                    "node",
                    "-e",
                    (
                        "const {Keypair}=require('@solana/web3.js');"
                        "const kp=Keypair.fromSecretKey(Uint8Array.from(JSON.parse(process.argv[1])));"
                        "console.log(kp.publicKey.toBase58());"
                    ),
                    json.dumps(secret),
                ],
                cwd=str(Path(__file__).resolve().parents[1] / "solana-layer"),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                self._solana_owner = completed.stdout.strip()
        except Exception:
            self._solana_owner = ""
        return self._solana_owner

    def refresh_local_onchain_profile(self, *, force: bool = False) -> None:
        if not self.config.solana_enable or not self.config.solana_reputation_enable:
            return
        now = time.time()
        if not force and (now - self._last_reputation_refresh_unix) < max(1, self.config.solana_reputation_refresh_s):
            return
        owner = self.solana_owner_pubkey()
        if not owner:
            return
        try:
            snapshot = self.solana.call("fetch_worker", {"owner": owner})
        except Exception:
            return
        account = snapshot.get("account", {}) if isinstance(snapshot, dict) else {}
        accounts = snapshot.get("accounts", {}) if isinstance(snapshot, dict) else {}
        onchain_global = reputation_value(account, "globalReputation") or reputation_value(account, "global_reputation")
        onchain_compute = reputation_value(account, "computeReputation") or reputation_value(account, "compute_reputation")
        onchain_verify = reputation_value(account, "verifyReputation") or reputation_value(account, "verify_reputation")
        onchain_storage = reputation_value(account, "storageReputation") or reputation_value(account, "storage_reputation")
        onchain_stake = reputation_value(account, "stakeAmount") or reputation_value(account, "stake_amount")
        onchain_status = str(account.get("status", "")) if isinstance(account, dict) else str(getattr(account, "status", ""))
        self._solana_owner = str(accounts.get("owner", owner))
        self._solana_worker = str(accounts.get("worker", ""))
        self._solana_onchain_reputation = onchain_global
        self._solana_onchain_compute_reputation = onchain_compute
        self._solana_onchain_verify_reputation = onchain_verify
        self._solana_onchain_storage_reputation = onchain_storage
        self._solana_onchain_stake_amount = onchain_stake
        self._solana_onchain_status = onchain_status
        self._last_reputation_refresh_unix = now
        self.peer_network.set_local_profile(
            capacity=self.runtime.capacity(),
            reputation_score=self.reputation.local_score(),
            onchain_reputation=onchain_global,
            onchain_global_reputation=onchain_global,
            onchain_compute_reputation=onchain_compute,
            onchain_verify_reputation=onchain_verify,
            onchain_storage_reputation=onchain_storage,
            onchain_stake_amount=onchain_stake,
            onchain_status=onchain_status,
            solana_owner=self._solana_owner,
            solana_worker=self._solana_worker,
        )

    def refresh_known_peer_onchain_reputations(self) -> None:
        if not self.config.solana_enable or not self.config.solana_reputation_enable:
            return
        if (time.time() - self._last_peer_reputation_refresh_unix) < max(1, self.config.solana_reputation_refresh_s):
            return
        for peer in self.peer_network.peers_snapshot().get("peers", []):
            if not isinstance(peer, dict) or peer.get("self"):
                continue
            owner = str(peer.get("solana_owner", "")).strip()
            if not owner:
                continue
            try:
                snapshot = self.solana.call("fetch_worker", {"owner": owner})
            except Exception:
                continue
            account = snapshot.get("account", {}) if isinstance(snapshot, dict) else {}
            accounts = snapshot.get("accounts", {}) if isinstance(snapshot, dict) else {}
            onchain_global = reputation_value(account, "globalReputation") or reputation_value(account, "global_reputation")
            onchain_compute = reputation_value(account, "computeReputation") or reputation_value(account, "compute_reputation")
            onchain_verify = reputation_value(account, "verifyReputation") or reputation_value(account, "verify_reputation")
            onchain_storage = reputation_value(account, "storageReputation") or reputation_value(account, "storage_reputation")
            onchain_stake = reputation_value(account, "stakeAmount") or reputation_value(account, "stake_amount")
            onchain_status = str(account.get("status", "")) if isinstance(account, dict) else str(getattr(account, "status", ""))
            self.peer_network.update_peer_metadata(
                str(peer.get("node_id", "")),
                {
                    "onchain_reputation": onchain_global,
                    "onchain_global_reputation": onchain_global,
                    "onchain_compute_reputation": onchain_compute,
                    "onchain_verify_reputation": onchain_verify,
                    "onchain_storage_reputation": onchain_storage,
                    "onchain_stake_amount": onchain_stake,
                    "onchain_status": onchain_status,
                    "solana_worker": str(accounts.get("worker", peer.get("solana_worker", ""))),
                    "solana_owner": str(accounts.get("owner", owner)),
                    "onchain_verified_utc": utc_now(),
                },
            )
        self._last_peer_reputation_refresh_unix = time.time()

    def write_heartbeat(self) -> None:
        self.refresh_local_onchain_profile()
        self.refresh_known_peer_onchain_reputations()
        capacity = self.runtime.capacity()
        current_reputation = self.reputation.local_score()
        self.config.reputation_score = current_reputation
        self.peer_network.set_local_profile(
            capacity=capacity,
            reputation_score=current_reputation,
            onchain_reputation=self._solana_onchain_reputation,
            onchain_global_reputation=self._solana_onchain_reputation,
            onchain_compute_reputation=getattr(self, "_solana_onchain_compute_reputation", 0.0),
            onchain_verify_reputation=getattr(self, "_solana_onchain_verify_reputation", 0.0),
            onchain_storage_reputation=getattr(self, "_solana_onchain_storage_reputation", 0.0),
            onchain_stake_amount=getattr(self, "_solana_onchain_stake_amount", 0.0),
            onchain_status=getattr(self, "_solana_onchain_status", ""),
            solana_owner=self._solana_owner,
            solana_worker=self._solana_worker,
        )
        atomic_write_json(
            self.heartbeat_path,
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "timestamp_utc": utc_now(),
                "roles": sorted(self.config.roles),
                "capacity": capacity,
                "reputation_score": current_reputation,
                "peer_http_base_url": self.peer_network.http_base_url,
                "peer_public_base_url": self.peer_network.advertised_http_base_url,
                "peer_count": int(self.peer_network.peers_snapshot().get("count", 0)),
                "gossip_enabled": self.config.gossip_enable,
                "peer_sync_interval_s": self.config.peer_sync_interval_s,
                "mesh_auth_enabled": bool(self.config.mesh_key),
                "identity_id": self.peer_network.identity.identity_id,
                "relay_enabled": self.config.relay_enable,
                "solana_owner": self._solana_owner,
                "solana_worker": self._solana_worker,
                "onchain_reputation": self._solana_onchain_reputation,
                "onchain_compute_reputation": self._solana_onchain_compute_reputation,
                "onchain_verify_reputation": self._solana_onchain_verify_reputation,
                "onchain_storage_reputation": self._solana_onchain_storage_reputation,
                "onchain_stake_amount": self._solana_onchain_stake_amount,
                "onchain_status": self._solana_onchain_status,
            },
        )

    def write_metrics(self) -> None:
        self.metrics["updated_utc"] = utc_now()
        atomic_write_json(self.metrics_path, self.metrics)

    def sweep(self) -> int:
        handled = 0
        for queue in self.queue_order():
            for envelope in self.read_new(queue):
                key = self.envelope_key(envelope)
                if self.state.seen(key):
                    continue
                if not self.accepts(envelope):
                    if self.try_remote_dispatch(envelope):
                        self.state.mark_seen(key)
                        handled += 1
                        if self.config.max_items > 0 and handled >= self.config.max_items:
                            return handled
                        continue
                    if {"resource", "storage"}.intersection(self.config.roles):
                        continue
                    self.schedule_retry_or_dead_letter(envelope, "no_local_role_and_dispatch_failed")
                    self.state.mark_seen(key)
                    continue
                self.handle(envelope)
                self.state.mark_seen(key)
                handled += 1
                if self.config.max_items > 0 and handled >= self.config.max_items:
                    return handled
        return handled

    def queue_order(self) -> list[Path]:
        queues: list[Path] = [self.config.export_dir / "requests.urgent.ndjson", self.config.export_dir / "retries.ndjson"]
        for role in sorted(self.config.roles):
            queues.append(self.config.export_dir / f"requests.{role}.queue.ndjson")
        queues.append(self.config.export_dir / "requests.queue.ndjson")
        for role in sorted(self.config.roles):
            queues.append(self.config.export_dir / f"tasks.{role}.queue.ndjson")
        queues.append(self.config.export_dir / "tasks.queue.ndjson")
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in queues:
            if path not in seen:
                seen.add(path)
                unique.append(path)
        return unique

    def read_new(self, path: Path) -> Iterable[dict[str, Any]]:
        if not path.exists():
            return []
        offset = self.state.offset_for(path)
        envelopes: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        envelopes.append(payload)
                except json.JSONDecodeError:
                    continue
            self.state.set_offset(path, handle.tell())
        return envelopes

    def envelope_key(self, envelope: dict[str, Any]) -> str:
        kind = str(envelope.get("envelope_kind") or "task")
        attempt = int(envelope.get("attempt", 0) or 0)
        if kind == "request":
            return f"request:{envelope.get('request_id', '')}:{attempt}"
        return f"task:{envelope.get('task_id', '')}:{attempt}"

    def accepts(self, envelope: dict[str, Any]) -> bool:
        kind = str(envelope.get("envelope_kind") or "task")
        if kind == "request":
            target_roles = set(str(role) for role in envelope.get("target_roles", []))
            return not target_roles or bool(target_roles.intersection(self.config.roles))
        required_roles = set(str(role) for role in envelope.get("required_roles", ["compute"]))
        return bool(required_roles.intersection(self.config.roles))

    def refresh_claiming_peer(self, claim: dict[str, Any]) -> dict[str, Any]:
        node_id = safe_id(str(claim.get("node_id", "")))
        if not node_id:
            return {}
        roles = [str(role).lower() for role in claim.get("roles", []) if str(role).strip()]
        capacity = claim.get("capacity", {}) if isinstance(claim.get("capacity"), dict) else {}
        with self.peer_network._lock:
            current = dict(self.peer_network._peers.get(node_id, {}))
            current.update(
                {
                    "node_id": node_id,
                    "roles": roles or current.get("roles", []),
                    "capacity": capacity or current.get("capacity", {}),
                    "reputation_score": float(claim.get("reputation_score", current.get("reputation_score", 0.0)) or 0.0),
                    "last_seen_unix": int(time.time()),
                    "updated_utc": utc_now(),
                    "self": node_id == self.config.node_id,
                }
            )
            self.peer_network._peers[node_id] = current
        self.peer_network.peers_snapshot()
        return current

    def claim_task_for_peer(self, claim: dict[str, Any]) -> dict[str, Any]:
        node_id = safe_id(str(claim.get("node_id", "")))
        roles = {str(role).lower() for role in claim.get("roles", []) if str(role).strip()}
        if not node_id or not roles:
            raise ValueError("missing_claim_identity")
        peer = self.refresh_claiming_peer(claim)
        constraints_base = {
            "min_compute_reputation": float(claim.get("min_compute_reputation", 0.0) or 0.0),
            "min_verify_reputation": float(claim.get("min_verify_reputation", 0.0) or 0.0),
        }
        tasks_dir = self.config.export_dir / "tasks"
        if not tasks_dir.exists():
            return {"ok": True, "claimed": False}
        with self._claim_lock:
            for path in tasks_dir.glob("*.json"):
                envelope = read_json(path, {})
                if not isinstance(envelope, dict):
                    continue
                status = str(envelope.get("status", "")).lower()
                claimed_by = safe_id(str(envelope.get("claimed_by", "")))
                if status == "claimed" and claimed_by == node_id:
                    task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
                    try:
                        stale_after_s = max(300.0, float(task.get("timeout_s", 300.0) or 300.0) * 2.0)
                    except (TypeError, ValueError):
                        stale_after_s = 600.0
                    try:
                        claimed_age_s = max(0.0, time.time() - path.stat().st_mtime)
                    except OSError:
                        claimed_age_s = 0.0
                    if claimed_age_s <= stale_after_s:
                        return {"ok": True, "claimed": False, "reason": "node_already_has_active_task"}
                    envelope["status"] = "queued"
                    envelope["requeued_utc"] = utc_now()
                    envelope["requeue_reason"] = "stale_claim"
                    envelope.pop("claimed_by", None)
                    envelope.pop("claimed_utc", None)
                    atomic_write_json(path, envelope)
                    self.reputation.record_peer_result(node_id, False)
                    append_jsonl(
                        self.events_path,
                        {
                            "schema_version": 1,
                            "timestamp_utc": utc_now(),
                            "node_id": self.config.node_id,
                            "kind": "task_requeued",
                            "item_id": safe_id(str(envelope.get("task_id", path.stem))),
                            "source_node": node_id,
                            "reason": "stale_claim",
                        },
                    )
            for path in sorted(tasks_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
                envelope = read_json(path, {})
                if not isinstance(envelope, dict):
                    continue
                status = str(envelope.get("status", "queued")).lower()
                if status in {"claimed", "completed", "failed", "dead_lettered"}:
                    continue
                required_roles = {str(role).lower() for role in envelope.get("required_roles", ["compute"]) if str(role).strip()}
                if required_roles and not required_roles.intersection(roles):
                    continue
                task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
                constraints = {**constraints_base, **_peer_constraints(task, envelope)}
                if isinstance(peer, dict) and peer:
                    if not self.peer_network._peer_meets_constraints(peer, required_roles, constraints):
                        continue
                item_id = safe_id(str(envelope.get("task_id", path.stem)))
                scheduler_role = str(next(iter(required_roles), "task")).lower()
                current_stats = self.reputation.peer_dispatch_stats(node_id)
                current_by_role = current_stats.get("by_role", {}) if isinstance(current_stats.get("by_role"), dict) else {}
                current_count = int(current_by_role.get(scheduler_role, 0) or 0)
                alternatives = self.peer_network.select_peers(
                    required_roles=required_roles,
                    limit=0,
                    exclude={node_id, self.config.node_id},
                    constraints=constraints,
                )
                alternative_counts: list[int] = []
                for alternative in alternatives:
                    alternative_id = safe_id(str(alternative.get("node_id", "")))
                    alternative_stats = self.reputation.peer_dispatch_stats(alternative_id)
                    alternative_by_role = (
                        alternative_stats.get("by_role", {})
                        if isinstance(alternative_stats.get("by_role"), dict)
                        else {}
                    )
                    alternative_counts.append(int(alternative_by_role.get(scheduler_role, 0) or 0))
                try:
                    fairness_until_unix = float(envelope.get("fairness_until_unix", task.get("fairness_until_unix", 0.0)) or 0.0)
                except (TypeError, ValueError):
                    fairness_until_unix = 0.0
                if time.time() < fairness_until_unix:
                    if alternative_counts and current_count > min(alternative_counts):
                        continue
                excluded_raw = envelope.get("excluded_node_ids", task.get("excluded_node_ids", []))
                if isinstance(excluded_raw, str):
                    excluded_values = [excluded_raw]
                elif isinstance(excluded_raw, list):
                    excluded_values = excluded_raw
                else:
                    excluded_values = []
                excluded_node_ids = {safe_id(str(value)) for value in excluded_values if str(value).strip()}
                try:
                    excluded_until_unix = float(envelope.get("excluded_until_unix", task.get("excluded_until_unix", 0.0)) or 0.0)
                except (TypeError, ValueError):
                    excluded_until_unix = 0.0
                excluded_fallback = node_id in excluded_node_ids and time.time() >= excluded_until_unix > 0
                if node_id in excluded_node_ids and not excluded_fallback:
                    alternatives = self.peer_network.select_peers(
                        required_roles=required_roles,
                        limit=1,
                        exclude={node_id, self.config.node_id},
                        constraints=constraints,
                    )
                    if alternatives:
                        continue
                claimed = dict(envelope)
                claimed["status"] = "claimed"
                claimed["claimed_by"] = node_id
                claimed["claimed_utc"] = utc_now()
                claimed["dispatched_by"] = self.config.node_id
                claimed["dispatched_utc"] = utc_now()
                claimed["result_return_url"] = self.peer_network.advertised_http_base_url.rstrip("/") + "/results/dispatch"
                dispatch_stats = self.reputation.record_peer_dispatch(node_id, scheduler_role, item_id)
                self.peer_network.update_peer_metadata(node_id, {"scheduler_dispatch": dispatch_stats})
                claimed["scheduler"] = {
                    "kind": "worker_pull",
                    "selected_peer": node_id,
                    "required_roles": sorted(required_roles),
                    "dispatch_stats": dispatch_stats,
                    "excluded_fallback": excluded_fallback,
                }
                atomic_write_json(path, claimed)
                append_jsonl(
                    self.events_path,
                    {
                        "schema_version": 1,
                        "timestamp_utc": utc_now(),
                        "node_id": self.config.node_id,
                        "kind": "pull_claim",
                        "item_id": item_id,
                        "target_peer": node_id,
                        "roles": sorted(required_roles),
                    },
                )
                return {"ok": True, "claimed": True, "task": claimed}
        return {"ok": True, "claimed": False}

    def pull_remote_task(self) -> bool:
        if not self.config.pull_tasks_enable or not self.config.seed_peers:
            return False
        if not {"compute", "verify"}.intersection(self.config.roles):
            return False
        now = time.time()
        if now - self._last_pull_unix < max(1, self.config.pull_tasks_interval_s):
            return False
        self._last_pull_unix = now
        claim = {
            "schema_version": 1,
            "node_id": self.config.node_id,
            "roles": sorted(self.config.roles),
            "capacity": self.runtime.capacity(),
            "reputation_score": self.reputation.local_score(),
        }
        raw = stable_json(claim).encode("utf-8")
        for seed in self.config.seed_peers:
            base_url = self.peer_network._normalize_http_target(seed)
            if not base_url:
                continue
            path = "/tasks/claim"
            request = urllib.request.Request(
                base_url.rstrip("/") + path,
                data=raw,
                method="POST",
                headers=self.peer_network._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    if response.status not in {200, 202}:
                        continue
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict) or not payload.get("claimed"):
                continue
            task = payload.get("task")
            if not isinstance(task, dict) or not self.accepts(task):
                continue
            append_jsonl(
                self.events_path,
                {
                    "schema_version": 1,
                    "timestamp_utc": utc_now(),
                    "node_id": self.config.node_id,
                    "kind": "task_received",
                    "item_id": safe_id(str(task.get("task_id", "task"))),
                    "roles": sorted(task.get("required_roles", [])),
                },
            )
            self.handle(task)
            return True
        return False

    def handle(self, envelope: dict[str, Any]) -> None:
        started = time.monotonic()
        kind = str(envelope.get("envelope_kind") or "task")
        try:
            if kind == "request":
                result = self.handle_request(envelope)
                item_id = str(envelope.get("request_id", "request"))
            else:
                result = self.handle_task(envelope)
                item_id = str(envelope.get("task_id", "task"))
            ok = True
            error = ""
        except Exception as exc:
            item_id = str(envelope.get("request_id") or envelope.get("task_id") or "unknown")
            result = {"success": False, "error": str(exc)}
            ok = False
            error = str(exc)

        duration_ms = int((time.monotonic() - started) * 1000)
        result.update(
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "roles": sorted(self.config.roles),
                "finished_utc": utc_now(),
                "duration_ms": duration_ms,
            }
        )
        safe_item = safe_id(item_id)
        log_payload = {"schema_version": 1, "item_id": safe_item, "ok": ok, "error": error, "duration_ms": duration_ms}
        atomic_write_json(self.config.export_dir / f"result.{safe_item}.json", result)
        atomic_write_json(self.config.export_dir / f"logs.{safe_item}.json", log_payload)
        self.update_envelope_status(envelope, "completed" if ok else "failed", result)
        if ok:
            self.metrics["handled"] = int(self.metrics.get("handled", 0) or 0) + 1
        else:
            self.metrics["failed"] = int(self.metrics.get("failed", 0) or 0) + 1
            self.schedule_retry_or_dead_letter(envelope, error)
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": kind,
                "item_id": safe_item,
                "ok": ok,
                "error": error,
                "duration_ms": duration_ms,
            },
        )
        if ok and kind == "task":
            self.peer_network.publish(
                "fragment_result",
                {
                    "item_id": safe_item,
                    "result_hash": result.get("result_hash", ""),
                    "proof_ref": result.get("proof_ref", {}),
                },
        )
        self.update_reputation(ok, kind, result)
        if ok and result.get("on_chain"):
            self.refresh_local_onchain_profile(force=True)
        self.return_dispatched_result(envelope, result, log_payload)

    def schedule_retry_or_dead_letter(self, envelope: dict[str, Any], error: str) -> None:
        attempt = int(envelope.get("attempt", 0) or 0)
        next_envelope = dict(envelope)
        next_envelope["last_error"] = error
        next_envelope["last_error_utc"] = utc_now()
        if attempt < self.config.max_retries:
            next_envelope["attempt"] = attempt + 1
            next_envelope["status"] = "retrying"
            append_jsonl(self.config.export_dir / "retries.ndjson", next_envelope)
            self.metrics["retried"] = int(self.metrics.get("retried", 0) or 0) + 1
            return
        next_envelope["status"] = "dead_lettered"
        append_jsonl(self.config.export_dir / "dead_letters.ndjson", next_envelope)
        self.metrics["dead_lettered"] = int(self.metrics.get("dead_lettered", 0) or 0) + 1

    def update_reputation(self, ok: bool, kind: str, result: dict[str, Any]) -> None:
        if ok:
            delta = 0.25
            if kind == "request" and bool(result.get("choice", True)):
                delta += 0.1
            if kind == "task" and isinstance(result.get("replication"), dict) and result["replication"].get("satisfied") is True:
                delta += 0.15
            score = self.reputation.adjust_local(delta, f"{kind}_success")
        else:
            score = self.reputation.adjust_local(-0.5, f"{kind}_failure")
        self.config.reputation_score = score  # keep announced score aligned

    def try_remote_dispatch(self, envelope: dict[str, Any]) -> bool:
        if not self.config.remote_dispatch_enable:
            return False
        dispatch_hops = int(envelope.get("dispatch_hops", 0) or 0)
        if dispatch_hops >= max(1, self.config.remote_dispatch_limit):
            return False
        kind = str(envelope.get("envelope_kind") or "task")
        required_roles = envelope.get("target_roles", []) if kind == "request" else envelope.get("required_roles", [])
        if not isinstance(required_roles, list):
            required_roles = []
        body = envelope.get("request") if kind == "request" and isinstance(envelope.get("request"), dict) else {}
        if kind != "request":
            body = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
        peer = self.peer_network.select_peers(
            required_roles={str(role).lower() for role in required_roles},
            limit=1,
            exclude={self.config.node_id},
            constraints=_peer_constraints(body, envelope),
        )
        if not peer:
            self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
            return False
        selected_peer = peer[0]
        selected_peer_id = str(selected_peer.get("node_id", ""))
        scheduler_score = self.peer_network._peer_score_components(selected_peer, {str(role).lower() for role in required_roles})
        scheduler_role = str(next(iter(required_roles), "task")).lower()
        item_id = safe_id(str(envelope.get("request_id") or envelope.get("task_id") or "unknown"))
        dispatch_stats = self.reputation.record_peer_dispatch(selected_peer_id, scheduler_role, item_id)
        self.peer_network.update_peer_metadata(selected_peer_id, {"scheduler_dispatch": dispatch_stats})
        payload = dict(envelope)
        payload["dispatch_hops"] = dispatch_hops + 1
        payload["dispatched_by"] = self.config.node_id
        payload["dispatched_utc"] = utc_now()
        payload["scheduler"] = {
            "kind": "reputation_weighted",
            "selected_peer": selected_peer_id,
            "required_roles": required_roles,
            "score": scheduler_score,
            "dispatch_stats": dispatch_stats,
        }
        payload["result_return_url"] = self.peer_network.advertised_http_base_url.rstrip("/") + "/results/dispatch"
        base_url = str(selected_peer.get("http_base_url", "")).rstrip("/")
        if not base_url:
            reverted_stats = self.reputation.record_peer_result(selected_peer_id, False)
            self.peer_network.update_peer_metadata(selected_peer_id, {"scheduler_dispatch": reverted_stats})
            self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
            return False
        path = "/requests/dispatch" if kind == "request" else "/tasks/dispatch"
        raw = stable_json(payload).encode("utf-8")
        request = urllib.request.Request(
            base_url + path,
            data=raw,
            method="POST",
            headers=self.peer_network._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                ok = response.status in {200, 202}
        except (TimeoutError, OSError, urllib.error.URLError):
            ok = False
        if ok:
            self.metrics["dispatched"] = int(self.metrics.get("dispatched", 0) or 0) + 1
            self.update_envelope_status(
                envelope,
                "dispatched",
                {
                    "result_hash": "",
                    "dispatched_to": selected_peer_id,
                    "scheduler": payload["scheduler"],
                },
            )
            append_jsonl(
                self.events_path,
                {
                    "schema_version": 1,
                    "timestamp_utc": utc_now(),
                    "node_id": self.config.node_id,
                    "kind": "dispatch",
                    "item_id": item_id,
                    "target_peer": selected_peer_id,
                    "roles": required_roles,
                    "scheduler": payload["scheduler"],
                },
            )
            return True
        reverted_stats = self.reputation.record_peer_result(selected_peer_id, False)
        self.peer_network.update_peer_metadata(selected_peer_id, {"scheduler_dispatch": reverted_stats})
        self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
        return False

    def return_dispatched_result(self, envelope: dict[str, Any], result: dict[str, Any], log_payload: dict[str, Any]) -> None:
        return_url = str(envelope.get("result_return_url", "")).strip()
        origin_node_id = str(envelope.get("dispatched_by", "")).strip()
        if not return_url or not origin_node_id or origin_node_id == self.config.node_id:
            return
        item_id = str(envelope.get("request_id") or envelope.get("task_id") or "")
        if not item_id:
            return
        safe_item = safe_id(item_id)
        content_sync = self.sync_result_content_refs(return_url, result, origin_node_id)
        if content_sync["attempted"] > 0:
            result["content_return"] = content_sync
        payload = {
            "schema_version": 1,
            "item_id": safe_item,
            "envelope_kind": str(envelope.get("envelope_kind") or "task"),
            "result": result,
            "log": log_payload,
            "handled_by": self.config.node_id,
            "status": "completed" if bool(result.get("success", True)) else "failed",
        }
        raw = stable_json(payload).encode("utf-8")
        path = urlparse(return_url).path or "/results/dispatch"
        request = urllib.request.Request(
            return_url,
            data=raw,
            method="POST",
            headers=self.peer_network._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                ok = response.status in {200, 202}
        except (TimeoutError, OSError, urllib.error.URLError):
            ok = False
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "result_return",
                "item_id": safe_item,
                "target_node": origin_node_id,
                "ok": ok,
            },
        )

    def iter_result_content_refs(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            protocol = str(value.get("protocol", "")).strip().lower()
            content_id = str(value.get("content_id", "")).strip()
            if protocol == "silicium" and content_id:
                yield value
            for nested in value.values():
                yield from self.iter_result_content_refs(nested)
            return
        if isinstance(value, list):
            for nested in value:
                yield from self.iter_result_content_refs(nested)

    def sync_result_content_refs(self, return_url: str, result: dict[str, Any], owner_node_id: str) -> dict[str, Any]:
        parsed = urlparse(return_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"attempted": 0, "stored": 0, "ok": False, "refs": []}
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        seen: set[str] = set()
        report: dict[str, Any] = {"attempted": 0, "stored": 0, "ok": True, "refs": []}
        for ref in self.iter_result_content_refs(result):
            content_id = str(ref.get("content_id", "")).strip()
            if not content_id or content_id in seen:
                continue
            seen.add(content_id)
            local = self.config.export_dir / "p2p" / content_id
            if not local.exists():
                report["refs"].append({"content_id": content_id, "ok": False, "error": "local_content_missing"})
                report["ok"] = False
                continue
            data = local.read_bytes()
            path = f"/p2p/ingest?content_id={quote(content_id, safe='')}"
            request = urllib.request.Request(
                base_url + path,
                data=data,
                method="POST",
                headers=self.peer_network._signed_headers("POST", path, data, {"Content-Type": "application/octet-stream"}),
            )
            report["attempted"] += 1
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    ok = response.status == 200
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                ok = False
                error = str(exc)
            else:
                error = ""
            if ok:
                report["stored"] += 1
                ref["peer_id"] = str(owner_node_id or self.config.node_id)
            else:
                report["ok"] = False
            item = {"content_id": content_id, "ok": ok, "size_bytes": len(data)}
            if error:
                item["error"] = error[-240:]
            report["refs"].append(item)
        return report

    def ingest_dispatched_result(self, payload: dict[str, Any]) -> None:
        item_id = safe_id(str(payload.get("item_id", "")))
        if not item_id:
            raise ValueError("missing_item_id")
        result = payload.get("result")
        log_payload = payload.get("log")
        if not isinstance(result, dict) or not isinstance(log_payload, dict):
            raise ValueError("missing_result_payload")
        kind = str(payload.get("envelope_kind") or "task")
        atomic_write_json(self.config.export_dir / f"result.{item_id}.json", result)
        atomic_write_json(self.config.export_dir / f"logs.{item_id}.json", log_payload)
        source_node = str(payload.get("handled_by", result.get("node_id", "")))
        completed_ok = str(payload.get("status", "completed")) == "completed" and bool(result.get("success", True))
        dispatch_stats = self.reputation.record_peer_result(source_node, completed_ok)
        self.peer_network.update_peer_metadata(source_node, {"scheduler_dispatch": dispatch_stats})
        target_dir = self.config.export_dir / ("requests" if kind == "request" else "tasks")
        envelope_path = target_dir / f"{item_id}.json"
        current = read_json(envelope_path, {})
        if not isinstance(current, dict):
            current = {}
        current["status"] = str(payload.get("status", "completed"))
        current["handled_by"] = source_node
        current["handled_utc"] = utc_now()
        current["result_hash"] = result.get("result_hash") or result.get("input_hash", "")
        current["result_resource"] = f"resources://silicium/results/by-task/{item_id}"
        current["scheduler_dispatch"] = dispatch_stats
        atomic_write_json(envelope_path, current)
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "result_ingest",
                "item_id": item_id,
                "source_node": source_node,
                "scheduler_dispatch": dispatch_stats,
            },
        )

    def handle_task(self, envelope: dict[str, Any]) -> dict[str, Any]:
        task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
        p2p_data, p2p_meta = self.p2p.fetch(envelope.get("p2p_ref"))
        role_output = self.runtime.run_task(envelope, task, p2p_data, p2p_meta)
        output = {
            "success": True,
            "envelope_kind": "task",
            "task_id": envelope.get("task_id", ""),
            "required_roles": envelope.get("required_roles", []),
            "priority": envelope.get("priority", "normal"),
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            **role_output,
        }
        output["result_hash"] = str(role_output.get("result_hash") or sha256_json(output))
        output_ref = self.p2p.put_local(stable_json(output).encode("utf-8"))
        output["proof_ref"] = output_ref
        on_chain = self.submit_task_on_chain(envelope, task, output, output_ref)
        if on_chain:
            output["on_chain"] = on_chain
        return output

    def handle_request(self, envelope: dict[str, Any]) -> dict[str, Any]:
        request = envelope.get("request") if isinstance(envelope.get("request"), dict) else {}
        p2p_data, p2p_meta = self.p2p.fetch(envelope.get("p2p_ref"))
        request_kind = str(envelope.get("kind", "request"))
        role_response = self.runtime.run_request(envelope, request, p2p_data, p2p_meta)
        response = {
            "success": True,
            "envelope_kind": "request",
            "request_id": envelope.get("request_id", ""),
            "kind": request_kind,
            "priority": envelope.get("priority", "high"),
            "target_roles": envelope.get("target_roles", []),
            "job_id": envelope.get("job_id", ""),
            "fragment_id": envelope.get("fragment_id", ""),
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            **role_response,
        }
        response_ref = self.p2p.put_local(stable_json(response).encode("utf-8"))
        response["response_ref"] = response_ref
        on_chain = self.submit_request_on_chain(envelope, response, response_ref)
        if on_chain:
            response["on_chain"] = on_chain
        return response

    def envelope_on_chain(self, envelope: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        on_chain = envelope.get("on_chain")
        if not isinstance(on_chain, dict):
            on_chain = body.get("on_chain")
        return on_chain if isinstance(on_chain, dict) else {}

    def fetch_fragment_state(self, on_chain: dict[str, Any]) -> dict[str, Any]:
        if not self.config.solana_enable:
            return {}
        params: dict[str, Any] = {}
        if on_chain.get("fragment"):
            params["fragment"] = on_chain.get("fragment")
        else:
            params["job"] = on_chain.get("job")
            params["fragment_index"] = on_chain.get("fragment_index", on_chain.get("fragmentIndex"))
        snapshot = self.solana.call("fetch_fragment", params)
        account = snapshot.get("account")
        return account if isinstance(account, dict) else {}

    def submit_task_on_chain(
        self,
        envelope: dict[str, Any],
        task: dict[str, Any],
        output: dict[str, Any],
        output_ref: dict[str, Any],
    ) -> list[dict[str, Any]]:
        on_chain = self.envelope_on_chain(envelope, task)
        if not on_chain:
            return []

        submitted: list[dict[str, Any]] = []
        required = bool(on_chain.get("required") or envelope.get("on_chain_required"))
        roles = {str(role).lower() for role in envelope.get("required_roles", [])}
        task_kind = str(task.get("kind", "")).lower()
        proof_ref = output_ref.get("hash") or stable_json(output_ref)

        try:
            if ("storage" in roles or task_kind == "storage") and on_chain.get("job"):
                submitted.append(
                    self.solana.call(
                        "declare_storage",
                        {
                            "job": on_chain.get("job"),
                            "manifest_hash": on_chain.get("manifest_hash") or output.get("manifest_hash") or output.get("result_hash"),
                            "input_root_hash": on_chain.get("input_root_hash") or output.get("input_hash") or output.get("result_hash"),
                            "storage_ref_hash": on_chain.get("storage_ref_hash") or proof_ref,
                            "encryption_ref_hash": on_chain.get("encryption_ref_hash"),
                        },
                    )
                )

            if ("compute" in roles or task_kind == "compute") and on_chain.get("job") and on_chain.get("worker_token"):
                fragment_index = on_chain.get("fragment_index", on_chain.get("fragmentIndex"))
                if fragment_index is not None:
                    fragment_state = self.fetch_fragment_state(on_chain)
                    status = fragment_status_name(fragment_state) if fragment_state else "unknown"
                    op = "claim_and_submit_fragment"
                    if status == "claimed":
                        op = "submit_fragment_result"
                    elif status in {"submitted", "verified", "finalized", "resolved"}:
                        op = ""
                    elif bool(on_chain.get("skip_claim")):
                        op = "submit_fragment_result"
                    if op:
                        params = {
                            "job": on_chain.get("job"),
                            "fragment_index": int(fragment_index),
                            "worker_token": on_chain.get("worker_token"),
                            "result_hash": output.get("result_hash"),
                            "proof_ref": proof_ref,
                            "skip_claim": bool(on_chain.get("skip_claim")),
                        }
                        if op == "submit_fragment_result":
                            params["skip_claim"] = True
                    submitted.append(
                        self.solana.call(op, params) if op else {"ok": True, "skipped": True, "reason": "fragment_already_submitted"}
                    )

            if on_chain.get("finalize") and on_chain.get("job") and on_chain.get("escrow") and on_chain.get("client_token"):
                submitted.append(
                    self.solana.call(
                        "finalize_job",
                        {
                            "job": on_chain.get("job"),
                            "escrow": on_chain.get("escrow"),
                            "client_token": on_chain.get("client_token"),
                            "final_hash": on_chain.get("final_hash") or output.get("result_hash"),
                            "output_uri": on_chain.get("output_uri") or output_ref.get("content_id") or stable_json(output_ref),
                        },
                    )
                )
        except Exception as exc:
            if required:
                raise
            submitted.append({"ok": False, "skipped": False, "error": "optional_on_chain_failed", "details": str(exc)})

        if required and not submitted:
            raise ValueError("on_chain_required_but_no_supported_task_operation")
        return submitted

    def submit_request_on_chain(
        self,
        envelope: dict[str, Any],
        response: dict[str, Any],
        response_ref: dict[str, Any],
    ) -> list[dict[str, Any]]:
        request = envelope.get("request") if isinstance(envelope.get("request"), dict) else {}
        on_chain = self.envelope_on_chain(envelope, request)
        if not on_chain:
            return []

        submitted: list[dict[str, Any]] = []
        required = bool(on_chain.get("required") or envelope.get("on_chain_required"))
        request_kind = str(envelope.get("kind", "")).lower()
        target_roles = {str(role).lower() for role in envelope.get("target_roles", [])}
        should_vote = request_kind in {"audit", "challenge", "verify"} or bool({"audit", "verify"}.intersection(target_roles))

        try:
            if should_vote and on_chain.get("job") and on_chain.get("escrow") and on_chain.get("worker_token"):
                params = {
                    "job": on_chain.get("job"),
                    "fragment": on_chain.get("fragment"),
                    "fragment_index": on_chain.get("fragment_index", on_chain.get("fragmentIndex")),
                    "escrow": on_chain.get("escrow"),
                    "worker_token": on_chain.get("worker_token"),
                    "choice": on_chain.get("choice", request.get("choice", response.get("choice", True))),
                    "compute_worker": on_chain.get("compute_worker"),
                    "round": on_chain.get("round"),
                    "response_ref": response_ref.get("hash") or stable_json(response_ref),
                    "response_hash": response.get("input_hash"),
                }
                submitted.append(self.solana.call("vote_fragment", params))
                if on_chain.get("claim_reward"):
                    submitted.append(
                        self.solana.call(
                            "claim_verifier_reward",
                            {
                                "job": on_chain.get("job"),
                                "fragment": on_chain.get("fragment"),
                                "escrow": on_chain.get("escrow"),
                                "verifier_token": on_chain.get("verifier_token") or on_chain.get("worker_token"),
                                "round": on_chain.get("round"),
                            },
                        )
                    )
        except Exception as exc:
            if required:
                raise
            submitted.append({"ok": False, "skipped": False, "error": "optional_on_chain_failed", "details": str(exc)})

        if required and not submitted:
            raise ValueError("on_chain_required_but_no_supported_request_operation")
        return submitted

    def update_envelope_status(self, envelope: dict[str, Any], status: str, result: dict[str, Any]) -> None:
        kind = str(envelope.get("envelope_kind") or "task")
        if kind == "request":
            item_id = safe_id(str(envelope.get("request_id", "")))
            path = self.config.export_dir / "requests" / f"{item_id}.json"
        else:
            item_id = safe_id(str(envelope.get("task_id", "")))
            path = self.config.export_dir / "tasks" / f"{item_id}.json"
        current = read_json(path, envelope)
        if not isinstance(current, dict):
            current = envelope
        current["status"] = status
        current["handled_by"] = self.config.node_id
        current["handled_utc"] = utc_now()
        current["result_hash"] = result.get("result_hash") or result.get("input_hash", "")
        current["result_resource"] = f"resources://silicium/results/by-task/{item_id}"
        if result.get("dispatched_to"):
            current["dispatched_to"] = result.get("dispatched_to")
        if isinstance(result.get("scheduler"), dict):
            current["scheduler"] = result.get("scheduler")
        atomic_write_json(path, current)


def parse_roles(raw: str) -> set[str]:
    roles = {item.strip().lower() for item in raw.split(",") if item.strip()}
    if not roles:
        roles = {"compute", "verify", "storage", "audit", "resource"}
    invalid = roles - NETWORK_ROLES
    if invalid:
        raise ValueError("unsupported roles: " + ",".join(sorted(invalid)))
    return roles


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="network_node")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--world", action="store_true", default=os.environ.get("SILICIUM_WORLD_MODE", "0") == "1")
    parser.add_argument("--world-name", default=os.environ.get("SILICIUM_WORLD_NAME", ""))
    parser.add_argument("--world-seeds", default=os.environ.get("SILICIUM_WORLD_SEEDS", ""))
    parser.add_argument("--roles", default=os.environ.get("SILICIUM_NODE_ROLES", "compute,verify,storage,audit,resource"))
    parser.add_argument("--node-id", default=os.environ.get("SILICIUM_NODE_ID", "node-" + uuid.uuid4().hex[:8]))
    parser.add_argument("--idle-ms", type=int, default=int(os.environ.get("SILICIUM_NODE_IDLE_MS", "250")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-items", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_ITEMS", "0")))
    parser.add_argument("--p2p-gateway", default=os.environ.get("SILICIUM_P2P_GATEWAY", "http://127.0.0.1:5001"))
    parser.add_argument("--state-dir", default="")
    parser.add_argument("--solana-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_ENABLE", "0") == "1")
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument(
        "--solana-program-id",
        default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA"),
    )
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.path.expanduser("~/.config/solana/id.json")))
    parser.add_argument("--solana-bridge", default=os.environ.get("SILICIUM_SOLANA_BRIDGE", str(Path(__file__).with_name("solana_layer_bridge.cjs"))))
    parser.add_argument("--solana-timeout-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_TIMEOUT_S", "45")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_RETRIES", "2")))
    parser.add_argument("--worker-binary", default=os.environ.get("SILICIUM_WORKER_BINARY", str(Path("experimental/worker/worker"))))
    parser.add_argument("--worker-mode", default=os.environ.get("SILICIUM_WORKER_MODE", "emu"))
    parser.add_argument("--bootstrap-worker", action="store_true", default=os.environ.get("SILICIUM_BOOTSTRAP_WORKER", "0") == "1")
    parser.add_argument("--gossip-enable", action="store_true", default=os.environ.get("SILICIUM_GOSSIP_ENABLE", "0") == "1")
    parser.add_argument("--gossip-bind", default=os.environ.get("SILICIUM_GOSSIP_BIND", "127.0.0.1"))
    parser.add_argument("--gossip-port", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_PORT", "0")))
    parser.add_argument("--peer-http-bind", default=os.environ.get("SILICIUM_PEER_HTTP_BIND", "127.0.0.1"))
    parser.add_argument("--peer-http-port", type=int, default=int(os.environ.get("SILICIUM_PEER_HTTP_PORT", "0")))
    parser.add_argument("--peer-advertise-host", default=os.environ.get("SILICIUM_PEER_ADVERTISE_HOST", ""))
    parser.add_argument("--peer-advertise-port", type=int, default=int(os.environ.get("SILICIUM_PEER_ADVERTISE_PORT", "0")))
    parser.add_argument("--gossip-advertise-host", default=os.environ.get("SILICIUM_GOSSIP_ADVERTISE_HOST", ""))
    parser.add_argument("--gossip-advertise-port", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_ADVERTISE_PORT", "0")))
    parser.add_argument("--seed-peers", default=os.environ.get("SILICIUM_SEED_PEERS", ""))
    parser.add_argument("--mesh-key", default=os.environ.get("SILICIUM_MESH_KEY", ""))
    parser.add_argument("--peer-sync-interval-s", type=int, default=int(os.environ.get("SILICIUM_PEER_SYNC_INTERVAL_S", "15")))
    parser.add_argument("--peer-event-limit", type=int, default=int(os.environ.get("SILICIUM_PEER_EVENT_LIMIT", "128")))
    parser.add_argument("--peer-stale-after-s", type=int, default=int(os.environ.get("SILICIUM_PEER_STALE_AFTER_S", "300")))
    parser.add_argument("--relay-enable", action="store_true", default=os.environ.get("SILICIUM_RELAY_ENABLE", "0") == "1")
    parser.add_argument("--relay-hops", type=int, default=int(os.environ.get("SILICIUM_RELAY_HOPS", "2")))
    parser.add_argument("--identity-key-path", default=os.environ.get("SILICIUM_IDENTITY_KEY_PATH", ""))
    parser.add_argument("--reputation-score", type=float, default=float(os.environ.get("SILICIUM_REPUTATION_SCORE", "0")))
    parser.add_argument("--replication-factor", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_FACTOR", "0")))
    parser.add_argument("--replication-quorum", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_QUORUM", "0")))
    parser.add_argument("--discovery-seeds", default=os.environ.get("SILICIUM_DISCOVERY_SEEDS", ""))
    parser.add_argument("--discovery-sync-interval-s", type=int, default=int(os.environ.get("SILICIUM_DISCOVERY_SYNC_INTERVAL_S", "30")))
    parser.add_argument("--remote-dispatch-enable", action="store_true", default=os.environ.get("SILICIUM_REMOTE_DISPATCH_ENABLE", "0") == "1")
    parser.add_argument("--remote-dispatch-limit", type=int, default=int(os.environ.get("SILICIUM_REMOTE_DISPATCH_LIMIT", "3")))
    parser.add_argument("--pull-tasks-enable", action="store_true", default=os.environ.get("SILICIUM_PULL_TASKS_ENABLE", "0") == "1")
    parser.add_argument("--pull-tasks-interval-s", type=int, default=int(os.environ.get("SILICIUM_PULL_TASKS_INTERVAL_S", "2")))
    parser.add_argument("--nat-punch-enable", action="store_true", default=os.environ.get("SILICIUM_NAT_PUNCH_ENABLE", "0") == "1")
    parser.add_argument("--solana-reputation-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_REPUTATION_ENABLE", "0") == "1")
    parser.add_argument("--solana-reputation-refresh-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_REPUTATION_REFRESH_S", "60")))
    parser.add_argument("--scheduler-onchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_ONCHAIN_WEIGHT", "10")))
    parser.add_argument("--scheduler-offchain-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_OFFCHAIN_WEIGHT", "1")))
    parser.add_argument("--scheduler-capacity-weight", type=float, default=float(os.environ.get("SILICIUM_SCHEDULER_CAPACITY_WEIGHT", "0.01")))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if bool(args.world):
        advertise_host = guess_world_advertise_host()
        if not str(args.gossip_bind).strip() or str(args.gossip_bind).strip() == "127.0.0.1":
            args.gossip_bind = "0.0.0.0"
        if not str(args.peer_http_bind).strip() or str(args.peer_http_bind).strip() == "127.0.0.1":
            args.peer_http_bind = "0.0.0.0"
        if int(args.gossip_port or 0) <= 0:
            args.gossip_port = WORLD_DEFAULT_GOSSIP_PORT
        if int(args.peer_http_port or 0) <= 0:
            args.peer_http_port = WORLD_DEFAULT_PEER_HTTP_PORT
        if not str(args.peer_advertise_host).strip():
            args.peer_advertise_host = advertise_host
        if not str(args.gossip_advertise_host).strip():
            args.gossip_advertise_host = advertise_host
        if int(args.peer_advertise_port or 0) <= 0:
            args.peer_advertise_port = int(args.peer_http_port)
        if int(args.gossip_advertise_port or 0) <= 0:
            args.gossip_advertise_port = int(args.gossip_port)
        if not str(args.mesh_key).strip():
            args.mesh_key = derive_world_mesh_key(str(args.world_name))
        args.discovery_seeds = merge_csv(str(args.discovery_seeds), str(args.world_seeds), os.environ.get("SILICIUM_WORLD_SEEDS", ""))
        args.gossip_enable = True
        args.relay_enable = True
        args.remote_dispatch_enable = True
        args.nat_punch_enable = True
        args.solana_reputation_enable = True
        args.peer_sync_interval_s = max(int(args.peer_sync_interval_s or 0), WORLD_DEFAULT_PEER_SYNC_INTERVAL_S)
        args.discovery_sync_interval_s = max(int(args.discovery_sync_interval_s or 0), WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S)
        if not str(args.identity_key_path).strip():
            args.identity_key_path = str(Path(".silicium") / "world-identities" / safe_id(str(args.node_id)) / "ed25519.pem")
    export_dir = Path(args.export_dir).expanduser().resolve()
    state_dir = Path(args.state_dir).expanduser().resolve() if args.state_dir else export_dir / "node-state" / safe_id(args.node_id)
    config = NodeConfig(
        export_dir=export_dir,
        roles=parse_roles(args.roles),
        node_id=safe_id(args.node_id),
        idle_ms=int(args.idle_ms),
        once=bool(args.once),
        max_items=int(args.max_items),
        p2p_gateway=str(args.p2p_gateway),
        state_dir=state_dir,
        solana_enable=bool(args.solana_enable),
        solana_rpc=str(args.solana_rpc),
        solana_program_id=str(args.solana_program_id),
        solana_wallet=str(args.solana_wallet),
        solana_bridge=Path(args.solana_bridge).expanduser().resolve(),
        solana_timeout_s=int(args.solana_timeout_s),
        max_retries=max(0, int(args.max_retries)),
        worker_binary=str(args.worker_binary),
        worker_mode=str(args.worker_mode),
        bootstrap_worker=bool(args.bootstrap_worker),
        gossip_enable=bool(args.gossip_enable),
        gossip_bind=str(args.gossip_bind),
        gossip_port=int(args.gossip_port),
        peer_http_bind=str(args.peer_http_bind),
        peer_http_port=int(args.peer_http_port),
        peer_advertise_host=str(args.peer_advertise_host),
        peer_advertise_port=int(args.peer_advertise_port),
        gossip_advertise_host=str(args.gossip_advertise_host),
        gossip_advertise_port=int(args.gossip_advertise_port),
        seed_peers=[item.strip() for item in str(args.seed_peers).split(",") if item.strip()],
        mesh_key=str(args.mesh_key),
        peer_sync_interval_s=max(0, int(args.peer_sync_interval_s)),
        peer_event_limit=max(1, int(args.peer_event_limit)),
        peer_stale_after_s=max(0, int(args.peer_stale_after_s)),
        relay_enable=bool(args.relay_enable),
        relay_hops=max(1, int(args.relay_hops)),
        identity_key_path=str(args.identity_key_path),
        reputation_score=float(args.reputation_score),
        replication_factor=max(0, int(args.replication_factor)),
        replication_quorum=max(0, int(args.replication_quorum)),
        discovery_seeds=[item.strip() for item in str(args.discovery_seeds).split(",") if item.strip()],
        discovery_sync_interval_s=max(0, int(args.discovery_sync_interval_s)),
        remote_dispatch_enable=bool(args.remote_dispatch_enable),
        remote_dispatch_limit=max(1, int(args.remote_dispatch_limit)),
        pull_tasks_enable=bool(args.pull_tasks_enable),
        pull_tasks_interval_s=max(1, int(args.pull_tasks_interval_s)),
        nat_punch_enable=bool(args.nat_punch_enable),
        solana_reputation_enable=bool(args.solana_reputation_enable),
        solana_reputation_refresh_s=max(1, int(args.solana_reputation_refresh_s)),
        scheduler_onchain_weight=float(args.scheduler_onchain_weight),
        scheduler_offchain_weight=float(args.scheduler_offchain_weight),
        scheduler_capacity_weight=float(args.scheduler_capacity_weight),
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    NetworkNode(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
