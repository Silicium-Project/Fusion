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
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, unquote, urlparse


DEFAULT_EXPORT_DIR = Path(".silicium/mcp/export")
NETWORK_ROLES = frozenset({"compute", "verify", "storage", "audit", "resource"})
REQUEST_ROLES = frozenset({"audit", "resource", "verify", "storage", "compute"})


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.:-" else "_" for ch in value.strip())
    return cleaned or uuid.uuid4().hex


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(stable_json(value).encode("utf-8"))


def fragment_status_name(fragment_account: dict[str, Any] | Any) -> str:
    status = fragment_account.get("status") if isinstance(fragment_account, dict) else getattr(fragment_account, "status", None)
    if isinstance(status, dict) and status:
        return str(next(iter(status.keys())))
    return str(status or "unknown")


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
    tmp.replace(path)


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


class NodeIdentity:
    def __init__(self, config: NodeConfig) -> None:
        default_key = config.state_dir / "peer_identity_ed25519.pem"
        self.private_key_path = Path(config.identity_key_path).expanduser() if str(config.identity_key_path).strip() else default_key
        self.public_key_path = self.private_key_path.with_suffix(".pub.pem")
        self.private_key_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_keypair()
        public_pem = self.public_key_path.read_bytes()
        self.public_key_b64 = base64.b64encode(public_pem).decode("ascii")
        self.identity_id = sha256_bytes(public_pem)[:32]

    def sign_bytes(self, data: bytes) -> str:
        with tempfile.TemporaryDirectory(prefix="silicium-sign-") as tmpdir:
            msg_path = Path(tmpdir) / "message.bin"
            sig_path = Path(tmpdir) / "signature.bin"
            msg_path.write_bytes(data)
            completed = subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(self.private_key_path), "-in", str(msg_path), "-out", str(sig_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"openssl_sign_failed:{completed.stderr.strip()}")
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
        identity_id = sha256_bytes(public_pem)[:32]
        with tempfile.TemporaryDirectory(prefix=f"silicium-verify-{identity_id}-") as tmpdir:
            msg_path = Path(tmpdir) / "message.bin"
            sig_path = Path(tmpdir) / "signature.bin"
            pub_path = Path(tmpdir) / "public.pem"
            msg_path.write_bytes(data)
            sig_path.write_bytes(signature)
            pub_path.write_bytes(public_pem)
            completed = subprocess.run(
                ["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(pub_path), "-in", str(msg_path), "-sigfile", str(sig_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            return completed.returncode == 0

    @staticmethod
    def identity_id_for_key(public_key_b64: str) -> str:
        try:
            public_pem = base64.b64decode(public_key_b64.encode("ascii"))
        except Exception:
            return ""
        return sha256_bytes(public_pem)[:32]

    def _ensure_keypair(self) -> None:
        if not self.private_key_path.exists():
            completed = subprocess.run(
                ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(self.private_key_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"openssl_identity_generate_failed:{completed.stderr.strip()}")
        if not self.public_key_path.exists():
            completed = subprocess.run(
                ["openssl", "pkey", "-in", str(self.private_key_path), "-pubout", "-out", str(self.public_key_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"openssl_identity_pubout_failed:{completed.stderr.strip()}")


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
        self._peers: dict[str, dict[str, Any]] = {}
        self._seen_events: set[str] = set()
        self._lock = threading.Lock()
        self._http_server: http.server.ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._udp_socket: socket.socket | None = None
        self._udp_thread: threading.Thread | None = None
        self._sync_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.http_base_url = ""
        self.advertised_http_base_url = ""
        self.gossip_target = ""
        self.mesh_post_url = ""
        self.local_capacity = build_capacity_snapshot(config)
        self.local_reputation_score = float(config.reputation_score)

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
        return payload

    def set_local_profile(self, *, capacity: dict[str, Any] | None = None, reputation_score: float | None = None) -> None:
        if capacity is not None:
            self.local_capacity = capacity
        if reputation_score is not None:
            self.local_reputation_score = float(reputation_score)
        self._record_self_peer()

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
                "updated_utc": str(message.get("timestamp_utc", utc_now())),
                "last_seen_unix": int(time.time()),
                "self": node_id == self.node_id,
            }
            changed = any(current.get(key) != value for key, value in merged.items() if key not in {"updated_utc", "last_seen_unix"})
            current.update(merged)
            self._peers[node_id] = current
        self.peers_snapshot()
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
        except urllib.error.URLError:
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
        except urllib.error.URLError:
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
            except urllib.error.URLError:
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
    ) -> dict[str, Any]:
        peers = self.select_peers(required_roles=set(required_roles or {"storage"}), limit=max(0, target_factor), exclude={self.node_id})
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

    def select_peers(
        self,
        *,
        required_roles: set[str] | None = None,
        limit: int = 0,
        require_relay: bool = False,
        exclude: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        exclude_ids = exclude or set()
        required_roles = required_roles or set()
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
            candidates.append(peer)
        candidates.sort(key=self._peer_score, reverse=True)
        if limit > 0:
            return candidates[:limit]
        return candidates

    def _peer_score(self, peer: dict[str, Any]) -> tuple[float, float, float]:
        capacity = peer.get("capacity", {}) if isinstance(peer.get("capacity"), dict) else {}
        reputation = float(peer.get("reputation_score", 0.0) or 0.0)
        cpu = float(capacity.get("cpu_count", 0) or 0)
        disk_free = float(capacity.get("disk_free_bytes", 0) or 0)
        return (reputation, cpu, disk_free)

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
        except urllib.error.URLError:
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
        targets = self._sync_targets()
        for base_url in targets:
            self._sync_peer_table(base_url)
            self._sync_recent_events(base_url)

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


class NetworkNode:
    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.state = QueueState(config.state_dir)
        self.peer_network = PeerNetwork(config, config.export_dir)
        self.p2p = P2PClient(config.p2p_gateway, config.export_dir, self.peer_network)
        self.solana = SolanaBridge(config)
        self.runtime = RoleRuntime(config, self.p2p)
        self.events_path = config.export_dir / "node.events.ndjson"
        self.heartbeat_path = config.export_dir / f"node.{safe_id(config.node_id)}.heartbeat.json"
        self.metrics_path = config.export_dir / f"node.{safe_id(config.node_id)}.metrics.json"
        self.metrics = read_json(self.metrics_path, {"schema_version": 1, "handled": 0, "failed": 0, "retried": 0, "dead_lettered": 0})
        self.peer_network.set_local_profile(capacity=self.runtime.capacity(), reputation_score=self.config.reputation_score)

    def run(self) -> None:
        self.peer_network.start()
        try:
            self.bootstrap()
            while True:
                self.write_heartbeat()
                handled = self.sweep()
                self.state.save()
                self.write_metrics()
                if self.config.once:
                    return
                if handled == 0:
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

    def write_heartbeat(self) -> None:
        capacity = self.runtime.capacity()
        self.peer_network.set_local_profile(capacity=capacity, reputation_score=self.config.reputation_score)
        atomic_write_json(
            self.heartbeat_path,
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "timestamp_utc": utc_now(),
                "roles": sorted(self.config.roles),
                "capacity": capacity,
                "reputation_score": self.config.reputation_score,
                "peer_http_base_url": self.peer_network.http_base_url,
                "peer_public_base_url": self.peer_network.advertised_http_base_url,
                "peer_count": int(self.peer_network.peers_snapshot().get("count", 0)),
                "gossip_enabled": self.config.gossip_enable,
                "peer_sync_interval_s": self.config.peer_sync_interval_s,
                "mesh_auth_enabled": bool(self.config.mesh_key),
                "identity_id": self.peer_network.identity.identity_id,
                "relay_enabled": self.config.relay_enable,
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
        atomic_write_json(self.config.export_dir / f"result.{safe_item}.json", result)
        atomic_write_json(
            self.config.export_dir / f"logs.{safe_item}.json",
            {"schema_version": 1, "item_id": safe_item, "ok": ok, "error": error, "duration_ms": duration_ms},
        )
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
        default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "HyXT83SzHsEPxNZ5zQPvkLwQ7JwFHh2veAE5PuGUgoiQ"),
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
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
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    NetworkNode(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
