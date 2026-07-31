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
import heapq
import hashlib
import hmac
import http.server
import importlib.util
import ipaddress
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

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from tools.direct_transport import DirectTransportBackend, IceDirectTransport, NativeLightDirectTransport
from tools.resource_intelligence import DualMemoryBayes, build_resource_profile, resource_baselines
from tools.runtime_telemetry import RuntimeTelemetrySampler
from workloads.raytracer.raytracer_workload import (
    build_verification_milestones,
    ppm_pixel_sha256,
    run_raytracer,
    scene_resolution,
    validate_fragment_ppm,
    verify_probabilistic_milestones,
)


DEFAULT_EXPORT_DIR = Path(".silicium/mcp/export")
NETWORK_ROLES = frozenset({"compute", "verify", "storage", "audit", "resource"})
REQUEST_ROLES = frozenset({"audit", "resource", "verify", "storage", "compute"})
WORLD_DEFAULT_GOSSIP_PORT = 46000
WORLD_DEFAULT_PEER_HTTP_PORT = 46001
WORLD_DEFAULT_PEER_SYNC_INTERVAL_S = 10
WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S = 15
DEFAULT_PUBLIC_STUN_SERVER = "stun.l.google.com:19302"
ATOMIC_WRITE_LOCK = threading.Lock()
TERMINAL_TASK_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "dead_lettered",
        "cancelled",
        "canceled",
        "expired",
        "finalized",
        "resolved",
    }
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def task_status(value: Any, default: str = "queued") -> str:
    return str(value or default).strip().lower()


def task_status_is_terminal(value: Any) -> bool:
    return task_status(value) in TERMINAL_TASK_STATUSES


def safe_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.:-" else "_" for ch in value.strip())
    return cleaned or uuid.uuid4().hex


def optional_peer_id(value: Any) -> str:
    raw = str(value or "").strip()
    return safe_id(raw) if raw else ""


def safe_path_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in value.strip())
    return cleaned or uuid.uuid4().hex


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


def apply_nat_traversal_defaults(args: argparse.Namespace) -> argparse.Namespace:
    backend = str(getattr(args, "p2p_direct_transport_backend", "auto") or "auto").strip().lower()
    stun_server = str(getattr(args, "p2p_stun_server", "") or "").strip()
    if bool(getattr(args, "nat_punch_enable", False)) and backend not in {"native", "native-light", "native_light"} and not stun_server:
        args.p2p_stun_server = DEFAULT_PUBLIC_STUN_SERVER
    return args


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
    with ATOMIC_WRITE_LOCK:
        for attempt in range(20):
            try:
                tmp.replace(path)
                return
            except PermissionError:
                if attempt >= 19:
                    raise
                time.sleep(0.05 * float(attempt + 1))


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n")


def emit_rpc_event(export_dir: Path, event: str, item_id: str, **details: Any) -> None:
    """Persist control-plane events for the RPC PUB bridge.

    Tile bytes deliberately never enter this journal: consumers receive only
    the content-addressed result reference and fetch it over the data plane.
    """
    append_jsonl(
        export_dir / "rpc.events.ndjson",
        {
            "schema_version": 1,
            "event": event,
            "item_id": safe_id(item_id),
            "timestamp_utc": utc_now(),
            **details,
        },
    )


def ingest_content_blobs(export_dir: Path, payload: dict[str, Any]) -> list[str]:
    stored: list[str] = []
    total_bytes = 0
    content_blobs = payload.get("content_blobs", [])
    if not isinstance(content_blobs, list):
        return stored
    p2p_dir = export_dir / "p2p"
    for blob in content_blobs:
        if not isinstance(blob, dict):
            continue
        content_id = str(blob.get("content_id", "")).strip().lower()
        encoded = str(blob.get("data_b64", ""))
        if len(content_id) != 64 or any(char not in "0123456789abcdef" for char in content_id):
            continue
        try:
            content = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            continue
        if total_bytes + len(content) > 16 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != content_id:
            continue
        p2p_dir.mkdir(parents=True, exist_ok=True)
        target = p2p_dir / content_id
        if not target.exists():
            target.write_bytes(content)
        stored.append(content_id)
        total_bytes += len(content)
    return stored


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
    peer_advertise_url: str
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
    identity_dev_mesh_auth: bool
    reputation_score: float
    replication_factor: int
    replication_quorum: int
    discovery_seeds: list[str]
    discovery_sync_interval_s: int
    remote_dispatch_enable: bool
    short_half_life_s: float
    long_half_life_s: float
    remote_dispatch_limit: int
    nat_punch_enable: bool
    p2p_candidate_ttl_s: int
    p2p_candidate_refresh_s: int
    p2p_session_ttl_s: int
    p2p_punch_retry_count: int
    p2p_punch_interval_ms: int
    p2p_session_timeout_ms: int
    p2p_direct_transport_backend: str
    p2p_stun_server: str
    p2p_turn_server: str
    p2p_turn_username: str
    p2p_turn_password: str
    p2p_turn_transport: str
    solana_reputation_enable: bool
    solana_reputation_refresh_s: int
    scheduler_onchain_weight: float
    scheduler_offchain_weight: float
    scheduler_capacity_weight: float
    world: bool = False
    pull_tasks_enable: bool = False
    pull_tasks_interval_s: float = 1.0
    app_version: str = "unknown"
    release_channel: str = "dev"
    release_build: str = ""
    gossip_max_hops: int = 8


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
        "resource_profile": build_resource_profile(config.export_dir),
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
    def __init__(self, config: NodeConfig) -> None:
        default_key = config.state_dir / "peer_identity_ed25519.pem"
        self.private_key_path = Path(config.identity_key_path).expanduser() if str(config.identity_key_path).strip() else default_key
        self.public_key_path = self.private_key_path.with_suffix(".pub.pem")
        self.private_key_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_keypair()
        self._harden_private_key_permissions()
        public_pem = self.public_key_path.read_bytes()
        self._private_key = serialization.load_pem_private_key(
            self.private_key_path.read_bytes(),
            password=None,
        )
        if not isinstance(self._private_key, Ed25519PrivateKey):
            raise RuntimeError("identity_private_key_is_not_ed25519")
        self.public_key_b64 = base64.b64encode(public_pem).decode("ascii")
        self.identity_id = sha256_bytes(public_pem)[:32]

    def sign_bytes(self, data: bytes) -> str:
        return self._private_key.sign(data).hex()

    @staticmethod
    def verify_bytes(data: bytes, signature_hex: str, public_key_b64: str) -> bool:
        if not signature_hex or not public_key_b64:
            return False
        try:
            public_pem = base64.b64decode(public_key_b64.encode("ascii"))
            signature = bytes.fromhex(signature_hex)
            public_key = serialization.load_pem_public_key(public_pem)
            if not isinstance(public_key, Ed25519PublicKey):
                return False
            public_key.verify(signature, data)
            return True
        except Exception:
            return False

    @staticmethod
    def identity_id_for_key(public_key_b64: str) -> str:
        try:
            public_pem = base64.b64decode(public_key_b64.encode("ascii"))
        except Exception:
            return ""
        return sha256_bytes(public_pem)[:32]

    def _ensure_keypair(self) -> None:
        if self.public_key_path.exists():
            try:
                legacy_marker = self.public_key_path.read_text(encoding="utf-8").startswith("SILICIUM-HMAC-SHA256:")
            except OSError:
                legacy_marker = False
            if legacy_marker:
                for path in (self.private_key_path, self.public_key_path):
                    if path.exists():
                        backup = path.with_name(path.name + ".legacy-hmac")
                        try:
                            path.replace(backup)
                        except OSError:
                            path.unlink(missing_ok=True)
        if not self.private_key_path.exists():
            private_key = Ed25519PrivateKey.generate()
            self.private_key_path.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        if not self.public_key_path.exists():
            private_key = serialization.load_pem_private_key(
                self.private_key_path.read_bytes(),
                password=None,
            )
            if not isinstance(private_key, Ed25519PrivateKey):
                raise RuntimeError("identity_private_key_is_not_ed25519")
            self.public_key_path.write_bytes(
                private_key.public_key().public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

    def _harden_private_key_permissions(self) -> None:
        if os.name == "nt":
            return
        try:
            os.chmod(self.private_key_path, 0o600)
        except OSError:
            pass


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
    def __init__(
        self,
        path: Path,
        initial_score: float = 0.0,
        resource_profile: Mapping[str, Any] | None = None,
        short_half_life_s: float | None = None,
        long_half_life_s: float | None = None,
    ) -> None:
        self._path = path
        self._lock = threading.Lock()
        self.short_half_life_s = short_half_life_s
        self.long_half_life_s = long_half_life_s
        loaded = read_json(path, {})
        self._payload = loaded if isinstance(loaded, dict) else {}
        self._payload["schema_version"] = max(2, int(self._payload.get("schema_version", 1) or 1))
        self._payload.setdefault("local_score", float(initial_score))
        self._payload.setdefault("peer_scores", {})
        self._payload.setdefault("history", [])
        self._payload.setdefault(
            "resource_memory",
            DualMemoryBayes(
                baselines=resource_baselines(resource_profile),
                short_half_life_s=self.short_half_life_s,
                long_half_life_s=self.long_half_life_s,
            ).export_state(),
        )
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

    def observe_resource(
        self,
        dimension: str,
        success: bool,
        *,
        weight: float = 1.0,
        event_class: str = "verified",
    ) -> dict[str, Any]:
        with self._lock:
            model = DualMemoryBayes(
                self._payload.get("resource_memory"),
                short_half_life_s=self.short_half_life_s,
                long_half_life_s=self.long_half_life_s,
            )
            model.observe(dimension, success, weight=weight, event_class=event_class)
            self._payload["resource_memory"] = model.export_state()
            snapshot = model.snapshot()
        self.save()
        return snapshot

    def observe_uptime(
        self,
        uptime_seconds: float,
        corroborated_peer_count: int = 1,
        *,
        self_reported_only: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            model = DualMemoryBayes(
                self._payload.get("resource_memory"),
                short_half_life_s=self.short_half_life_s,
                long_half_life_s=self.long_half_life_s,
            )
            model.observe_uptime(uptime_seconds, corroborated_peer_count, self_reported_only=self_reported_only)
            self._payload["resource_memory"] = model.export_state()
            snapshot = model.snapshot()
        self.save()
        return snapshot

    def resource_snapshot(self) -> dict[str, Any]:
        with self._lock:
            model = DualMemoryBayes(
                self._payload.get("resource_memory"),
                short_half_life_s=self.short_half_life_s,
                long_half_life_s=self.long_half_life_s,
            )
        return model.snapshot()

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

        # Results retain a local file reference for the producing node and a
        # portable content-addressed shared_ref. Prefer the latter whenever
        # this node has already received the artifact from the return path.
        shared_ref = p2p_ref.get("shared_ref")
        if isinstance(shared_ref, dict):
            shared_id = str(shared_ref.get("content_id", "")).strip().lower()
            shared_path = self.export_dir / "p2p" / shared_id
            if len(shared_id) == 64 and shared_path.exists():
                data = shared_path.read_bytes()
                return data, {"source": "local-shared-cache", "content_id": shared_id, "size_bytes": len(data)}

        protocol = str(p2p_ref.get("protocol", "ipfs")).lower()
        content_id = str(p2p_ref.get("content_id") or p2p_ref.get("cid") or p2p_ref.get("url") or "").strip()
        if not content_id:
            raise ValueError("missing_p2p_content_id")

        if protocol == "file":
            path = Path(content_id).expanduser()
            try:
                data = path.read_bytes()
            except FileNotFoundError:
                # put_local embeds an absolute path that is only valid on the
                # producing node. Cross-node consumers (verify handoff, pin,
                # reassembly) must follow shared_ref over the mesh instead.
                if isinstance(shared_ref, dict) and str(shared_ref.get("protocol", "")).lower() == "silicium":
                    return self.fetch(shared_ref)
                raise
            return data, {"source": "file", "path": str(path), "size_bytes": len(data)}

        if protocol == "silicium":
            if self.peer_network is None:
                raise ValueError("peer_network_not_configured")
            local_path = self.export_dir / "p2p" / content_id.lower()
            if len(content_id) == 64 and local_path.is_file():
                data = local_path.read_bytes()
                if sha256_bytes(data) == content_id.lower():
                    return data, {
                        "source": "local-silicium-cache",
                        "content_id": content_id.lower(),
                        "size_bytes": len(data),
                    }
            data, peer_meta = self.peer_network.fetch_content(content_id, str(p2p_ref.get("peer_id", "")).strip())
            # Scene/spec content is reused by every tile of a render. Cache a
            # verified fetch locally so subsequent tasks do not pay another
            # HTTPS/ICE handshake to the orchestrator.
            if len(content_id) == 64 and sha256_bytes(data) == content_id.lower():
                local_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = local_path.with_name(f".{content_id}.tmp-{os.getpid()}")
                temporary.write_bytes(data)
                temporary.replace(local_path)
            meta = {
                "source": peer_meta.get("source", "silicium-peer"),
                "content_id": content_id,
                "peer_id": peer_meta.get("node_id", ""),
                "peer_url": peer_meta.get("http_base_url", ""),
                "size_bytes": len(data),
            }
            if peer_meta.get("transport_backend"):
                meta["transport_backend"] = peer_meta["transport_backend"]
            if peer_meta.get("transport_route"):
                meta["transport_route"] = peer_meta["transport_route"]
            if peer_meta.get("session_id"):
                meta["session_id"] = peer_meta["session_id"]
            if peer_meta.get("relayed_via"):
                meta["relayed_via"] = peer_meta.get("relayed_via", "")
            if isinstance(peer_meta.get("path_attestation"), dict):
                meta["path_attestation"] = peer_meta["path_attestation"]
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
                # Availability gossip is advisory.  Never make the worker
                # wait for unreachable/NATed peers before returning a render
                # result; the anti-entropy loop will retry the announcement.
                background=True,
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
        self._cancel_event = threading.Event()
        self._cancel_reason = ""

    def begin_task(self) -> None:
        self._cancel_reason = ""
        self._cancel_event.clear()

    def cancel_task(self, reason: str) -> None:
        self._cancel_reason = str(reason or "task cancelled")
        self._cancel_event.set()

    def run_process(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + max(1, timeout)
        while True:
            if self._cancel_event.wait(0.2):
                process.kill()
                stdout, stderr = process.communicate()
                raise RuntimeError(f"task_cancelled:{self._cancel_reason}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                stdout, stderr = process.communicate()
                raise RuntimeError(f"task_timeout:{timeout}s:{stderr[-2048:]}")
            try:
                stdout, stderr = process.communicate(timeout=min(0.5, remaining))
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue

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
        if str(task.get("workload", "")).strip().lower() == "calcul/rendering/raytracer-fragment":
            return self.run_raytracer_fragment(task, p2p_data, p2p_meta)
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

    def run_raytracer_fragment(self, task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        timings_ms: dict[str, int] = {}
        try:
            spec = json.loads(p2p_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"raytracer_fragment_spec_invalid:{exc}") from exc
        if not isinstance(spec, dict):
            raise RuntimeError("raytracer_fragment_spec_invalid")
        scene_ref = task.get("scene_p2p_ref") or spec.get("scene_p2p_ref")
        if not isinstance(scene_ref, dict):
            raise RuntimeError("raytracer_scene_ref_missing")
        phase_started = time.perf_counter()
        scene_bytes, scene_meta = self.p2p.fetch(scene_ref)
        timings_ms["scene_fetch"] = int((time.perf_counter() - phase_started) * 1000)
        with tempfile.TemporaryDirectory(prefix="silicium-raytracer-fragment-") as temp_dir:
            temp_path = Path(temp_dir)
            scene_path = temp_path / "scene.cfg"
            output_path = temp_path / "fragment.ppm"
            phase_started = time.perf_counter()
            scene_path.write_bytes(scene_bytes)
            timings_ms["scene_write"] = int((time.perf_counter() - phase_started) * 1000)
            x_start = int(task.get("x_start", spec.get("x_start", 0)) or 0)
            x_end = int(task.get("x_end", spec.get("x_end", 0)) or 0)
            if x_end <= x_start:
                x_end = scene_resolution(scene_path)[0]
            y_start = int(task.get("y_start", spec.get("y_start", 0)) or 0)
            y_end = int(task.get("y_end", spec.get("y_end", 0)) or 0)
            phase_started = time.perf_counter()
            # The Rust renderer serializes a progress-file update from its
            # hot pixel loop.  On Windows this changes a 20 ms tile into a
            # ~900 ms tile.  The node monitor still exposes queue/execution
            # phases; completion is the meaningful granularity for a tile.
            rendered = run_raytracer(
                scene_path,
                output_path,
                int(task.get("timeout_s", 300) or 300),
                y_start,
                y_end,
                x_start,
                x_end,
            )
            timings_ms["renderer"] = int((time.perf_counter() - phase_started) * 1000)
            output = output_path.read_bytes()
        try:
            validate_fragment_ppm(output, task_id=task.get("task_id", ""))
        except RuntimeError as exc:
            raise RuntimeError(f"raytracer_fragment_invalid_ppm:{exc}") from exc
        phase_started = time.perf_counter()
        output_ref = self.p2p.put_local(output)
        timings_ms["output_store"] = int((time.perf_counter() - phase_started) * 1000)
        result_hash = sha256_bytes(output)
        phase_started = time.perf_counter()
        milestone_manifest = build_verification_milestones(
            output,
            int(task.get("y_start", spec.get("y_start", 0)) or 0),
            int(task.get("verification_batch_rows", spec.get("verification_batch_rows", 20)) or 20),
            int(task.get("x_start", spec.get("x_start", 0)) or 0),
        )
        timings_ms["milestones"] = int((time.perf_counter() - phase_started) * 1000)
        timings_ms["total"] = int((time.perf_counter() - started) * 1000)
        return {
            "role_result": "compute",
            "input": p2p_meta,
            "scene": scene_meta,
            "input_hash": sha256_bytes(p2p_data),
            "compute": {
                "mode": "raytracer-fragment",
                "executed": True,
                "stdout": str(rendered.get("stdout", ""))[-2048:],
                "stderr": str(rendered.get("stderr", ""))[-2048:],
                "renderer_telemetry": rendered.get("renderer_telemetry", {}),
                "timings_ms": timings_ms,
            },
            "output_ref": output_ref,
            "proof_ref": output_ref,
            "result_hash": result_hash,
            "verification_milestones": milestone_manifest,
        }

    def run_raytracer_milestone_verification(
        self,
        task: dict[str, Any],
        p2p_data: bytes,
        p2p_meta: dict[str, Any],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        timings_ms: dict[str, int] = {}
        try:
            challenge = json.loads(p2p_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"raytracer_verification_challenge_invalid:{exc}") from exc
        supported_strategies = {"random-row-milestone-v1", "random-tile-row-milestone-v2"}
        if not isinstance(challenge, dict) or challenge.get("strategy") not in supported_strategies:
            raise RuntimeError("raytracer_verification_challenge_invalid")

        sample = challenge.get("milestone")
        if not isinstance(sample, dict):
            raise RuntimeError("raytracer_verification_milestone_missing")
        y_start = int(sample.get("y_start", -1))
        y_end = int(sample.get("y_end", -1))
        x_start = int(sample.get("x_start", 0))
        x_end = int(sample.get("x_end", 0))
        sample_rows = y_end - y_start
        max_sample_rows = max(1, int(task.get("max_sample_rows", 256) or 256))
        if y_start < 0 or x_start < 0 or sample_rows <= 0 or sample_rows > max_sample_rows:
            raise RuntimeError("raytracer_verification_milestone_range_invalid")
        expected = str(sample.get("pixel_sha256", "")).removeprefix("sha256:").lower()
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise RuntimeError("raytracer_verification_milestone_hash_invalid")

        scene_ref = task.get("scene_p2p_ref") or challenge.get("scene_p2p_ref")
        if not isinstance(scene_ref, dict):
            raise RuntimeError("raytracer_scene_ref_missing")
        phase_started = time.perf_counter()
        scene_bytes, scene_meta = self.p2p.fetch(scene_ref)
        timings_ms["scene_fetch"] = int((time.perf_counter() - phase_started) * 1000)
        source_output_ref = task.get("source_output_ref")
        handoff_meta: dict[str, Any] = {}
        probabilistic_result: dict[str, Any] | None = None
        if isinstance(source_output_ref, dict):
            source_output, handoff_meta = self.p2p.fetch(source_output_ref)
            source_manifest = build_verification_milestones(
                source_output,
                int(task.get("y_start", 0) or 0),
                max(1, int(task.get("max_sample_rows", 20) or 20)),
                int(task.get("x_start", 0) or 0),
            )
            if str(source_manifest.get("commitment_hash", "")) != str(challenge.get("commitment_hash", "")):
                raise RuntimeError("raytracer_source_handoff_commitment_invalid")

            probabilistic_result = verify_probabilistic_milestones(
                source_output,
                source_manifest,
                seed=str(challenge.get("challenge_nonce", "verifier")),
                reputation_score=float(task.get("worker_reputation", 50.0)),
            )

        with tempfile.TemporaryDirectory(prefix="silicium-raytracer-milestone-verify-") as temp_dir:
            temp_path = Path(temp_dir)
            scene_path = temp_path / "scene.cfg"
            output_path = temp_path / "sample.ppm"
            scene_path.write_bytes(scene_bytes)
            if x_end <= x_start and challenge.get("strategy") == "random-row-milestone-v1":
                x_end = scene_resolution(scene_path)[0]
            if x_end <= x_start:
                raise RuntimeError("raytracer_verification_milestone_range_invalid")
            phase_started = time.perf_counter()
            rendered = run_raytracer(
                scene_path,
                output_path,
                int(task.get("timeout_s", 300) or 300),
                y_start,
                y_end,
                x_start,
                x_end,
            )
            timings_ms["renderer"] = int((time.perf_counter() - phase_started) * 1000)
            phase_started = time.perf_counter()
            recomputed_hash = ppm_pixel_sha256(output_path.read_bytes())
            timings_ms["ppm_hash"] = int((time.perf_counter() - phase_started) * 1000)

        passed = recomputed_hash == expected
        if probabilistic_result and not probabilistic_result.get("verified"):
            passed = False

        fragment_rows = max(sample_rows, int(challenge.get("fragment_rows", sample_rows) or sample_rows))
        verification = {
            "mode": str(challenge.get("strategy")),
            "challenge_nonce": str(challenge.get("challenge_nonce", "")),
            "commitment_hash": str(challenge.get("commitment_hash", "")),
            "milestone_index": int(sample.get("index", 0) or 0),
            "milestone_count": int(challenge.get("milestone_count", 1) or 1),
            "sample_y_start": y_start,
            "sample_y_end": y_end,
            "sample_x_start": x_start,
            "sample_x_end": x_end,
            "sample_rows": sample_rows,
            "fragment_rows": fragment_rows,
            "sample_ratio": sample_rows / fragment_rows,
            "expected_pixel_hash": expected,
            "recomputed_pixel_hash": recomputed_hash,
            "probabilistic_result": probabilistic_result,
        }
        return {
            "role_result": "verify",
            "input": p2p_meta,
            "scene": scene_meta,
            "source_handoff": {
                **handoff_meta,
                "source_node_id": str(task.get("source_node_id", "")),
                "direct": bool(handoff_meta),
            },
            "input_hash": sha256_bytes(p2p_data),
            "expected_hash": expected,
            "recomputed_hash": recomputed_hash,
            "verification_mode": str(challenge.get("strategy")),
            "verification": verification,
            "timings_ms": {**timings_ms, "total": int((time.perf_counter() - started) * 1000)},
            "renderer_telemetry": rendered.get("renderer_telemetry", {}),
            "verified": passed,
            "choice": passed,
            "result_hash": sha256_json({"verified": passed, **verification}),
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
        completed = self.run_process(cmd, timeout=int(task.get("timeout_s", 120)))
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
        if str(task.get("workload", "")).strip().lower() == "verification/rendering/raytracer-fragment":
            return self.run_raytracer_milestone_verification(task, p2p_data, p2p_meta)
        actual = sha256_bytes(p2p_data)
        expected = str(task.get("expected_hash") or envelope.get("expected_hash") or "").removeprefix("sha256:")
        embedded_hash = ""
        try:
            parsed = json.loads(p2p_data.decode("utf-8"))
            if isinstance(parsed, dict):
                embedded_hash = str(parsed.get("result_hash") or parsed.get("compute_result_hash") or "").removeprefix("sha256:")
        except Exception:
            pass
        passed = not expected or expected == actual or (bool(embedded_hash) and expected == embedded_hash)
        return {
            "role_result": "verify",
            "input": p2p_meta,
            "input_hash": actual,
            "expected_hash": expected,
            "recomputed_hash": embedded_hash or actual,
            "verified": passed,
            "choice": passed,
            "result_hash": sha256_json({"verified": passed, "actual": actual, "expected": expected, "embedded": embedded_hash}),
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
        embedded_hash = ""
        try:
            parsed = json.loads(p2p_data.decode("utf-8"))
            if isinstance(parsed, dict):
                embedded_hash = str(parsed.get("result_hash") or parsed.get("compute_result_hash") or "").removeprefix("sha256:")
        except Exception:
            pass
        choice = not expected or expected == actual or (bool(embedded_hash) and expected == embedded_hash)
        return {
            "request_result": kind,
            "input_hash": actual,
            "expected_hash": expected,
            "recomputed_hash": embedded_hash or actual,
            "choice": choice,
            "audit": {"passed": choice, "source": p2p_meta},
        }


class PeerNetwork:
    def __init__(self, config: NodeConfig, export_dir: Path) -> None:
        self.config = config
        self.export_dir = export_dir
        self.node_id = safe_id(config.node_id)
        self.identity = NodeIdentity(config)
        self.node_path_id = safe_path_id(self.node_id)
        self.peers_path = export_dir / f"node.{self.node_path_id}.peers.json"
        self.routes_path = export_dir / f"node.{self.node_path_id}.routes.json"
        self.candidates_path = export_dir / "p2p.candidates.json"
        self.sessions_path = export_dir / "p2p.sessions.json"
        self.session_events_path = export_dir / "p2p.sessions.ndjson"
        self.direct_sessions_path = export_dir / "p2p.direct_sessions.json"
        self.transport_attestations_path = export_dir / "p2p.transport_attestations.json"
        self.transport_attestation_events_path = export_dir / "p2p.transport_attestations.ndjson"
        self.gossip_events_path = export_dir / "gossip.events.ndjson"
        self.task_control_events_path = export_dir / "gossip.task-controls.ndjson"
        self.update_announcements_dir = export_dir / "software-updates"
        self.discovery_registry_path = export_dir / "mesh.discovery.json"
        self._peers: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._direct_sessions: dict[str, dict[str, Any]] = {}
        self._transport_attestations: list[dict[str, Any]] = []
        self._ice_content_sessions: dict[str, str] = {}
        self._signaling_ready_payloads: dict[str, dict[str, Any]] = {}
        self._started_direct_sessions: set[str] = set()
        self._local_candidates: list[dict[str, Any]] = []
        self._seen_events: set[str] = set()
        self._update_fetches: set[str] = set()
        self._verified_transport_claims: set[str] = set()
        self._seen_handshake_nonces: dict[str, float] = {}
        self._seen_punch_nonces: set[str] = set()
        self._lock = threading.RLock()
        self._http_server: http.server.ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._udp_socket: socket.socket | None = None
        self._udp_thread: threading.Thread | None = None
        self._sync_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._peer_score_sink: Any = None
        self.http_base_url = ""
        self.advertised_http_base_url = ""
        self.gossip_target = ""
        self.mesh_post_url = ""
        self.local_capacity = build_capacity_snapshot(config)
        self.local_reputation_score = float(config.reputation_score)
        self.local_resource_reputation: dict[str, Any] = DualMemoryBayes().snapshot()
        self.local_activity: dict[str, Any] = {
            "status": "idle",
            "active_tasks": [],
            "last_response": {},
        }
        self.local_task_queue: list[dict[str, Any]] = []
        self.local_onchain_reputation = 0.0
        self.local_onchain_global_reputation = 0.0
        self.local_onchain_compute_reputation = 0.0
        self.local_onchain_verify_reputation = 0.0
        self.local_onchain_storage_reputation = 0.0
        self.local_onchain_stake_amount = 0.0
        self.local_onchain_status = ""
        self.local_solana_owner = ""
        self.local_solana_worker = ""
        self._last_candidate_refresh_unix = 0.0
        self._observed_public_address = ""
        self._nat_behavior = "unknown"
        self.direct_transport = self._build_direct_transport_backend()

    def _build_direct_transport_backend(self) -> DirectTransportBackend:
        backend_name = str(self.config.p2p_direct_transport_backend or "auto").strip().lower()
        if backend_name in {"", "auto", "automatic"}:
            backend_name = "ice" if importlib.util.find_spec("aioice") is not None else "native-light"
        if backend_name in {"native-light", "native_light", "native"}:
            return NativeLightDirectTransport(self, safe_id=safe_id, utc_now=utc_now, atomic_write_json=atomic_write_json)
        if backend_name in {"ice", "aioice", "ice-stun-turn"}:
            return IceDirectTransport(self, safe_id=safe_id, utc_now=utc_now, atomic_write_json=atomic_write_json)
        raise ValueError(f"unsupported_direct_transport_backend:{backend_name}")

    def _seed_local_update_manifests(self) -> None:
        paths: list[Path] = []
        env_manifest = os.environ.get("SILICIUM_UPDATE_MANIFEST_PATH", "").strip()
        if env_manifest:
            paths.append(Path(env_manifest))
        for filename in ("update.manifest.json", "manifest.json"):
            candidate = self.export_dir / filename
            if candidate not in paths:
                paths.append(candidate)

        for path in paths:
            if not path.is_file():
                continue
            payload = read_json(path, None)
            if not payload:
                continue
            if isinstance(payload, dict):
                releases = payload.get("releases", [payload]) if "releases" in payload else [payload]
                for release in releases:
                    if isinstance(release, dict):
                        self._record_update_announcement(release, source_peer_id="local_disk")

    def start(self) -> None:
        # Upgrade old general gossip logs before any listener can append a new
        # control and accidentally make the dedicated index look complete.
        self.recent_task_control_events(2048)
        self._start_http_server()
        self._seed_local_update_manifests()
        if self.config.gossip_enable:
            self._start_udp_listener()
        self._load_persisted_peers()
        self._load_persisted_sessions()
        self._load_transport_attestations()
        self.refresh_candidates(force=True)
        self._record_self_peer()
        if self.config.peer_sync_interval_s > 0:
            self._start_sync_loop()
        # A peer may be unreachable during startup.  Announcements and the
        # initial HTTP sync each have network timeouts, so run them outside the
        # critical path: callers can publish a heartbeat as soon as the local
        # HTTP service is listening.
        threading.Thread(
            target=self._announce_and_sync_initial,
            name=f"silicium-peer-bootstrap-{self.node_id}",
            daemon=True,
        ).start()

    def _announce_and_sync_initial(self) -> None:
        try:
            self.announce()
            self.sync_once()
        except Exception:
            # Peer convergence is best-effort and retried by the periodic sync
            # loop; it must never prevent a node from becoming ready.
            return

    def stop(self) -> None:
        self._stop_event.set()
        self.direct_transport.close()
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
        self._prune_expired_peer_candidates()
        with self._lock:
            peers = sorted(self._peers.values(), key=lambda item: str(item.get("node_id", "")))
        payload = {
            "schema_version": 1,
            "node_id": self.node_id,
            "count": len(peers),
            "peers": peers,
            "routes": self.route_table_snapshot(),
            "updated_utc": utc_now(),
        }
        atomic_write_json(self.peers_path, payload)
        atomic_write_json(self.discovery_registry_path, payload)
        return payload

    def route_table_snapshot(self) -> list[dict[str, Any]]:
        """Compute shortest known peer paths, preferring direct ICE/UDP links."""
        with self._lock:
            peers = {str(peer.get("node_id", "")): dict(peer) for peer in self._peers.values() if peer.get("node_id")}
        peers[self.node_id] = {"node_id": self.node_id}
        graph: dict[str, list[tuple[float, str, str]]] = {node_id: [] for node_id in peers}
        weights = {"direct": 1.0, "relay": 2.0, "central": 8.0, "peer-http": 8.0}
        for observer, peer in peers.items():
            attestations = peer.get("transport_attestations", [])
            if not isinstance(attestations, list):
                attestations = []
            for claim in attestations:
                if not isinstance(claim, Mapping) or not bool(claim.get("success", False)):
                    continue
                target = str(claim.get("remote_peer_id", "")).strip()
                route = str(claim.get("route", "")).strip().lower()
                if target not in peers or route not in weights:
                    continue
                graph.setdefault(observer, []).append((weights[route], target, route))
            if observer != self.node_id and str(peer.get("http_base_url", "")).strip():
                graph.setdefault(self.node_id, []).append((weights["central"], observer, "central"))
        distances: dict[str, float] = {self.node_id: 0.0}
        previous: dict[str, tuple[str, str]] = {}
        queue: list[tuple[float, str]] = [(0.0, self.node_id)]
        while queue:
            cost, current = heapq.heappop(queue)
            if cost != distances.get(current):
                continue
            for edge_cost, target, route in graph.get(current, []):
                candidate = cost + edge_cost
                if candidate < distances.get(target, float("inf")):
                    distances[target] = candidate
                    previous[target] = (current, route)
                    heapq.heappush(queue, (candidate, target))
        routes: list[dict[str, Any]] = []
        for target in sorted(node_id for node_id in peers if node_id != self.node_id):
            if target not in distances:
                routes.append({"target_peer_id": target, "reachable": False, "path": [], "cost": None, "hops": 0})
                continue
            path = [target]
            route_kinds: list[str] = []
            cursor = target
            while cursor != self.node_id:
                parent, route = previous[cursor]
                route_kinds.append(route)
                path.append(parent)
                cursor = parent
            path.reverse()
            route_kinds.reverse()
            routes.append(
                {
                    "target_peer_id": target,
                    "reachable": True,
                    "path": path,
                    "next_hop": path[1] if len(path) > 1 else target,
                    "hops": len(path) - 1,
                    "cost": distances[target],
                    "transport": route_kinds[-1] if route_kinds else "local",
                }
            )
        atomic_write_json(self.routes_path, {"schema_version": 1, "node_id": self.node_id, "routes": routes, "updated_utc": utc_now()})
        return routes

    def local_candidates_snapshot(self) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._lock:
            self._local_candidates = [candidate for candidate in self._local_candidates if int(candidate.get("expires_unix", 0) or 0) > now]
            candidates = [dict(candidate) for candidate in self._local_candidates]
        self._write_candidate_snapshot(candidates)
        return candidates

    def candidate_diagnostics(self) -> dict[str, Any]:
        candidates = self.local_candidates_snapshot()
        selected = self._select_candidate(candidates)
        return {
            "candidate_count": len(candidates),
            "candidate_types": sorted({str(candidate.get("candidate_type", "")) for candidate in candidates if candidate.get("candidate_type")}),
            "selected_candidate": selected,
            "observed_public_address": self._observed_public_address,
            "nat_behavior": self._nat_behavior,
            "direct_transport_backend": self.direct_transport.name,
            "direct_transport_features": self.direct_transport.features(),
        }

    def refresh_candidates(self, *, force: bool = False) -> list[dict[str, Any]]:
        now = int(time.time())
        refresh_s = max(1, int(self.config.p2p_candidate_refresh_s))
        with self._lock:
            fresh = any(int(candidate.get("expires_unix", 0) or 0) > now for candidate in self._local_candidates)
            recently_refreshed = (now - self._last_candidate_refresh_unix) < refresh_s
        if not force and fresh and recently_refreshed:
            return self.local_candidates_snapshot()
        gathered = self._gather_host_candidates(now)
        gathered.extend(self._discover_server_reflexive_candidates(now))
        candidates = self._merge_candidate_list(gathered, self.node_id, now)
        with self._lock:
            self._local_candidates = candidates
            self._last_candidate_refresh_unix = float(now)
        self._write_candidate_snapshot(candidates)
        return [dict(candidate) for candidate in candidates]

    def record_observed_candidate(self, observed_ip: str, *, source: str = "server-observed", observed_port: int = 0) -> dict[str, Any] | None:
        now = int(time.time())
        candidate = self._server_reflexive_candidate(observed_ip, now, source=source, observed_port=observed_port)
        if candidate is None:
            return None
        with self._lock:
            merged = self._merge_candidate_list([*self._local_candidates, candidate], self.node_id, now)
            self._local_candidates = merged
            self._last_candidate_refresh_unix = float(now)
        self._write_candidate_snapshot(self.local_candidates_snapshot())
        self._record_self_peer()
        return dict(candidate)

    def _write_candidate_snapshot(self, candidates: list[dict[str, Any]]) -> None:
        atomic_write_json(
            self.candidates_path,
            {
                "schema_version": 1,
                "node_id": self.node_id,
                "updated_utc": utc_now(),
                "observed_public_address": self._observed_public_address,
                "nat_behavior": self._nat_behavior,
                "selected_candidate": self._select_candidate(candidates),
                "candidates": candidates,
            },
        )

    def _select_candidate(self, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                1 if bool(candidate.get("internet_routable", False)) else 0,
                1 if str(candidate.get("candidate_type", "")) == "srflx" else 0,
                int(candidate.get("priority", 0) or 0),
            ),
            reverse=True,
        )
        return dict(ranked[0]) if ranked else None

    def _gather_host_candidates(self, now: int) -> list[dict[str, Any]]:
        port = self._advertised_gossip_port()
        if port <= 0:
            return []
        hosts: list[tuple[str, str]] = [
            (self._advertised_gossip_host(), "advertised-gossip"),
            (str(self.config.gossip_bind), "gossip-bind"),
        ]
        default_route = self._default_route_ip()
        if default_route:
            hosts.append((default_route, "default-route"))
        try:
            hosts.append((socket.gethostname(), "hostname"))
        except Exception:
            pass
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for host, source in hosts:
            for ip in self._resolve_candidate_addresses(host):
                if ip in seen:
                    continue
                seen.add(ip)
                candidates.append(self._make_candidate("host", ip, port, source, 100, now))
        return candidates

    def _discover_server_reflexive_candidates(self, now: int) -> list[dict[str, Any]]:
        targets = {self._normalize_http_target(seed) for seed in self.config.discovery_seeds + self.config.seed_peers}
        targets.update(self._sync_targets())
        targets.discard("")
        targets.discard(self.advertised_http_base_url)
        candidates: list[dict[str, Any]] = []
        for base_url in sorted(target for target in targets if target):
            path = "/discovery/observe"
            request = urllib.request.Request(base_url.rstrip("/") + path, headers=self._signed_headers("GET", path, b""))
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            candidate = self._server_reflexive_candidate(
                str(payload.get("observed_ip", "")),
                now,
                source=f"observe:{base_url.rstrip('/')}",
                observed_port=0,
            )
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _server_reflexive_candidate(self, observed_ip: str, now: int, *, source: str, observed_port: int = 0) -> dict[str, Any] | None:
        port = int(observed_port or 0) or self._advertised_gossip_port()
        if port <= 0:
            return None
        candidate = self._make_candidate("srflx", observed_ip, port, source, 900, now)
        normalized = self._normalize_candidate(candidate, self.node_id, now)
        if normalized is None:
            return None
        if bool(normalized.get("internet_routable", False)):
            self._observed_public_address = str(normalized.get("ip", ""))
            self._nat_behavior = "public_or_endpoint_independent" if self._has_matching_public_host(normalized) else "address_translated"
        else:
            self._nat_behavior = "private_or_unroutable_observed"
        return normalized

    def _make_candidate(self, candidate_type: str, ip: str, port: int, source: str, priority: int, now: int) -> dict[str, Any]:
        ttl_s = max(1, int(self.config.p2p_candidate_ttl_s))
        return {
            "candidate_type": candidate_type,
            "transport": "udp",
            "ip": str(ip).strip(),
            "port": int(port),
            "priority": int(priority),
            "observed_unix": now,
            "expires_unix": now + ttl_s,
            "source": str(source),
        }

    def _normalize_candidate_list(self, candidates: Any, peer_id: str, now: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(candidates, list):
            return []
        return self._merge_candidate_list(candidates, peer_id, int(now if now is not None else time.time()))

    def _merge_candidate_list(self, candidates: list[dict[str, Any]], peer_id: str, now: int) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str, str, int], dict[str, Any]] = {}
        for candidate in candidates:
            normalized = self._normalize_candidate(candidate, peer_id, now)
            if normalized is None:
                continue
            key = (
                str(normalized.get("candidate_type", "")),
                str(normalized.get("transport", "")),
                str(normalized.get("ip", "")),
                int(normalized.get("port", 0) or 0),
            )
            previous = merged.get(key)
            if previous is None or int(normalized.get("priority", 0) or 0) >= int(previous.get("priority", 0) or 0):
                merged[key] = normalized
        return sorted(merged.values(), key=lambda candidate: str(candidate.get("candidate_id", "")))

    def _normalize_candidate(self, candidate: Any, peer_id: str, now: int) -> dict[str, Any] | None:
        if not isinstance(candidate, Mapping):
            return None
        candidate_type = str(candidate.get("candidate_type", "")).strip().lower()
        if candidate_type not in {"host", "srflx", "relay"}:
            return None
        transport = str(candidate.get("transport", "udp")).strip().lower()
        if transport != "udp":
            return None
        try:
            ip_value = ipaddress.ip_address(str(candidate.get("ip", "")).strip().strip("[]"))
            port = int(candidate.get("port", 0) or 0)
            if "observed_unix" in candidate:
                observed_unix = int(candidate.get("observed_unix", 0) or 0)
            else:
                observed_unix = int(int(candidate.get("observed_unix_ms", now * 1000) or 0) // 1000)
            if "expires_unix" in candidate:
                expires_unix = int(candidate.get("expires_unix", 0) or 0)
            else:
                expires_unix = int(int(candidate.get("expires_unix_ms", 0) or 0) // 1000)
            priority = int(candidate.get("priority", 0) or 0)
        except (TypeError, ValueError):
            return None
        if port <= 0 or port > 65535 or observed_unix <= 0 or expires_unix <= now:
            return None
        family = "ipv6" if ip_value.version == 6 else "ipv4"
        metadata = self._ip_metadata(ip_value)
        normalized = {
            "candidate_id": safe_id(str(candidate.get("candidate_id", "")))
            if str(candidate.get("candidate_id", "")).strip()
            else self._candidate_id(peer_id, candidate_type, transport, ip_value.compressed, port),
            "peer_id": safe_id(peer_id),
            "address_family": family,
            "transport": transport,
            "ip": ip_value.compressed,
            "port": port,
            "candidate_type": candidate_type,
            "priority": priority,
            "observed_unix": observed_unix,
            "expires_unix": expires_unix,
            "source": str(candidate.get("source", candidate.get("source_interface", ""))).strip(),
            "private": bool(metadata["private"]),
            "local": bool(metadata["local"]),
            "internet_routable": bool(metadata["public"]),
        }
        if "nat_behavior" in candidate:
            normalized["nat_behavior"] = str(candidate.get("nat_behavior", "")).strip()
        return normalized

    def _candidate_id(self, peer_id: str, candidate_type: str, transport: str, ip: str, port: int) -> str:
        digest = sha256_bytes(stable_json([safe_id(peer_id), candidate_type, transport, ip, int(port)]).encode("utf-8"))[:16]
        return f"cand-{safe_id(peer_id)}-{candidate_type}-{digest}"

    def _ip_metadata(self, ip_value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> dict[str, bool]:
        local = bool(ip_value.is_loopback or ip_value.is_link_local or ip_value.is_private or ip_value.is_unspecified)
        public = not bool(
            ip_value.is_loopback
            or ip_value.is_link_local
            or ip_value.is_private
            or ip_value.is_multicast
            or ip_value.is_reserved
            or ip_value.is_unspecified
        )
        return {"local": local, "private": not public, "public": public}

    def _resolve_candidate_addresses(self, host: str) -> list[str]:
        value = str(host or "").strip().strip("[]")
        if not value or value in {"0.0.0.0", "::"}:
            return []
        try:
            return [ipaddress.ip_address(value).compressed]
        except ValueError:
            pass
        addresses: set[str] = set()
        try:
            for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(value, None):
                if family not in {socket.AF_INET, socket.AF_INET6}:
                    continue
                addresses.add(ipaddress.ip_address(str(sockaddr[0])).compressed)
        except OSError:
            return []
        return sorted(addresses)

    def _default_route_ip(self) -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(("8.8.8.8", 80))
                return str(sock.getsockname()[0])
            finally:
                sock.close()
        except OSError:
            return ""

    def _has_matching_public_host(self, observed: Mapping[str, Any]) -> bool:
        observed_ip = str(observed.get("ip", ""))
        for candidate in self._local_candidates:
            if str(candidate.get("candidate_type", "")) == "host" and bool(candidate.get("internet_routable", False)) and str(candidate.get("ip", "")) == observed_ip:
                return True
        return False

    def _prune_expired_peer_candidates(self) -> None:
        now = int(time.time())
        changed = False
        with self._lock:
            for peer in self._peers.values():
                candidates = peer.get("candidates")
                if not isinstance(candidates, list):
                    continue
                fresh = [candidate for candidate in candidates if isinstance(candidate, dict) and int(candidate.get("expires_unix", 0) or 0) > now]
                if len(fresh) != len(candidates):
                    peer["candidates"] = fresh
                    changed = True
        if changed:
            atomic_write_json(self.peers_path, {"schema_version": 1, "node_id": self.node_id, "count": len(self._peers), "peers": list(self._peers.values()), "updated_utc": utc_now()})

    def sessions_snapshot(self) -> dict[str, Any]:
        self._prune_expired_sessions()
        with self._lock:
            sessions = sorted(self._sessions.values(), key=lambda item: str(item.get("session_id", "")))
        payload = {"schema_version": 1, "node_id": self.node_id, "count": len(sessions), "sessions": sessions, "updated_utc": utc_now()}
        atomic_write_json(self.sessions_path, payload)
        return payload

    def record_transport_attestation(
        self,
        *,
        route: str,
        transport_backend: str,
        remote_peer_id: str = "",
        session_id: str = "",
        proof_scope: str = "connectivity_check",
        task_id: str = "",
        content_id: str = "",
        content_sha256: str = "",
        size_bytes: int = 0,
        endpoint: str = "",
        relay_peer_id: str = "",
        selected_candidate_pair: Mapping[str, Any] | None = None,
        peer_proof: Mapping[str, Any] | None = None,
        success: bool = True,
        failure_reason: str = "",
    ) -> dict[str, Any]:
        normalized_route = safe_id(str(route)).lower()
        if normalized_route not in {"direct", "relay", "central", "failed"}:
            raise ValueError(f"unsupported_transport_route:{normalized_route}")
        normalized_remote = self._optional_peer_id(remote_peer_id)
        pair = selected_candidate_pair if isinstance(selected_candidate_pair, Mapping) else {}
        proof = peer_proof if isinstance(peer_proof, Mapping) else {}
        peer_proof_hash = sha256_bytes(stable_json(dict(proof)).encode("utf-8")) if proof else ""
        peer_proof_verified = bool(
            proof
            and proof.get("signature")
            and proof.get("public_key")
            and self._verify_message(dict(proof))
            and (
                not normalized_remote
                or safe_id(str(proof.get("node_id") or proof.get("source_peer_id") or "")) == normalized_remote
            )
        )
        claim = {
            "schema_version": 1,
            "attestation_type": "silicium.transport-path",
            "observer_peer_id": self.node_id,
            "observer_identity_id": self.identity.identity_id,
            "observer_public_key": self.identity.public_key_b64,
            "remote_peer_id": normalized_remote,
            "route": normalized_route,
            "transport_backend": safe_id(str(transport_backend)).lower(),
            "proof_scope": safe_id(str(proof_scope)).lower(),
            "session_id": str(session_id).strip(),
            "task_id": self._optional_peer_id(task_id),
            "content_id": str(content_id).strip(),
            "content_sha256": str(content_sha256).removeprefix("sha256:").strip().lower(),
            "size_bytes": max(0, int(size_bytes)),
            "endpoint": str(endpoint).strip(),
            "relay_peer_id": self._optional_peer_id(relay_peer_id),
            "selected_candidate_pair": {
                str(key): value
                for key, value in pair.items()
                if str(key)
                in {
                    "local_candidate_id",
                    "remote_candidate_id",
                    "ack_local_candidate_id",
                    "ack_remote_candidate_id",
                    "local_candidate_type",
                    "remote_candidate_type",
                }
            },
            "peer_proof_hash": peer_proof_hash,
            "peer_proof_verified": peer_proof_verified,
            "success": bool(success),
            "failure_reason": safe_id(str(failure_reason)).lower() if failure_reason else "",
            "timestamp_unix": int(time.time()),
            "timestamp_utc": utc_now(),
        }
        claim_hash = sha256_bytes(stable_json(claim).encode("utf-8"))
        attestation = {
            **claim,
            "claim_hash": claim_hash,
            "signature": self.identity.sign_bytes(stable_json(claim).encode("utf-8")),
        }
        with self._lock:
            if not any(item.get("claim_hash") == claim_hash for item in self._transport_attestations):
                self._transport_attestations.append(attestation)
                self._transport_attestations = self._transport_attestations[-128:]
        append_jsonl(self.transport_attestation_events_path, attestation)
        self.transport_attestations_snapshot()
        return dict(attestation)

    def record_transport_attestation_background(self, **claim: Any) -> None:
        def _record() -> None:
            try:
                self.record_transport_attestation(**claim)
            except (OSError, RuntimeError, ValueError):
                return

        threading.Thread(
            target=_record,
            name=f"transport-attestation-{self.node_path_id}",
            daemon=True,
        ).start()

    @staticmethod
    def verify_transport_attestation(attestation: Mapping[str, Any]) -> bool:
        if not isinstance(attestation, Mapping):
            return False
        signature = str(attestation.get("signature", "")).strip()
        claim_hash = str(attestation.get("claim_hash", "")).strip().lower()
        public_key = str(attestation.get("observer_public_key", "")).strip()
        identity_id = str(attestation.get("observer_identity_id", "")).strip()
        route = str(attestation.get("route", "")).strip().lower()
        if not signature or not claim_hash or route not in {"direct", "relay", "central", "failed"}:
            return False
        if NodeIdentity.identity_id_for_key(public_key) != identity_id:
            return False
        claim = dict(attestation)
        claim.pop("signature", None)
        claim.pop("claim_hash", None)
        encoded = stable_json(claim).encode("utf-8")
        return PeerNetwork._transport_attestation_hash_valid(attestation) and NodeIdentity.verify_bytes(encoded, signature, public_key)

    @staticmethod
    def _transport_attestation_hash_valid(attestation: Mapping[str, Any]) -> bool:
        claim_hash = str(attestation.get("claim_hash", "")).strip().lower()
        if not claim_hash:
            return False
        claim = dict(attestation)
        claim.pop("signature", None)
        claim.pop("claim_hash", None)
        return hmac.compare_digest(
            sha256_bytes(stable_json(claim).encode("utf-8")),
            claim_hash,
        )

    def recent_transport_attestations(self, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(
                self._transport_attestations,
                key=lambda item: (int(item.get("timestamp_unix", 0) or 0), str(item.get("claim_hash", ""))),
                reverse=True,
            )
        return [dict(item) for item in ordered[: max(0, int(limit))]]

    def transport_attestations_snapshot(self) -> dict[str, Any]:
        attestations = self.recent_transport_attestations(128)
        payload = {
            "schema_version": 1,
            "node_id": self.node_id,
            "count": len(attestations),
            "attestations": attestations,
            "updated_utc": utc_now(),
        }
        atomic_write_json(self.transport_attestations_path, payload)
        return payload

    def _load_transport_attestations(self) -> None:
        snapshot = read_json(self.transport_attestations_path, {})
        attestations = snapshot.get("attestations") if isinstance(snapshot, dict) else None
        if not isinstance(attestations, list):
            return
        verified = [
            dict(attestation)
            for attestation in attestations
            if isinstance(attestation, Mapping)
            and str(attestation.get("observer_peer_id", "")) == self.node_id
            and self.verify_transport_attestation(attestation)
        ]
        with self._lock:
            self._transport_attestations = verified[-128:]

    def create_signaling_session(self, payload: Mapping[str, Any], requester_node_id: str) -> tuple[int, dict[str, Any]]:
        self._prune_expired_sessions()
        requester_id = safe_id(str(payload.get("peer_id", requester_node_id)))
        requester_node_id = safe_id(requester_node_id)
        target_peer_id = safe_id(str(payload.get("target_peer_id", "")))
        task_id = safe_id(str(payload.get("task_id", ""))) if str(payload.get("task_id", "")).strip() else ""
        purpose = safe_id(str(payload.get("purpose", "direct_session")))
        content_id = str(payload.get("content_id", "") or payload.get("payload_id", "")).strip()
        allowed_transports = {
            safe_id(str(item)).lower()
            for item in (payload.get("allowed_transports", []) if isinstance(payload.get("allowed_transports", []), list) else [])
            if str(item).strip()
        }
        if requester_node_id and requester_id != requester_node_id:
            return 403, {"ok": False, "error": "requester_mismatch"}
        if not requester_id or not target_peer_id or requester_id == target_peer_id:
            return 400, {"ok": False, "error": "invalid_peer_pair"}
        allowed, reason = self._authorize_session_pair(requester_id, target_peer_id, task_id, purpose, content_id)
        if not allowed:
            return 403, {"ok": False, "error": reason}
        requester_peer = self._peer_for_signaling(requester_id)
        target_peer = self._peer_for_signaling(target_peer_id)
        if requester_peer is None or target_peer is None:
            return 404, {"ok": False, "error": "peer_not_registered"}
        candidate_pairs = self._candidate_pairs(requester_peer, target_peer)
        allow_ice_ready_candidates = "ice" in allowed_transports or (
            "ice_v1" in set(requester_peer.get("features", [])) and "ice_v1" in set(target_peer.get("features", []))
        )
        if not candidate_pairs and not allow_ice_ready_candidates:
            return 409, {"ok": False, "error": "no_valid_candidate_pair"}
        now = int(time.time())
        ttl_s = max(1, int(self.config.p2p_session_ttl_s))
        session_id = "p2p-sess-" + uuid.uuid4().hex
        session = {
            "schema_version": 1,
            "session_id": session_id,
            "status": "signaling",
            "initiator_peer_id": requester_id,
            "target_peer_id": target_peer_id,
            "purpose": purpose,
            "task_id": task_id,
            "content_id": content_id,
            "candidate_pairs": candidate_pairs,
            "allowed_transports": sorted(allowed_transports),
            "ready_peers": [],
            "ready_transports": {},
            "results": [],
            "created_unix": now,
            "expires_unix": now + ttl_s,
            "updated_utc": utc_now(),
        }
        with self._lock:
            self._sessions[session_id] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_created", session)
        return 201, {"ok": True, "session": self._session_response(session)}

    def mark_session_ready(self, session_id: str, requester_node_id: str, payload: Mapping[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        session, error = self._session_for_peer(session_id, requester_node_id)
        if session is None:
            return error
        if str(session.get("status", "")) in {"direct", "relay", "completed"}:
            return 200, {"ok": True, "session": self._session_response(session), "punch_start": self._punch_start_message(session)}
        payload = payload or {}
        peer_id = safe_id(requester_node_id)
        ready = list(session.get("ready_peers", [])) if isinstance(session.get("ready_peers"), list) else []
        if peer_id not in ready:
            ready.append(peer_id)
        session["ready_peers"] = sorted(ready)
        if isinstance(payload, Mapping) and payload:
            ready_transports = dict(session.get("ready_transports", {})) if isinstance(session.get("ready_transports"), dict) else {}
            transport_payload = {
                "direct_transport_backend": str(payload.get("direct_transport_backend", "")),
                "ice": payload.get("ice", {}) if isinstance(payload.get("ice", {}), Mapping) else {},
            }
            ready_transports[peer_id] = transport_payload
            session["ready_transports"] = ready_transports
        session["status"] = "punching" if {session["initiator_peer_id"], session["target_peer_id"]}.issubset(set(ready)) else "ready_wait"
        session["updated_utc"] = utc_now()
        with self._lock:
            self._sessions[str(session["session_id"])] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_ready", session, {"peer_id": peer_id})
        return 200, {"ok": True, "session": self._session_response(session), "punch_start": self._punch_start_message(session)}

    def record_session_result(self, session_id: str, payload: Mapping[str, Any], requester_node_id: str) -> tuple[int, dict[str, Any]]:
        session, error = self._session_for_peer(session_id, requester_node_id)
        if session is None:
            return error
        peer_id = safe_id(requester_node_id)
        ok = bool(payload.get("ok", False))
        transport = safe_id(str(payload.get("transport", "direct")))
        path_attestation = payload.get("path_attestation")
        if path_attestation:
            if (
                not isinstance(path_attestation, Mapping)
                or str(path_attestation.get("observer_peer_id", "")) != peer_id
                or str(path_attestation.get("session_id", "")) != str(session_id)
                or str(path_attestation.get("route", "")) != (transport if ok else "failed")
                or not self.verify_transport_attestation(path_attestation)
            ):
                return 400, {"ok": False, "error": "transport_attestation_invalid"}
        result = {
            "peer_id": peer_id,
            "ok": ok,
            "transport": transport,
            "selected_local_candidate_id": str(payload.get("selected_local_candidate_id", "")),
            "selected_remote_candidate_id": str(payload.get("selected_remote_candidate_id", "")),
            "error": str(payload.get("error", "")),
            "path_attestation": dict(path_attestation) if isinstance(path_attestation, Mapping) else {},
            "attestation_verified": bool(path_attestation) and isinstance(path_attestation, Mapping),
            "timestamp_unix": int(time.time()),
        }
        results = list(session.get("results", [])) if isinstance(session.get("results"), list) else []
        results.append(result)
        session["results"] = results[-8:]
        session["status"] = transport if ok and transport in {"direct", "relay"} else ("failed" if not ok else "completed")
        session["updated_utc"] = utc_now()
        with self._lock:
            self._sessions[str(session["session_id"])] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_result", session, result)
        return 200, {"ok": True, "session": self._session_response(session)}

    def close_session(self, session_id: str, payload: Mapping[str, Any], requester_node_id: str) -> tuple[int, dict[str, Any]]:
        session, error = self._session_for_peer(session_id, requester_node_id)
        if session is None:
            return error
        peer_id = safe_id(requester_node_id)
        session["status"] = "closed"
        session["closed_by"] = peer_id
        session["close_reason"] = safe_id(str(payload.get("reason", "closed")))
        session["updated_utc"] = utc_now()
        with self._lock:
            self._sessions[str(session["session_id"])] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_closed", session, {"peer_id": peer_id, "reason": session["close_reason"]})
        return 200, {"ok": True, "session": self._session_response(session)}

    def _load_persisted_sessions(self) -> None:
        snapshot = read_json(self.sessions_path, {})
        sessions = snapshot.get("sessions") if isinstance(snapshot, dict) else None
        if not isinstance(sessions, list):
            return
        now = int(time.time())
        with self._lock:
            for session in sessions:
                if not isinstance(session, dict):
                    continue
                session_id = str(session.get("session_id", "")).strip()
                if not session_id or int(session.get("expires_unix", 0) or 0) <= now:
                    continue
                if str(session.get("status", "")) in {"closed", "failed"}:
                    continue
                self._sessions[session_id] = dict(session)

    def _write_sessions_snapshot(self) -> None:
        with self._lock:
            sessions = sorted(self._sessions.values(), key=lambda item: str(item.get("session_id", "")))
        atomic_write_json(
            self.sessions_path,
            {"schema_version": 1, "node_id": self.node_id, "count": len(sessions), "sessions": sessions, "updated_utc": utc_now()},
        )

    def _emit_signaling_event(self, event_type: str, session: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> None:
        payload = {
            "schema_version": 1,
            "timestamp_utc": utc_now(),
            "node_id": self.node_id,
            "event_type": event_type,
            "session_id": str(session.get("session_id", "")),
            "status": str(session.get("status", "")),
            "initiator_peer_id": str(session.get("initiator_peer_id", "")),
            "target_peer_id": str(session.get("target_peer_id", "")),
            "task_id": str(session.get("task_id", "")),
        }
        if extra:
            payload.update(dict(extra))
        append_jsonl(self.session_events_path, payload)

    def _authorize_session_pair(
        self,
        requester_id: str,
        target_peer_id: str,
        task_id: str,
        purpose: str,
        content_id: str = "",
    ) -> tuple[bool, str]:
        if not task_id:
            if purpose == "content_fetch" and content_id:
                return True, "ok"
            return (purpose in {"nat_punch", "diagnostic"}), "task_required"
        for directory in ("tasks", "requests"):
            path = self.export_dir / directory / f"{safe_path_id(safe_id(task_id))}.json"
            envelope = read_json(path, {})
            if not isinstance(envelope, dict) or not envelope:
                continue
            assigned = {
                self._optional_peer_id(envelope.get("dispatched_to", "")),
                self._optional_peer_id(envelope.get("assigned_peer_id", "")),
                self._optional_peer_id(envelope.get("target_peer_id", "")),
                self._optional_peer_id(envelope.get("handled_by", "")),
            }
            assigned.discard("")
            owners = {
                self._optional_peer_id(envelope.get("node_id", "")),
                self._optional_peer_id(envelope.get("dispatched_by", "")),
                self._optional_peer_id(envelope.get("requester_peer_id", "")),
                self.node_id,
            }
            owners.discard("")
            pair = {requester_id, target_peer_id}
            if assigned.intersection(pair) and (owners.intersection(pair) or self.node_id in pair):
                return True, "ok"
            if {requester_id, target_peer_id}.issubset(assigned):
                return True, "ok"
            return False, "task_peer_pair_unauthorized"
        return False, "task_not_found"

    def _optional_peer_id(self, value: Any) -> str:
        return optional_peer_id(value)

    def _peer_for_signaling(self, peer_id: str) -> dict[str, Any] | None:
        safe_peer_id = safe_id(peer_id)
        if safe_peer_id == self.node_id:
            self._record_self_peer()
        with self._lock:
            peer = self._peers.get(safe_peer_id)
            return dict(peer) if isinstance(peer, dict) else None

    def _candidate_pairs(self, initiator_peer: Mapping[str, Any], target_peer: Mapping[str, Any]) -> list[dict[str, Any]]:
        now = int(time.time())
        local = self._normalize_candidate_list(initiator_peer.get("candidates", []), str(initiator_peer.get("node_id", "")), now)
        remote = self._normalize_candidate_list(target_peer.get("candidates", []), str(target_peer.get("node_id", "")), now)
        pairs: list[dict[str, Any]] = []
        for local_candidate in local:
            for remote_candidate in remote:
                if str(local_candidate.get("transport", "")) != str(remote_candidate.get("transport", "")):
                    continue
                if str(local_candidate.get("address_family", "")) != str(remote_candidate.get("address_family", "")):
                    continue
                priority = self._candidate_pair_priority(local_candidate, remote_candidate)
                pairs.append(
                    {
                        "local_candidate_id": str(local_candidate.get("candidate_id", "")),
                        "remote_candidate_id": str(remote_candidate.get("candidate_id", "")),
                        "transport": str(local_candidate.get("transport", "udp")),
                        "address_family": str(local_candidate.get("address_family", "")),
                        "priority": priority,
                        "local_candidate": local_candidate,
                        "remote_candidate": remote_candidate,
                    }
                )
        pairs.sort(key=lambda pair: int(pair.get("priority", 0) or 0), reverse=True)
        return pairs

    def _candidate_pair_priority(self, local_candidate: Mapping[str, Any], remote_candidate: Mapping[str, Any]) -> int:
        score = int(local_candidate.get("priority", 0) or 0) + int(remote_candidate.get("priority", 0) or 0)
        if bool(local_candidate.get("internet_routable", False)):
            score += 1000
        if bool(remote_candidate.get("internet_routable", False)):
            score += 1000
        if str(local_candidate.get("candidate_type", "")) == "srflx":
            score += 200
        if str(remote_candidate.get("candidate_type", "")) == "srflx":
            score += 200
        return score

    def _session_response(self, session: Mapping[str, Any]) -> dict[str, Any]:
        response = dict(session)
        response["candidate_pairs"] = list(session.get("candidate_pairs", [])) if isinstance(session.get("candidate_pairs"), list) else []
        return response

    def _punch_start_message(self, session: Mapping[str, Any]) -> dict[str, Any]:
        message = {
            "message_type": "punch_start",
            "session_id": str(session.get("session_id", "")),
            "peer_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "initiator_peer_id": str(session.get("initiator_peer_id", "")),
            "target_peer_id": str(session.get("target_peer_id", "")),
            "candidate_pairs": list(session.get("candidate_pairs", [])) if isinstance(session.get("candidate_pairs"), list) else [],
            "retry": {
                "count": max(1, int(self.config.p2p_punch_retry_count)),
                "interval_ms": max(1, int(self.config.p2p_punch_interval_ms)),
                "timeout_ms": max(1, int(self.config.p2p_session_timeout_ms)),
            },
            "timestamp_unix": int(time.time()),
            "nonce": uuid.uuid4().hex,
        }
        ready_transports = session.get("ready_transports", {}) if isinstance(session.get("ready_transports"), Mapping) else {}
        ice_peers: dict[str, Any] = {}
        for peer_id in (str(session.get("initiator_peer_id", "")), str(session.get("target_peer_id", ""))):
            transport = ready_transports.get(peer_id) if isinstance(ready_transports.get(peer_id), Mapping) else {}
            ice = transport.get("ice") if isinstance(transport.get("ice"), Mapping) else {}
            if ice.get("supported") is True:
                ice_peers[peer_id] = dict(ice)
        if ice_peers:
            message["ice"] = {"peers": ice_peers}
        self._sign_message(message)
        return message

    def _session_for_peer(self, session_id: str, requester_node_id: str) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]]]:
        self._prune_expired_sessions()
        safe_session_id = str(session_id).strip()
        requester_id = safe_id(requester_node_id)
        with self._lock:
            session = dict(self._sessions.get(safe_session_id, {}))
        if not session:
            return None, (404, {"ok": False, "error": "session_not_found"})
        if int(session.get("expires_unix", 0) or 0) <= int(time.time()):
            self._expire_session(safe_session_id, session)
            return None, (410, {"ok": False, "error": "session_expired"})
        if str(session.get("status", "")) == "closed":
            return None, (409, {"ok": False, "error": "session_closed"})
        if requester_id not in {str(session.get("initiator_peer_id", "")), str(session.get("target_peer_id", "")), self.node_id}:
            return None, (403, {"ok": False, "error": "session_peer_unauthorized"})
        return session, (200, {"ok": True})

    def _prune_expired_sessions(self) -> None:
        now = int(time.time())
        expired: list[dict[str, Any]] = []
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                if int(session.get("expires_unix", 0) or 0) <= now and str(session.get("status", "")) not in {"closed", "direct", "relay"}:
                    expired_session = dict(session)
                    expired_session["status"] = "expired"
                    expired.append(expired_session)
                    self._sessions.pop(session_id, None)
        for session in expired:
            self._emit_signaling_event("session_expired", session)
        if expired:
            self._write_sessions_snapshot()

    def _expire_session(self, session_id: str, session: Mapping[str, Any]) -> None:
        expired = dict(session)
        expired["status"] = "expired"
        with self._lock:
            self._sessions.pop(session_id, None)
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_expired", expired)

    def set_local_profile(
        self,
        *,
        capacity: dict[str, Any] | None = None,
        reputation_score: float | None = None,
        resource_reputation: dict[str, Any] | None = None,
        onchain_reputation: float | None = None,
        onchain_global_reputation: float | None = None,
        onchain_compute_reputation: float | None = None,
        onchain_verify_reputation: float | None = None,
        onchain_storage_reputation: float | None = None,
        onchain_stake_amount: float | None = None,
        onchain_status: str | None = None,
        solana_owner: str | None = None,
        solana_worker: str | None = None,
        activity: dict[str, Any] | None = None,
        task_queue: list[dict[str, Any]] | None = None,
    ) -> None:
        if capacity is not None:
            self.local_capacity = capacity
        if reputation_score is not None:
            self.local_reputation_score = float(reputation_score)
        if resource_reputation is not None:
            self.local_resource_reputation = dict(resource_reputation)
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
        if activity is not None:
            self.local_activity = dict(activity)
        if task_queue is not None:
            self.local_task_queue = [dict(item) for item in task_queue[:64] if isinstance(item, dict)]
        self._record_self_peer()

    def set_peer_score_sink(self, callback: Any) -> None:
        self._peer_score_sink = callback

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

    def publish(self, topic: str, payload: dict[str, Any], *, background: bool = False) -> None:
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
        if background:
            threading.Thread(
                target=self._broadcast,
                args=(message,),
                name=f"silicium-gossip-publish-{safe_path_id(topic)}",
                daemon=True,
            ).start()
        else:
            self._broadcast(message)

    @staticmethod
    def _normalize_update_announcement(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        channel = str(payload.get("channel", "")).strip().lower()
        version = str(payload.get("version", "")).strip()
        digest = str(payload.get("sha256", "")).strip().lower()
        content_id = str(payload.get("content_id", digest)).strip().lower()
        signature = str(payload.get("signature", "")).strip()
        try:
            size_bytes = int(payload.get("size_bytes", 0) or 0)
            check_interval = max(15, int(payload.get("check_interval_seconds", 0) or 0))
        except (TypeError, ValueError):
            return None
        if channel not in {"dev", "prod"} or not version or len(version) > 80:
            return None
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            return None
        if content_id != digest or size_bytes <= 0 or size_bytes > 1024 * 1024 * 1024:
            return None
        if not signature or len(signature) > 256:
            return None
        return {
            "schema_version": 1,
            "channel": channel,
            "version": version,
            "url": str(payload.get("url", "")).strip(),
            "sha256": digest,
            "content_id": content_id,
            "size_bytes": size_bytes,
            "auto_install": bool(payload.get("auto_install", True)),
            "check_interval_seconds": check_interval,
            "signature": signature,
            "signing_key_id": str(payload.get("signing_key_id", "")).strip(),
            "publisher_id": str(payload.get("publisher_id", "")).strip(),
            "publisher_public_key": str(payload.get("publisher_public_key", "")).strip(),
        }

    def _record_update_announcement(self, payload: Any, source_peer_id: str) -> bool:
        release = self._normalize_update_announcement(payload)
        if release is None:
            return False
        
        # Verify Ed25519 signature of the manifest (Issue #76)
        unsigned_payload = {
            "schema_version": 1,
            "channel": release["channel"],
            "version": release["version"],
            "content_id": release["content_id"],
            "sha256": release["sha256"],
            "url": release["url"],
            "size_bytes": release["size_bytes"],
            "check_interval_seconds": release["check_interval_seconds"],
            "publisher_id": release["publisher_id"],
            "publisher_public_key": release["publisher_public_key"],
        message_bytes = stable_json(unsigned_payload).encode("utf-8")
        if not self.identity.verify_bytes(message_bytes, release["signature"], release["publisher_public_key"]):
            return False

        release["source_peer_id"] = safe_id(source_peer_id) if source_peer_id else ""
        release["observed_utc"] = utc_now()
        target = (
            self.update_announcements_dir
            / release["channel"]
            / f"{safe_path_id(release['version'])}-{release['content_id']}.json"
        )
        atomic_write_json(target, release)
        return True

    def update_announcements(self) -> list[dict[str, Any]]:
        releases: list[dict[str, Any]] = []
        if self.update_announcements_dir.exists():
            for path in self.update_announcements_dir.glob("*/*.json"):
                payload = read_json(path, {})
                normalized = self._normalize_update_announcement(payload)
                if normalized is None:
                    continue
                normalized["source_peer_id"] = str(payload.get("source_peer_id", ""))
                normalized["observed_utc"] = str(payload.get("observed_utc", ""))
                normalized["cached"] = (self.export_dir / "p2p" / normalized["content_id"]).is_file()
                releases.append(normalized)
        releases.sort(key=lambda item: (str(item.get("channel", "")), str(item.get("version", "")), str(item.get("observed_utc", ""))))
        return releases[-64:]

    def fetch_update_content(self, content_id: str) -> bytes:
        normalized = str(content_id).strip().lower()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("update_content_id_invalid")
        known = [release for release in self.update_announcements() if release.get("content_id") == normalized]
        if not known:
            raise FileNotFoundError("update_announcement_not_found")
        target = self.export_dir / "p2p" / normalized
        if target.is_file():
            data = target.read_bytes()
        else:
            preferred_peer_id = str(known[-1].get("source_peer_id", ""))
            data, _meta = self.fetch_content(normalized, preferred_peer_id)
            expected_size = int(known[-1].get("size_bytes", 0) or 0)
            if expected_size > 0 and len(data) != expected_size:
                raise ValueError("update_size_mismatch")
            if sha256_bytes(data) != normalized:
                raise ValueError("update_sha256_mismatch")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(data)
            self.publish(
                "software_update_cached",
                {"content_id": normalized, "size_bytes": len(data), "cached_by": self.node_id},
            )
        if sha256_bytes(data) != normalized:
            raise ValueError("update_sha256_mismatch")
        return data

    def announce(self) -> None:
        candidates = self.refresh_candidates()
        message = {
            "message_type": "peer_announce",
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "roles": sorted(self.config.roles),
            "app_version": self.config.app_version,
            "release_channel": self.config.release_channel,
            "release_build": self.config.release_build,
            "features": sorted({*self.direct_transport.features(), "raytracer_fastpath_v1"}),
            "transport_attestations": self.recent_transport_attestations(4),
            "http_base_url": self.advertised_http_base_url,
            "mesh_post_url": self.mesh_post_url,
            "gossip_bind": self._advertised_gossip_host(),
            "gossip_port": self._advertised_gossip_port(),
            "candidates": candidates,
            "relay_capable": bool(self.config.relay_enable),
            "capacity": self.local_capacity,
            "reputation_score": self.local_reputation_score,
            "resource_reputation": self.local_resource_reputation,
            "activity": self.local_activity,
            "task_queue": self.local_task_queue,
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
        self.announce_candidates(candidates)

    def announce_candidates(self, candidates: list[dict[str, Any]] | None = None) -> None:
        candidate_list = candidates if candidates is not None else self.refresh_candidates()
        message = {
            "message_type": "candidate_announce",
            "peer_id": self.node_id,
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "candidates": candidate_list,
            "timestamp_utc": utc_now(),
            "timestamp_unix": int(time.time()),
            "nonce": uuid.uuid4().hex,
        }
        self._sign_message(message)
        self._broadcast(message)

    def fetch_content(self, content_id: str, preferred_peer_id: str = "") -> tuple[bytes, dict[str, Any]]:
        peers = self.peers_snapshot().get("peers", [])
        candidates = []
        if preferred_peer_id:
            candidates.extend([peer for peer in peers if str(peer.get("node_id", "")) == preferred_peer_id])
        candidates.extend([peer for peer in peers if str(peer.get("node_id", "")) != preferred_peer_id])
        for peer in candidates:
            ice_capable = bool(self.config.nat_punch_enable and "ice_v1" in {
                str(feature) for feature in (peer.get("features", []) if isinstance(peer.get("features", []), list) else [])
            })
            if self._prefer_peer_http(peer) and not ice_capable:
                data = self._fetch_direct_from_peer(peer, content_id)
                if data is not None:
                    return data, self._attested_fetch_meta(
                        peer,
                        content_id=content_id,
                        data=data,
                        route="direct",
                        transport_backend="peer-http",
                        endpoint=str(peer.get("http_base_url", "")),
                    )
            ice_result = self._fetch_direct_ice(peer, content_id)
            if ice_result is not None:
                return ice_result
            if self._prefer_peer_http(peer):
                data = self._fetch_direct_from_peer(peer, content_id)
                if data is not None:
                    return data, self._attested_fetch_meta(
                        peer,
                        content_id=content_id,
                        data=data,
                        route="direct",
                        transport_backend="peer-http",
                        endpoint=str(peer.get("http_base_url", "")),
                    )
        if preferred_peer_id:
            self.request_udp_punch(preferred_peer_id)
            time.sleep(0.1)
            for peer in candidates:
                if str(peer.get("node_id", "")) != preferred_peer_id:
                    continue
                data = self._fetch_direct_from_peer(peer, content_id)
                if data is not None:
                    return data, self._attested_fetch_meta(
                        peer,
                        content_id=content_id,
                        data=data,
                        route="direct",
                        transport_backend="peer-http-after-punch",
                        endpoint=str(peer.get("http_base_url", "")),
                    )
        relayed = self._fetch_via_relays(content_id, preferred_peer_id, candidates)
        if relayed is not None:
            return relayed
        raise FileNotFoundError(f"peer_content_not_found:{content_id}")

    @staticmethod
    def _prefer_peer_http(peer: Mapping[str, Any]) -> bool:
        """Use reachable public HTTP before paying the ICE setup cost."""
        parsed = urlparse(str(peer.get("http_base_url", "")).strip())
        if parsed.scheme.lower() == "https" and parsed.hostname:
            return True
        try:
            address = ipaddress.ip_address(str(parsed.hostname or ""))
        except ValueError:
            return False
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_reserved
        )

    def _attested_fetch_meta(
        self,
        peer: Mapping[str, Any],
        *,
        content_id: str,
        data: bytes,
        route: str,
        transport_backend: str,
        endpoint: str = "",
        relay_peer_id: str = "",
    ) -> dict[str, Any]:
        meta = dict(peer)
        meta["transport_route"] = route
        meta["transport_backend"] = transport_backend
        meta["path_attestation"] = self.record_transport_attestation(
            route=route,
            transport_backend=transport_backend,
            remote_peer_id=str(peer.get("node_id", "")),
            proof_scope="payload_transfer",
            content_id=content_id,
            content_sha256=sha256_bytes(data),
            size_bytes=len(data),
            endpoint=endpoint,
            relay_peer_id=relay_peer_id,
            success=True,
        )
        return meta

    def _fetch_direct_ice(self, peer: dict[str, Any], content_id: str) -> tuple[bytes, dict[str, Any]] | None:
        if not self.config.nat_punch_enable or self.direct_transport.name != "ice":
            return None
        features = peer.get("features", []) if isinstance(peer.get("features", []), list) else []
        if "ice_v1" not in {str(feature) for feature in features}:
            return None
        peer_id = safe_id(str(peer.get("node_id", "")))
        if not peer_id or peer_id == self.node_id:
            return None
        session_id = self._ice_content_sessions.get(peer_id, "")
        if session_id:
            result = self.direct_transport.request_content(session_id, content_id)
            if result is not None:
                return result
            self._ice_content_sessions.pop(peer_id, None)
        session_id = self._open_ice_content_session(peer, content_id)
        if not session_id:
            return None
        result = self.direct_transport.request_content(session_id, content_id)
        if result is None:
            self._ice_content_sessions.pop(peer_id, None)
            return None
        self._ice_content_sessions[peer_id] = session_id
        return result

    def _open_ice_content_session(self, peer: dict[str, Any], content_id: str) -> str:
        target_peer_id = safe_id(str(peer.get("node_id", "")))
        if not target_peer_id:
            return ""
        signaling_targets = self._signaling_targets()
        if not signaling_targets:
            direct_target = str(peer.get("http_base_url", "")).rstrip("/")
            if direct_target:
                signaling_targets.append(direct_target)
        request_payload = {
            "peer_id": self.node_id,
            "target_peer_id": target_peer_id,
            "purpose": "content_fetch",
            "content_id": content_id,
            "allowed_transports": ["ice"],
        }
        for base_url in signaling_targets:
            try:
                response = self._post_peer_json(base_url, "/p2p/sessions/request", request_payload)
                session = response.get("session") if isinstance(response.get("session"), dict) else {}
                session_id = str(session.get("session_id", "")).strip()
                if not session_id:
                    continue
                ready = self.build_session_ready_payload(session)
                self._signaling_ready_payloads[session_id] = ready
                deadline = time.monotonic() + max(8.0, float(self.config.p2p_session_timeout_ms) / 1000.0)
                while time.monotonic() < deadline:
                    ready_response = self._post_peer_json(base_url, f"/p2p/sessions/{session_id}/ready", ready)
                    ready_session = ready_response.get("session") if isinstance(ready_response.get("session"), dict) else {}
                    punch_start = ready_response.get("punch_start") if isinstance(ready_response.get("punch_start"), dict) else {}
                    ice = punch_start.get("ice") if isinstance(punch_start.get("ice"), dict) else {}
                    ice_peers = ice.get("peers") if isinstance(ice.get("peers"), dict) else {}
                    if str(ready_session.get("status", "")) == "punching" and len(ice_peers) >= 2:
                        result = self.establish_direct_udp_session(punch_start)
                        self._report_signaling_result(base_url, session_id, result)
                        return session_id if result.get("status") == "direct" else ""
                    time.sleep(0.1)
            except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError):
                continue
        return ""

    def _signaling_targets(self) -> list[str]:
        targets: set[str] = set()
        for seed in self.config.discovery_seeds + self.config.seed_peers:
            normalized = self._normalize_http_target(seed)
            if normalized and normalized != self.advertised_http_base_url:
                targets.add(normalized)
        return sorted(targets)

    def _poll_signaling_sessions(self, base_url: str) -> None:
        path = "/p2p/sessions/pending"
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            headers=self._signed_headers("GET", path, b""),
        )
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            return
        sessions = payload.get("sessions") if isinstance(payload, dict) else None
        if not isinstance(sessions, list):
            return
        for session in sessions:
            if not isinstance(session, dict) or safe_id(str(session.get("target_peer_id", ""))) != self.node_id:
                continue
            session_id = str(session.get("session_id", "")).strip()
            if not session_id:
                continue
            with self._lock:
                if session_id in self._started_direct_sessions:
                    continue
            ready = self._signaling_ready_payloads.get(session_id)
            if ready is None:
                ready = self.build_session_ready_payload(session)
                self._signaling_ready_payloads[session_id] = ready
            try:
                ready_response = self._post_peer_json(base_url, f"/p2p/sessions/{session_id}/ready", ready)
            except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError):
                continue
            ready_session = ready_response.get("session") if isinstance(ready_response.get("session"), dict) else {}
            punch_start = ready_response.get("punch_start") if isinstance(ready_response.get("punch_start"), dict) else {}
            if str(ready_session.get("status", "")) == "punching":
                self._start_direct_session_background(punch_start, base_url)

    def _post_peer_json(self, base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        raw = stable_json(payload).encode("utf-8")
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=raw,
            method="POST",
            headers=self._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("peer_response_not_object")
        return body

    def _report_signaling_result(self, base_url: str, session_id: str, result: Mapping[str, Any]) -> None:
        pair = result.get("selected_candidate_pair") if isinstance(result.get("selected_candidate_pair"), Mapping) else {}
        path_attestation = next(
            (
                item
                for item in self.recent_transport_attestations(16)
                if str(item.get("session_id", "")) == session_id
                and str(item.get("proof_scope", "")) == "connectivity_check"
            ),
            {},
        )
        try:
            self._post_peer_json(
                base_url,
                f"/p2p/sessions/{session_id}/result",
                {
                    "ok": result.get("status") == "direct",
                    "transport": "direct" if result.get("status") == "direct" else "failed",
                    "error": result.get("failure_reason", ""),
                    "selected_local_candidate_id": pair.get("local_candidate_id", ""),
                    "selected_remote_candidate_id": pair.get("remote_candidate_id", ""),
                    "path_attestation": path_attestation,
                },
            )
        except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            pass

    def _serve_direct_content(self, session_id: str, requester_peer_id: str, content_id: str) -> tuple[bool, bytes, str]:
        requester_id = safe_id(requester_peer_id)
        with self._lock:
            session = dict(self._direct_sessions.get(str(session_id), {}))
        if str(session.get("status", "")) != "direct" or safe_id(str(session.get("remote_peer_id", ""))) != requester_id:
            return False, b"", "session_not_direct"
        if not content_id or Path(content_id).name != content_id:
            return False, b"", "content_id_invalid"
        content_path = self.export_dir / "p2p" / content_id
        try:
            if not content_path.is_file():
                return False, b"", "content_not_found"
            return True, content_path.read_bytes(), ""
        except OSError:
            return False, b"", "content_read_failed"

    def _record_self_peer(self) -> None:
        candidates = self.local_candidates_snapshot()
        transport_attestations = self.recent_transport_attestations(4)
        with self._lock:
            self._peers[self.node_id] = {
                "node_id": self.node_id,
                "identity_id": self.identity.identity_id,
                "public_key": self.identity.public_key_b64,
                "roles": sorted(self.config.roles),
                "app_version": self.config.app_version,
                "release_channel": self.config.release_channel,
                "release_build": self.config.release_build,
                "features": sorted({*self.direct_transport.features(), "raytracer_fastpath_v1"}),
                "transport_attestations": transport_attestations,
                "http_base_url": self.advertised_http_base_url,
                "mesh_post_url": self.mesh_post_url,
                "gossip_bind": self._advertised_gossip_host(),
                "gossip_port": self._advertised_gossip_port(),
                "candidates": candidates,
                "relay_capable": bool(self.config.relay_enable),
                "capacity": self.local_capacity,
                "reputation_score": self.local_reputation_score,
                "resource_reputation": self.local_resource_reputation,
                "activity": self.local_activity,
                "task_queue": self.local_task_queue,
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
        candidates = self._normalize_candidate_list(message.get("candidates", []), node_id)
        transport_attestations = self._verified_peer_transport_attestations(
            node_id,
            message.get("transport_attestations", []),
        )
        with self._lock:
            current = dict(self._peers.get(node_id, {}))
            roles = message.get("roles") if isinstance(message.get("roles"), list) else []
            features = message.get("features") if isinstance(message.get("features"), list) else []
            capacity = message.get("capacity") if isinstance(message.get("capacity"), dict) else {}
            resource_reputation = message.get("resource_reputation") if isinstance(message.get("resource_reputation"), dict) else {}
            activity = message.get("activity") if isinstance(message.get("activity"), dict) else {}
            task_queue = message.get("task_queue") if isinstance(message.get("task_queue"), list) else []
            merged = {
                "node_id": node_id,
                # Peer tables are transitive and are not proof that a third
                # party is authorised to change another peer's identity or
                # routing profile. Keep established fields; signed candidate
                # announcements refresh the mutable NAT addresses separately.
                "identity_id": str(current.get("identity_id", "") or message.get("identity_id", "")),
                "public_key": str(current.get("public_key", "") or message.get("public_key", "")),
                "roles": list(current.get("roles", []) or roles),
                "app_version": str(message.get("app_version", "") or current.get("app_version", "")),
                "release_channel": str(message.get("release_channel", "") or current.get("release_channel", "")),
                "release_build": str(message.get("release_build", "") or current.get("release_build", "")),
                "features": [str(feature) for feature in (current.get("features", []) or features)],
                "transport_attestations": transport_attestations or current.get("transport_attestations", []),
                "http_base_url": str(current.get("http_base_url", "") or message.get("http_base_url", "")),
                "mesh_post_url": str(current.get("mesh_post_url", "") or message.get("mesh_post_url", "")),
                "gossip_bind": str(current.get("gossip_bind", "") or message.get("gossip_bind", "")),
                "gossip_port": int(current.get("gossip_port", 0) or message.get("gossip_port", 0) or 0),
                "candidates": candidates or current.get("candidates", []),
                "relay_capable": bool(message.get("relay_capable", current.get("relay_capable", False))),
                "capacity": capacity or current.get("capacity", {}),
                "reputation_score": float(message.get("reputation_score", current.get("reputation_score", 0.0)) or 0.0),
                "resource_reputation": resource_reputation or current.get("resource_reputation", {}),
                "activity": activity if "activity" in message else current.get("activity", {}),
                "task_queue": (
                    [dict(item) for item in task_queue[:64] if isinstance(item, dict)]
                    if "task_queue" in message
                    else current.get("task_queue", [])
                ),
                "onchain_reputation": float(message.get("onchain_reputation", current.get("onchain_reputation", 0.0)) or 0.0),
                "onchain_global_reputation": float(message.get("onchain_global_reputation", current.get("onchain_global_reputation", 0.0)) or 0.0),
                "onchain_compute_reputation": float(message.get("onchain_compute_reputation", current.get("onchain_compute_reputation", 0.0)) or 0.0),
                "onchain_verify_reputation": float(message.get("onchain_verify_reputation", current.get("onchain_verify_reputation", 0.0)) or 0.0),
                "onchain_storage_reputation": float(message.get("onchain_storage_reputation", current.get("onchain_storage_reputation", 0.0)) or 0.0),
                "onchain_stake_amount": float(message.get("onchain_stake_amount", current.get("onchain_stake_amount", 0.0)) or 0.0),
                "onchain_status": str(message.get("onchain_status", "") or current.get("onchain_status", "")),
                "solana_owner": str(message.get("solana_owner", "") or current.get("solana_owner", "")),
                "solana_worker": str(message.get("solana_worker", "") or current.get("solana_worker", "")),
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

    def _verified_peer_transport_attestations(self, node_id: str, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        verified: list[dict[str, Any]] = []
        for item in raw[-8:]:
            if not isinstance(item, Mapping) or str(item.get("observer_peer_id", "")) != node_id:
                continue
            claim_hash = str(item.get("claim_hash", "")).strip().lower()
            if not claim_hash:
                continue
            with self._lock:
                known = claim_hash in self._verified_transport_claims
            if known and not self._transport_attestation_hash_valid(item):
                continue
            if not known and not self.verify_transport_attestation(item):
                continue
            with self._lock:
                self._verified_transport_claims.add(claim_hash)
            verified.append(dict(item))
        verified.sort(key=lambda item: int(item.get("timestamp_unix", 0) or 0), reverse=True)
        return verified[:8]

    def _record_candidate_announce(self, message: dict[str, Any]) -> bool:
        node_id = safe_id(str(message.get("peer_id", message.get("node_id", ""))))
        if not node_id:
            return False
        candidates = self._normalize_candidate_list(message.get("candidates", []), node_id)
        with self._lock:
            current = dict(self._peers.get(node_id, {"node_id": node_id}))
            existing = current.get("candidates", []) if isinstance(current.get("candidates"), list) else []
            current["candidates"] = self._merge_candidate_list([*existing, *candidates], node_id, int(time.time()))
            current["last_seen_unix"] = int(time.time())
            current["updated_utc"] = str(message.get("timestamp_utc", utc_now()))
            current["self"] = node_id == self.node_id
            self._peers[node_id] = current
        self.peers_snapshot()
        return True

    def _record_event(self, message: dict[str, Any]) -> bool:
        event_id = str(message.get("event_id", "")).strip()
        if not event_id:
            return False
        with self._lock:
            if event_id in self._seen_events:
                return False
            self._seen_events.add(event_id)
        append_jsonl(self.gossip_events_path, message)
        if str(message.get("topic", "")).strip() == "task_control":
            append_jsonl(self.task_control_events_path, message)
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
        if self._udp_socket is not None:
            try:
                self._udp_socket.sendto(payload, (host, port))
                return
            except OSError:
                pass
        family = socket.AF_INET6 if ":" in str(host) else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            try:
                sock.sendto(payload, (host, port))
            except OSError:
                # A stale LAN/ICE candidate or a transient route failure must
                # never terminate gossip reconciliation.
                return
        finally:
            sock.close()

    def _send_http(self, base_url: str, message: dict[str, Any]) -> None:
        url = base_url.rstrip("/") + "/mesh"
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers=self._signed_headers("POST", "/mesh", data, {"Content-Type": "application/json"}))
        try:
            with urllib.request.urlopen(req, timeout=5):
                return
        except (urllib.error.URLError, TimeoutError, OSError):
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
        relays = self.select_peers(required_roles=set(), limit=max(1, self.config.relay_hops), require_relay=True, exclude={target_peer_id})
        if not relays:
            relays = [peer for peer in candidates if str(peer.get("node_id", "")) != target_peer_id and bool(peer.get("relay_capable", False))]
        for relay in relays:
            relay_url = str(relay.get("http_base_url", "")).rstrip("/")
            if not relay_url:
                continue
            path = f"/relay/fetch?peer_id={quote(target_peer_id, safe='')}&content_id={quote(content_id, safe='')}"
            request = urllib.request.Request(relay_url + path, headers=self._signed_headers("GET", path, b""))
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        data = response.read()
                        peer = {
                            "node_id": target_peer_id,
                            "http_base_url": relay_url,
                            "relayed_via": relay.get("node_id", ""),
                        }
                        return data, self._attested_fetch_meta(
                            peer,
                            content_id=content_id,
                            data=data,
                            route="relay",
                            transport_backend="relay-http",
                            endpoint=relay_url,
                            relay_peer_id=str(relay.get("node_id", "")),
                        )
                except (urllib.error.URLError, TimeoutError, OSError):
                    if attempt < 2:
                        time.sleep(0.05)
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

    def direct_sessions_snapshot(self) -> dict[str, Any]:
        return self.direct_transport.direct_sessions_snapshot()

    def direct_transport_snapshot(self) -> dict[str, Any]:
        requested = str(self.config.p2p_direct_transport_backend or "auto").strip().lower() or "auto"
        features = self.direct_transport.features()
        attestations = self.recent_transport_attestations(8)
        return {
            "schema_version": 1,
            "node_id": self.node_id,
            "requested_backend": requested,
            "active_backend": self.direct_transport.name,
            "features": features,
            "ice_enabled": "ice_v1" in features,
            "nat_punch_enabled": bool(self.config.nat_punch_enable),
            "stun_configured": bool(self.config.p2p_stun_server),
            "turn_configured": bool(self.config.p2p_turn_server),
            "latest_transport_route": str(attestations[0].get("route", "")) if attestations else "",
            "transport_attestations": attestations,
            "updated_utc": utc_now(),
        }

    def establish_direct_udp_session(self, punch_start: Mapping[str, Any]) -> dict[str, Any]:
        return self.direct_transport.establish_session(punch_start)

    def _start_direct_session_background(self, punch_start: Mapping[str, Any], signaling_base_url: str = "") -> None:
        if not isinstance(punch_start, Mapping):
            return
        ice = punch_start.get("ice") if isinstance(punch_start.get("ice"), Mapping) else {}
        peers = ice.get("peers") if isinstance(ice.get("peers"), Mapping) else {}
        if len(peers) < 2:
            return
        session_id = str(punch_start.get("session_id", "")).strip()
        if not session_id:
            return
        with self._lock:
            if session_id in self._started_direct_sessions:
                return
            self._started_direct_sessions.add(session_id)

        def _establish_target_session() -> None:
            result = self.establish_direct_udp_session(punch_start)
            if signaling_base_url:
                self._report_signaling_result(signaling_base_url, session_id, result)
            else:
                pair = result.get("selected_candidate_pair") if isinstance(result.get("selected_candidate_pair"), dict) else {}
                path_attestation = next(
                    (
                        item
                        for item in self.recent_transport_attestations(16)
                        if str(item.get("session_id", "")) == session_id
                        and str(item.get("proof_scope", "")) == "connectivity_check"
                    ),
                    {},
                )
                self.record_session_result(
                    session_id,
                    {
                        "ok": result.get("status") == "direct",
                        "transport": "direct" if result.get("status") == "direct" else "failed",
                        "error": result.get("failure_reason", ""),
                        "selected_local_candidate_id": pair.get("local_candidate_id", ""),
                        "selected_remote_candidate_id": pair.get("remote_candidate_id", ""),
                        "path_attestation": path_attestation,
                    },
                    self.node_id,
                )

        threading.Thread(target=_establish_target_session, name=f"ice-target-{session_id}", daemon=True).start()

    def build_session_ready_payload(self, session: Mapping[str, Any]) -> dict[str, Any]:
        return self.direct_transport.build_session_ready_payload(session)

    def _handle_direct_punch_probe(self, message: Mapping[str, Any], sender: str) -> None:
        self.direct_transport.handle_punch_probe(message, sender)

    def _handle_punch_ack(self, message: Mapping[str, Any]) -> None:
        self.direct_transport.handle_punch_ack(message)

    def request_udp_punch(self, target_peer_id: str) -> bool:
        if not self.config.nat_punch_enable:
            return False
        session_id = "punch-" + uuid.uuid4().hex
        handshake = self.create_session_handshake(
            target_peer_id=target_peer_id,
            session_id=session_id,
            purpose="nat_punch",
            candidate_fingerprints=[
                {"candidate_id": str(candidate.get("candidate_id", "")), "expires_unix": int(candidate.get("expires_unix", 0) or 0)}
                for candidate in self.refresh_candidates()
            ],
        )

        target_urls: list[str] = []
        target_peers = [
            peer
            for peer in self.peers_snapshot().get("peers", [])
            if str(peer.get("node_id", "")) == target_peer_id
        ]
        if target_peers:
            target_peer = target_peers[0]
            if target_peer.get("http_base_url"):
                target_urls.append(str(target_peer["http_base_url"]).rstrip("/"))
            for cand in target_peer.get("candidates", []):
                if isinstance(cand, dict) and cand.get("ip") and cand.get("port"):
                    ip = str(cand["ip"])
                    port = cand["port"]
                    formatted_ip = f"[{ip}]" if ":" in ip else ip
                    cand_url = f"http://{formatted_ip}:{port}".rstrip("/")
                    if cand_url not in target_urls:
                        target_urls.append(cand_url)

        relays = self.select_peers(required_roles=set(), limit=max(1, self.config.relay_hops), require_relay=True, exclude={target_peer_id})
        for relay in relays:
            relay_url = str(relay.get("http_base_url", "")).rstrip("/")
            if relay_url and relay_url not in target_urls:
                target_urls.append(relay_url)

        payload = {"target_peer_id": target_peer_id, "session_id": session_id, "handshake": handshake}
        raw = stable_json(payload).encode("utf-8")
        path = "/relay/punch"

        for base_url in target_urls:
            request = urllib.request.Request(
                base_url + path,
                data=raw,
                method="POST",
                headers=self._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    if response.status in {200, 202}:
                        return True
            except Exception:
                continue
        return False

    def create_session_handshake(
        self,
        *,
        target_peer_id: str,
        session_id: str = "",
        purpose: str = "direct_session",
        task_id: str = "",
        candidate_fingerprints: list[dict[str, Any]] | None = None,
        ttl_s: int = 300,
    ) -> dict[str, Any]:
        now = int(time.time())
        handshake = {
            "schema_version": 1,
            "message_type": "session_handshake",
            "session_id": session_id or "sess-" + uuid.uuid4().hex,
            "peer_id": self.node_id,
            "target_peer_id": safe_id(target_peer_id),
            "purpose": safe_id(purpose),
            "task_id": str(task_id or ""),
            "roles": sorted(self.config.roles),
            "reputation_score": self.local_reputation_score,
            "resource_reputation": self.local_resource_reputation,
            "onchain_reputation": self.local_onchain_reputation,
            "candidate_fingerprints": candidate_fingerprints or [],
            "timestamp_unix": now,
            "expires_unix": now + max(1, int(ttl_s)),
            "nonce": uuid.uuid4().hex,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
        }
        handshake["signature"] = self.identity.sign_bytes(stable_json(handshake).encode("utf-8"))
        return handshake

    def verify_session_handshake(
        self,
        handshake: Mapping[str, Any] | None,
        *,
        expected_peer_id: str = "",
        expected_target_peer_id: str = "",
        authorized_task_ids: set[str] | None = None,
        max_age_s: int = 300,
    ) -> tuple[bool, str]:
        if not isinstance(handshake, Mapping):
            return False, "handshake_not_object"
        if str(handshake.get("message_type", "")) != "session_handshake":
            return False, "handshake_type_invalid"
        public_key = str(handshake.get("public_key", "")).strip()
        identity_id = str(handshake.get("identity_id", "")).strip()
        signature = str(handshake.get("signature", "")).strip()
        if not public_key or not identity_id or not signature:
            return False, "handshake_identity_missing"
        if NodeIdentity.identity_id_for_key(public_key) != identity_id:
            return False, "handshake_identity_mismatch"
        unsigned = dict(handshake)
        unsigned.pop("signature", None)
        if not NodeIdentity.verify_bytes(stable_json(unsigned).encode("utf-8"), signature, public_key):
            return False, "handshake_signature_invalid"
        peer_id = safe_id(str(handshake.get("peer_id", "")))
        target_peer_id = safe_id(str(handshake.get("target_peer_id", "")))
        if expected_peer_id and peer_id != safe_id(expected_peer_id):
            return False, "handshake_peer_mismatch"
        if expected_target_peer_id and target_peer_id != safe_id(expected_target_peer_id):
            return False, "handshake_target_mismatch"
        now = int(time.time())
        try:
            timestamp_unix = int(handshake.get("timestamp_unix", 0) or 0)
            expires_unix = int(handshake.get("expires_unix", 0) or 0)
        except (TypeError, ValueError):
            return False, "handshake_timestamp_invalid"
        if timestamp_unix <= 0 or abs(now - timestamp_unix) > max(1, int(max_age_s)):
            return False, "handshake_expired"
        if expires_unix <= now:
            return False, "handshake_expired"
        task_id = str(handshake.get("task_id", "") or "")
        if authorized_task_ids is not None and task_id not in authorized_task_ids:
            return False, "handshake_task_unauthorized"
        roles = handshake.get("roles", [])
        if not isinstance(roles, list) or not roles:
            return False, "handshake_roles_invalid"
        role_set = {str(role).lower() for role in roles}
        if not role_set.issubset(NETWORK_ROLES):
            return False, "handshake_roles_invalid"
        try:
            float(handshake.get("reputation_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            return False, "handshake_reputation_invalid"
        candidates = handshake.get("candidate_fingerprints", [])
        if not isinstance(candidates, list):
            return False, "handshake_candidates_invalid"
        for candidate in candidates:
            if not isinstance(candidate, dict):
                return False, "handshake_candidates_invalid"
            try:
                candidate_expires = int(candidate.get("expires_unix", expires_unix) or expires_unix)
            except (TypeError, ValueError):
                return False, "handshake_candidates_invalid"
            if candidate_expires <= now:
                return False, "handshake_candidate_expired"
        nonce = str(handshake.get("nonce", "")).strip()
        session_id = str(handshake.get("session_id", "")).strip()
        if not nonce or not session_id:
            return False, "handshake_nonce_missing"
        replay_key = f"{identity_id}:{session_id}:{nonce}"
        self._prune_handshake_nonces(now)
        with self._lock:
            if replay_key in self._seen_handshake_nonces:
                return False, "handshake_replay"
            self._seen_handshake_nonces[replay_key] = float(expires_unix)
        return True, "ok"

    def _prune_handshake_nonces(self, now: int | None = None) -> None:
        cutoff = float(now if now is not None else int(time.time()))
        with self._lock:
            for key, expires_at in list(self._seen_handshake_nonces.items()):
                if float(expires_at) <= cutoff:
                    self._seen_handshake_nonces.pop(key, None)

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
        checks = {
            "min_global_reputation": float(peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0)) or 0.0),
            "min_compute_reputation": float(peer.get("onchain_compute_reputation", 0.0) or 0.0),
            "min_verify_reputation": float(peer.get("onchain_verify_reputation", 0.0) or 0.0),
            "min_storage_reputation": float(peer.get("onchain_storage_reputation", 0.0) or 0.0),
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

    def _peer_score(self, peer: dict[str, Any], required_roles: set[str]) -> tuple[float, float, float]:
        capacity = peer.get("capacity", {}) if isinstance(peer.get("capacity"), dict) else {}
        reputation = float(peer.get("reputation_score", 0.0) or 0.0)
        resource_reputation = peer.get("resource_reputation") if isinstance(peer.get("resource_reputation"), dict) else {}
        dimensions = resource_reputation.get("dimensions") if isinstance(resource_reputation.get("dimensions"), dict) else {}
        if "verify" in required_roles:
            resource_dimension = "verify"
        elif "storage" in required_roles:
            resource_dimension = "storage"
        elif "compute" in required_roles:
            resource_dimension = "compute"
        else:
            resource_dimension = "delegation"
        role_memory = dimensions.get(resource_dimension) if isinstance(dimensions.get(resource_dimension), dict) else {}
        connection_memory = dimensions.get("connection") if isinstance(dimensions.get("connection"), dict) else {}
        role_combined = role_memory.get("combined") if isinstance(role_memory.get("combined"), dict) else {}
        connection_combined = connection_memory.get("combined") if isinstance(connection_memory.get("combined"), dict) else {}
        if "lower_bound" in role_combined:
            role_lower = float(role_combined.get("lower_bound", 0.0) or 0.0)
            connection_lower = float(connection_combined.get("lower_bound", role_lower) or role_lower)
            reputation = 100.0 * ((role_lower * 0.75) + (connection_lower * 0.25))
        if "verify" in required_roles:
            onchain_reputation = float(peer.get("onchain_verify_reputation", peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0))) or 0.0)
        elif "storage" in required_roles:
            onchain_reputation = float(peer.get("onchain_storage_reputation", peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0))) or 0.0)
        else:
            onchain_reputation = float(peer.get("onchain_compute_reputation", peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0))) or 0.0)
        cpu = float(capacity.get("cpu_count", 0) or 0)
        disk_free = float(capacity.get("disk_free_bytes", 0) or 0)
        onchain_component = onchain_reputation * max(0.0, float(self.config.scheduler_onchain_weight))
        offchain_component = reputation * max(0.0, float(self.config.scheduler_offchain_weight))
        capacity_component = (cpu + (disk_free / max(1.0, 1024.0 * 1024.0 * 1024.0))) * max(
            0.0, float(self.config.scheduler_capacity_weight)
        )
        return (onchain_component, offchain_component, capacity_component)

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
        if message_type == "candidate_announce":
            self._record_candidate_announce(message)
            return
        if message_type == "punch_probe":
            requester_handshake = message.get("requester_handshake")
            if not isinstance(requester_handshake, dict):
                self._handle_direct_punch_probe(message, sender)
                return
            if isinstance(requester_handshake, dict) and safe_id(str(requester_handshake.get("peer_id", ""))) != self.node_id:
                ok, _reason = self.verify_session_handshake(requester_handshake, expected_target_peer_id=self.node_id)
                if not ok:
                    return
            target_host = str(message.get("target_host", "")).strip()
            target_port = int(message.get("target_port", 0) or 0)
            if target_host and target_port > 0:
                probe = {
                    "message_type": "peer_announce",
                    "node_id": self.node_id,
                    "identity_id": self.identity.identity_id,
                    "public_key": self.identity.public_key_b64,
                    "roles": sorted(self.config.roles),
                    "app_version": self.config.app_version,
                    "release_channel": self.config.release_channel,
                    "release_build": self.config.release_build,
                    "http_base_url": self.advertised_http_base_url,
                    "mesh_post_url": self.mesh_post_url,
                    "gossip_bind": self._advertised_gossip_host(),
                    "gossip_port": self._advertised_gossip_port(),
                    "candidates": self.refresh_candidates(),
                    "relay_capable": bool(self.config.relay_enable),
                    "capacity": self.local_capacity,
                    "reputation_score": self.local_reputation_score,
                    "resource_reputation": self.local_resource_reputation,
                    "activity": self.local_activity,
                    "task_queue": self.local_task_queue,
                    "timestamp_utc": utc_now(),
                }
                self._sign_message(probe)
                self._send_udp(f"{target_host}:{target_port}", target_host, target_port, probe)
            return
        if message_type == "punch_ack":
            self._handle_punch_ack(message)
            return
        if message_type != "gossip_event":
            return
        if not self._record_event(message):
            return
        topic = str(message.get("topic", ""))
        if topic == "software_update":
            self._record_update_announcement(message.get("payload"), str(message.get("node_id", "")))
        elif topic == "task_control" and self.node is not None:
            payload = message.get("payload")
            if isinstance(payload, dict):
                self.node.apply_task_control(payload, signed_by=str(message.get("node_id", "")))
        hops = int(message.get("hops", 0) or 0)
        if hops >= max(1, int(self.config.gossip_max_hops)):
            return
        forwarded = dict(message)
        forwarded["hops"] = hops + 1
        self._broadcast(forwarded, exclude=sender)

    def _handle_udp_message(self, message: dict[str, Any], sender: str) -> None:
        self._handle_network_message(message, sender)

    def _start_sync_loop(self) -> None:
        def _loop() -> None:
            while not self._stop_event.wait(max(1, self.config.peer_sync_interval_s)):
                try:
                    self.sync_once()
                except Exception as exc:
                    # Peer discovery is a permanent background responsibility.
                    # Persist the incident for diagnostics, then keep reconciling.
                    try:
                        append_jsonl(
                            self.export_dir / "peer-sync-errors.ndjson",
                            {
                                "schema_version": 1,
                                "timestamp_utc": utc_now(),
                                "node_id": self.node_id,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                        )
                    except OSError:
                        pass

        self._sync_thread = threading.Thread(target=_loop, name=f"silicium-peer-sync-{self.node_id}", daemon=True)
        self._sync_thread.start()

    def sync_once(self) -> None:
        self._prune_stale_peers()
        self.refresh_candidates()
        self._record_self_peer()
        targets = self._sync_targets()
        for base_url in targets:
            self._sync_peer_table(base_url)
            self._sync_task_controls(base_url)
            self._sync_recent_events(base_url)
            self._sync_update_manifest(base_url)
            self._poll_signaling_sessions(base_url)
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

    def recent_task_control_events(self, limit: int) -> list[dict[str, Any]]:
        """Return durable signed controls even when normal gossip history is noisy.

        Older nodes only persisted controls in the general event log. Bootstrap
        the dedicated anti-entropy index from that log once so upgrades retain
        every still-relevant cancellation.
        """
        if limit <= 0:
            return []
        with self._lock:
            if not self.task_control_events_path.exists():
                controls: list[dict[str, Any]] = []
                if self.gossip_events_path.exists():
                    try:
                        lines = self.gossip_events_path.read_text(encoding="utf-8").splitlines()
                    except Exception:
                        lines = []
                    for line in lines:
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(payload, dict) and str(payload.get("topic", "")).strip() == "task_control":
                            controls.append(payload)
                self.task_control_events_path.parent.mkdir(parents=True, exist_ok=True)
                for control in controls:
                    append_jsonl(self.task_control_events_path, control)
                if not controls:
                    self.task_control_events_path.touch(exist_ok=True)
            try:
                lines = self.task_control_events_path.read_text(encoding="utf-8").splitlines()[-limit:]
            except Exception:
                return []
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and str(payload.get("topic", "")).strip() == "task_control":
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
        # A public HTTP seed is also a discovery rendezvous. Desktop nodes only
        # receive --seed-peers from the installer, so restricting registration
        # to --discovery-seeds left their ICE candidates local-only.
        seeds = {
            seed.strip()
            for seed in self.config.discovery_seeds + self.config.seed_peers
            if seed.strip()
        }
        for seed in sorted(seeds):
            base_url = self._normalize_http_target(seed)
            if not base_url:
                continue
            self._register_with_discovery(base_url)
            self._fetch_discovery_snapshot(base_url)

    def _register_with_discovery(self, base_url: str) -> None:
        candidates = self.refresh_candidates()
        payload = {
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "roles": sorted(self.config.roles),
            "app_version": self.config.app_version,
            "release_channel": self.config.release_channel,
            "release_build": self.config.release_build,
            "features": sorted({*self.direct_transport.features(), "raytracer_fastpath_v1"}),
            "transport_attestations": self.recent_transport_attestations(4),
            "http_base_url": self.advertised_http_base_url,
            "mesh_post_url": self.mesh_post_url,
            "gossip_bind": self._advertised_gossip_host(),
            "gossip_port": self._advertised_gossip_port(),
            "candidates": candidates,
            "relay_capable": bool(self.config.relay_enable),
            "capacity": self.local_capacity,
            "reputation_score": self.local_reputation_score,
            "resource_reputation": self.local_resource_reputation,
            "activity": self.local_activity,
            "task_queue": self.local_task_queue,
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

    def _sync_task_controls(self, base_url: str) -> None:
        """Reconcile signed cancellation controls outside the bounded event feed."""
        path = "/events/task-controls?limit=2048"
        url = f"{base_url.rstrip('/')}{path}"
        try:
            request = urllib.request.Request(url, headers=self._signed_headers("GET", path, b""))
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return
        for event in events:
            if isinstance(event, dict):
                self._handle_network_message(event, base_url)

    def _sync_update_manifest(self, base_url: str) -> None:
        """Reconcile durable update announcements after transient gossip loss."""
        path = "/updates/manifest"
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            headers=self._signed_headers("GET", path, b""),
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        releases = payload.get("releases")
        if not isinstance(releases, list):
            return
        source_peer_id = str(payload.get("node_id", "")).strip()
        known = {
            (str(item.get("channel", "")), str(item.get("version", "")), str(item.get("content_id", "")))
            for item in self.update_announcements()
        }
        for release in releases:
            normalized = self._normalize_update_announcement(release)
            if normalized is None:
                continue
            key = (normalized["channel"], normalized["version"], normalized["content_id"])
            if key in known:
                continue
            if self._record_update_announcement(normalized, source_peer_id):
                known.add(key)

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
        if self.config.gossip_port > 0:
            return int(self.config.gossip_port)
        if self.config.peer_advertise_port > 0:
            return int(self.config.peer_advertise_port)
        if self.config.peer_http_port > 0:
            return int(self.config.peer_http_port)
        return 46101

    def _normalize_http_target(self, target: str) -> str:
        value = str(target or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme}://{parsed.netloc}{path}"
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
        if self.config.mesh_key and self.config.identity_dev_mesh_auth:
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
        signed_paths = [str(handler.path)]
        original_uri = str(handler.headers.get("X-Silicium-Original-URI", "")).strip()
        if original_uri.startswith("/") and len(original_uri) <= 4096 and original_uri not in signed_paths:
            signed_paths.append(original_uri)
        for signed_path in signed_paths:
            signing_payload = "\n".join([handler.command.upper(), signed_path, timestamp, body_hash, node_id, identity_id]).encode("utf-8")
            if NodeIdentity.verify_bytes(signing_payload, signature, public_key):
                return True
        return False

    def _start_http_server(self) -> None:
        peer_network = self

        class _PeerHandler(http.server.BaseHTTPRequestHandler):
            def _local_or_authorized(self, body: bytes = b"") -> bool:
                try:
                    if ipaddress.ip_address(str(self.client_address[0])).is_loopback:
                        return True
                except ValueError:
                    pass
                return peer_network._authorize_peer_request(self, body)

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
                if self.path == "/discovery/observe":
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    raw = stable_json(
                        {
                            "schema_version": 1,
                            "node_id": peer_network.node_id,
                            "observed_ip": str(self.client_address[0]),
                            "observed_port": int(self.client_address[1]),
                            "timestamp_unix": int(time.time()),
                        }
                    ).encode("utf-8")
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
                if self.path.startswith("/events/task-controls"):
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    query = parse_qs(urlparse(self.path).query)
                    try:
                        limit = int((query.get("limit") or ["2048"])[0])
                    except ValueError:
                        limit = 2048
                    raw = stable_json(
                        {
                            "schema_version": 1,
                            "node_id": peer_network.node_id,
                            "events": peer_network.recent_task_control_events(min(max(1, limit), 4096)),
                        }
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/p2p/sessions":
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    raw = stable_json(peer_network.sessions_snapshot()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/updates/manifest":
                    if not self._local_or_authorized():
                        self.send_error(403)
                        return
                    raw = stable_json(
                        {
                            "schema_version": 1,
                            "source": "silicium-gossip",
                            "node_id": peer_network.node_id,
                            "releases": peer_network.update_announcements(),
                        }
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path.startswith("/updates/content/"):
                    if not self._local_or_authorized():
                        self.send_error(403)
                        return
                    content_id = unquote(urlparse(self.path).path[len("/updates/content/") :]).strip()
                    try:
                        raw = peer_network.fetch_update_content(content_id)
                    except FileNotFoundError:
                        self.send_error(404)
                        return
                    except (OSError, ValueError):
                        self.send_error(502)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Cache-Control", "private, max-age=31536000, immutable")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/p2p/sessions/pending":
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    requester_node_id = safe_id(str(self.headers.get("X-Silicium-Node-Id", "")))
                    now = int(time.time())
                    with peer_network._lock:
                        sessions = [
                            peer_network._session_response(session)
                            for session in peer_network._sessions.values()
                            if requester_node_id
                            in {
                                safe_id(str(session.get("initiator_peer_id", ""))),
                                safe_id(str(session.get("target_peer_id", ""))),
                            }
                            and int(session.get("expires_unix", 0) or 0) > now
                            and str(session.get("status", "")) not in {"closed", "failed", "expired", "direct", "relay", "completed"}
                        ]
                    raw = stable_json({"ok": True, "sessions": sessions}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/p2p/transport":
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    raw = stable_json(peer_network.direct_transport_snapshot()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if self.path == "/p2p/attestations":
                    if not peer_network._authorize_peer_request(self):
                        self.send_error(403)
                        return
                    raw = stable_json(peer_network.transport_attestations_snapshot()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
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
                        target_peer = {}
                    data = None
                    for attempt in range(3):
                        data = peer_network._fetch_direct_from_peer(target_peer, content_id)
                        if data is not None:
                            break
                        try:
                            peer_network.sync_once()
                        except Exception:
                            pass
                        target_peer = peer_network._peers.get(peer_id, {})
                        if attempt < 2:
                            time.sleep(0.05)
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
                if self.path.startswith("/updates/cache/") and self._local_or_authorized(raw):
                    content_id = unquote(urlparse(self.path).path[len("/updates/cache/") :]).strip().lower()
                    if (
                        len(content_id) != 64
                        or any(char not in "0123456789abcdef" for char in content_id)
                        or len(raw) > 1024 * 1024 * 1024
                        or sha256_bytes(raw) != content_id
                    ):
                        self.send_error(400)
                        return
                    target = peer_network.export_dir / "p2p" / content_id
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_bytes(raw)
                    peer_network.publish(
                        "software_update_cached",
                        {"content_id": content_id, "size_bytes": len(raw), "cached_by": peer_network.node_id},
                    )
                    body = stable_json({"ok": True, "content_id": content_id}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
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
                if self.path == "/gossip/publish":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    topic = str(payload.get("topic", "")).strip() if isinstance(payload, dict) else ""
                    event_payload = payload.get("payload") if isinstance(payload, dict) else None
                    valid_software_update = (
                        topic == "software_update"
                        and peer_network._normalize_update_announcement(event_payload) is not None
                    )
                    valid_task_control = (
                        topic == "task_control"
                        and peer_network.node is not None
                        and peer_network.node.validate_task_control(event_payload, signed_by=peer_network.node_id)
                    )
                    if not valid_software_update and not valid_task_control:
                        self.send_error(400)
                        return
                    if valid_software_update:
                        peer_network._record_update_announcement(event_payload, peer_network.node_id)
                    else:
                        peer_network.node.apply_task_control(event_payload, signed_by=peer_network.node_id)
                    # The announcement is durable locally before this call. Fan-out may
                    # encounter slow/offline peers and must not hold the HTTP response.
                    peer_network.publish(topic, event_payload, background=True)
                    body = stable_json({"ok": True, "topic": topic}).encode("utf-8")
                    self.send_response(202)
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
                if self.path == "/p2p/peers/register":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    requester_node_id = safe_id(str(self.headers.get("X-Silicium-Node-Id", "")))
                    payload_node_id = safe_id(str(payload.get("node_id", "")))
                    if payload_node_id != requester_node_id:
                        body = stable_json({"ok": False, "error": "requester_mismatch"}).encode("utf-8")
                        self.send_response(403)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    peer_network._record_peer(payload)
                    body = stable_json({"ok": True, "peer_id": requester_node_id}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/p2p/candidates":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    requester_node_id = safe_id(str(self.headers.get("X-Silicium-Node-Id", "")))
                    payload_peer_id = safe_id(str(payload.get("peer_id", payload.get("node_id", ""))))
                    if payload_peer_id != requester_node_id:
                        body = stable_json({"ok": False, "error": "requester_mismatch"}).encode("utf-8")
                        self.send_response(403)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    peer_network._record_candidate_announce(payload)
                    candidates = peer_network._normalize_candidate_list(payload.get("candidates", []), requester_node_id)
                    body = stable_json({"ok": True, "peer_id": requester_node_id, "candidate_count": len(candidates)}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/p2p/sessions/request":
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    status, body_payload = peer_network.create_signaling_session(payload, str(self.headers.get("X-Silicium-Node-Id", "")))
                    session = body_payload.get("session") if isinstance(body_payload.get("session"), dict) else {}
                    if status == 201 and str(session.get("target_peer_id", "")) == peer_network.node_id:
                        local_ready = peer_network.build_session_ready_payload(session)
                        ready_status, ready_body = peer_network.mark_session_ready(str(session.get("session_id", "")), peer_network.node_id, local_ready)
                        if ready_status == 200:
                            body_payload = ready_body
                            punch_start = ready_body.get("punch_start") if isinstance(ready_body.get("punch_start"), dict) else {}
                            peer_network._start_direct_session_background(punch_start)
                    body = stable_json(body_payload).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.startswith("/p2p/sessions/"):
                    parts = [part for part in urlparse(self.path).path.split("/") if part]
                    if len(parts) != 4 or parts[0] != "p2p" or parts[1] != "sessions":
                        self.send_error(404)
                        return
                    session_id = parts[2]
                    action = parts[3]
                    try:
                        payload = json.loads(raw.decode("utf-8")) if raw else {}
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    requester_node_id = str(self.headers.get("X-Silicium-Node-Id", ""))
                    if action == "ready":
                        status, body_payload = peer_network.mark_session_ready(session_id, requester_node_id, payload)
                        ready_session = body_payload.get("session") if isinstance(body_payload.get("session"), dict) else {}
                        if status == 200 and str(ready_session.get("status", "")) == "punching" and str(ready_session.get("target_peer_id", "")) == peer_network.node_id:
                            peer_network._start_direct_session_background(body_payload.get("punch_start", {}))
                    elif action == "result":
                        status, body_payload = peer_network.record_session_result(session_id, payload, requester_node_id)
                    elif action == "close":
                        status, body_payload = peer_network.close_session(session_id, payload, requester_node_id)
                    else:
                        self.send_error(404)
                        return
                    body = stable_json(body_payload).encode("utf-8")
                    self.send_response(status)
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
                if self.path == "/tasks/claim":
                    try:
                        payload = json.loads(raw.decode("utf-8")) if raw else {}
                    except Exception:
                        self.send_error(400)
                        return
                    if not isinstance(payload, dict):
                        self.send_error(400)
                        return
                    requester_node_id = safe_id(str(payload.get("node_id", "") or self.headers.get("X-Silicium-Node-Id", "")))
                    roles = payload.get("roles", [])
                    if isinstance(roles, str):
                        roles = split_csv(roles)
                    roles_set = {str(r).lower() for r in roles if str(r).strip()}
                    if requester_node_id:
                        peer_network._record_peer(
                            {
                                "node_id": requester_node_id,
                                "identity_id": str(self.headers.get("X-Silicium-Identity-Id", "")),
                                "public_key": str(self.headers.get("X-Silicium-Public-Key", "")),
                                "roles": sorted(roles_set),
                                "features": payload.get("features", []),
                                "transport_attestations": payload.get("transport_attestations", []),
                                "http_base_url": payload.get("http_base_url", ""),
                                "mesh_post_url": payload.get("mesh_post_url", ""),
                                "gossip_bind": payload.get("gossip_bind", ""),
                                "gossip_port": payload.get("gossip_port", 0),
                                "candidates": payload.get("candidates", []),
                                "relay_capable": payload.get("relay_capable", False),
                                "capacity": payload.get("capacity", {}),
                                "reputation_score": payload.get("reputation_score", 0.0),
                                "resource_reputation": payload.get("resource_reputation", {}),
                                "app_version": payload.get("app_version", ""),
                                "release_channel": payload.get("release_channel", ""),
                                "release_build": payload.get("release_build", ""),
                                "timestamp_utc": utc_now(),
                            }
                        )
                    claim_features = {
                        str(feature).strip()
                        for feature in (payload.get("features", []) if isinstance(payload.get("features", []), list) else [])
                        if str(feature).strip()
                    }
                    claimed_envelope = (
                        peer_network.node.claim_task_for_worker(requester_node_id, roles_set, claim_features)
                        if peer_network.node
                        else None
                    )
                    if peer_network.node:
                        append_jsonl(
                            peer_network.node.events_path,
                            {
                                "schema_version": 1,
                                "timestamp_utc": utc_now(),
                                "node_id": peer_network.node.config.node_id,
                                "kind": "claim_request",
                                "worker_id": requester_node_id,
                                "roles": sorted(roles_set),
                                "app_version": str(payload.get("app_version", "")),
                                "release_channel": str(payload.get("release_channel", "")),
                                "release_build": str(payload.get("release_build", "")),
                                "claimed": isinstance(claimed_envelope, dict),
                                "item_id": safe_id(str((claimed_envelope or {}).get("request_id") or (claimed_envelope or {}).get("task_id") or "")),
                            },
                        )
                    body = stable_json({"ok": True, "task": claimed_envelope}).encode("utf-8")
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
                    ingest_content_blobs(peer_network.export_dir, payload)
                    enqueue_task_envelope(peer_network.export_dir, payload)
                    body = b'{"ok":true}'
                    self.send_response(202)
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
                    ingest_content_blobs(peer_network.export_dir, payload)
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
                    session_id = str(payload.get("session_id", "")).strip()
                    requester_handshake = payload.get("handshake")
                    requester_node_id = str(self.headers.get("X-Silicium-Node-Id", "")).strip()
                    ok, reason = peer_network.verify_session_handshake(
                        requester_handshake if isinstance(requester_handshake, dict) else None,
                        expected_peer_id=requester_node_id,
                        expected_target_peer_id=target_peer_id,
                    )
                    if not ok:
                        body = stable_json({"ok": False, "error": reason}).encode("utf-8")
                        self.send_response(403)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
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
                            "session_id": session_id,
                            "node_id": peer_network.node_id,
                            "identity_id": peer_network.identity.identity_id,
                            "public_key": peer_network.identity.public_key_b64,
                            "requester_handshake": requester_handshake,
                            "target_host": requester_host,
                            "target_port": requester_port,
                            "timestamp_utc": utc_now(),
                        }
                        peer_network._sign_message(probe_to_target)
                        peer_network._send_udp(f"{target_host}:{target_port}", target_host, target_port, probe_to_target)
                        probe_to_requester = {
                            "message_type": "punch_probe",
                            "session_id": session_id,
                            "node_id": peer_network.node_id,
                            "identity_id": peer_network.identity.identity_id,
                            "public_key": peer_network.identity.public_key_b64,
                            "requester_handshake": requester_handshake,
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
        self.advertised_http_base_url = (
            self.config.peer_advertise_url.strip().rstrip("/")
            or f"http://{self._advertised_http_host()}:{self._advertised_http_port()}"
        )
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
    final_path = tasks_dir / f"{safe_path_id(task_id)}.json"
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
    final_path = requests_dir / f"{safe_path_id(request_id)}.json"
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
        self._started_unix = time.time()
        self.state = QueueState(config.state_dir)
        node_path_id = safe_path_id(safe_id(config.node_id))
        self.reputation = ReputationStore(
            config.export_dir / f"node.{node_path_id}.reputation.json",
            initial_score=config.reputation_score,
            resource_profile=build_resource_profile(config.export_dir),
            short_half_life_s=config.short_half_life_s,
            long_half_life_s=config.long_half_life_s,
        )
        self.config.reputation_score = self.reputation.local_score()
        self.peer_network = PeerNetwork(config, config.export_dir)
        self.peer_network.node = self
        self.peer_network.set_peer_score_sink(self.reputation.set_peer_score)
        self.p2p = P2PClient(config.p2p_gateway, config.export_dir, self.peer_network)
        self.solana = SolanaBridge(config)
        self.runtime = RoleRuntime(config, self.p2p)
        self.events_path = config.export_dir / "node.events.ndjson"
        self.heartbeat_path = config.export_dir / f"node.{node_path_id}.heartbeat.json"
        self.metrics_path = config.export_dir / f"node.{node_path_id}.metrics.json"
        self.metrics = read_json(
            self.metrics_path,
            {"schema_version": 1, "handled": 0, "failed": 0, "retried": 0, "dead_lettered": 0, "dispatched": 0, "dispatch_failed": 0},
        )
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
        self._pull_thread: threading.Thread | None = None
        self._pull_stop_event = threading.Event()
        self._last_claim_poll_unix = 0.0
        self._last_claim_poll_utc = ""
        self._last_claim_error = ""
        self._last_claim_result = "not_started"
        self._last_claim_targets: list[dict[str, Any]] = []
        self._activity_lock = threading.Lock()
        self._active_tasks: list[dict[str, Any]] = []
        self._last_response: dict[str, Any] = {}
        self._task_queue_cache_lock = threading.Lock()
        self._task_queue_cache: list[dict[str, Any]] = []
        self._task_queue_cache_updated_monotonic = 0.0
        self._task_queue_cache_refreshing = False
        self.telemetry_sampler = RuntimeTelemetrySampler(config.export_dir)
        self._telemetry: dict[str, Any] = self.telemetry_sampler.sample()
        self._task_monitor_stop = threading.Event()
        self._task_monitor_thread: threading.Thread | None = None
        self._task_controls_lock = threading.Lock()
        self._task_controls: dict[str, dict[str, Any]] = {}
        self._task_controls_path = config.export_dir / "task-controls.ndjson"
        if self._task_controls_path.exists():
            for line in self._task_controls_path.read_text(encoding="utf-8").splitlines()[-2048:]:
                try:
                    control = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(control, dict) and str(control.get("control_id", "")).strip():
                    self._task_controls[str(control["control_id"])] = control
        self.peer_network.set_local_profile(
            capacity=self.runtime.capacity(),
            reputation_score=self.reputation.local_score(),
            resource_reputation=self.reputation.resource_snapshot(),
            activity=self.activity_snapshot(),
            task_queue=self.cached_task_queue_snapshot(),
        )

    def run(self) -> None:
        self.peer_network.start()
        if self.config.once and self.config.remote_dispatch_enable:
            # One-shot dispatch has no later convergence cycle to wait for.
            self.peer_network.sync_once()
        if self.config.pull_tasks_enable:
            self._start_pull_tasks_loop()
        try:
            self.bootstrap()
            self.refresh_local_onchain_profile(force=True)
            while True:
                self.write_heartbeat()
                handled = self.sweep()
                self.state.save()
                self.write_metrics()
                self.write_heartbeat()
                if self.config.once:
                    return
                if handled == 0:
                    time.sleep(max(0, self.config.idle_ms) / 1000.0)
        finally:
            self._stop_pull_tasks_loop()
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
        
        uptime_seconds = time.time() - self._started_unix
        peer_count = len(self.peer_network.sessions_snapshot())
        self.reputation.observe_uptime(uptime_seconds, peer_count, self_reported_only=True)
        
        capacity = self.runtime.capacity()
        current_reputation = self.reputation.local_score()
        resource_reputation = self.reputation.resource_snapshot()
        self._telemetry = self.telemetry_sampler.sample()
        task_queue = self.cached_task_queue_snapshot()
        self.config.reputation_score = current_reputation
        self.peer_network.set_local_profile(
            capacity=capacity,
            reputation_score=current_reputation,
            resource_reputation=resource_reputation,
            onchain_reputation=self._solana_onchain_reputation,
            onchain_global_reputation=self._solana_onchain_reputation,
            onchain_compute_reputation=getattr(self, "_solana_onchain_compute_reputation", 0.0),
            onchain_verify_reputation=getattr(self, "_solana_onchain_verify_reputation", 0.0),
            onchain_storage_reputation=getattr(self, "_solana_onchain_storage_reputation", 0.0),
            onchain_stake_amount=getattr(self, "_solana_onchain_stake_amount", 0.0),
            onchain_status=getattr(self, "_solana_onchain_status", ""),
            solana_owner=self._solana_owner,
            solana_worker=self._solana_worker,
            activity=self.activity_snapshot(),
            task_queue=task_queue,
        )
        p2p_candidates = self.peer_network.candidate_diagnostics()
        p2p_sessions = self.peer_network.sessions_snapshot()
        p2p_direct_sessions = self.peer_network.direct_sessions_snapshot()
        atomic_write_json(
            self.heartbeat_path,
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "timestamp_utc": utc_now(),
                "roles": sorted(self.config.roles),
                "app_version": self.config.app_version,
                "release_channel": self.config.release_channel,
                "release_build": self.config.release_build,
                "capacity": capacity,
                "reputation_score": current_reputation,
                "resource_reputation": resource_reputation,
                "peer_http_base_url": self.peer_network.http_base_url,
                "peer_public_base_url": self.peer_network.advertised_http_base_url,
                "peer_count": int(self.peer_network.peers_snapshot().get("count", 0)),
                "gossip_enabled": self.config.gossip_enable,
                "peer_sync_interval_s": self.config.peer_sync_interval_s,
                "mesh_auth_enabled": bool(self.config.mesh_key),
                "identity_id": self.peer_network.identity.identity_id,
                "relay_enabled": self.config.relay_enable,
                "p2p_candidate_count": p2p_candidates["candidate_count"],
                "p2p_candidate_types": p2p_candidates["candidate_types"],
                "p2p_selected_candidate": p2p_candidates["selected_candidate"],
                "p2p_observed_public_address": p2p_candidates["observed_public_address"],
                "p2p_nat_behavior": p2p_candidates["nat_behavior"],
                "p2p_session_count": int(p2p_sessions.get("count", 0) or 0),
                "p2p_direct_session_count": int(p2p_direct_sessions.get("count", 0) or 0),
                "p2p_transport_attestations": self.peer_network.recent_transport_attestations(8),
                "last_claim_poll_unix": self._last_claim_poll_unix,
                "last_claim_poll_utc": self._last_claim_poll_utc,
                "last_claim_error": self._last_claim_error,
                "last_claim_result": self._last_claim_result,
                "last_claim_targets": self._last_claim_targets,
                "activity": self.activity_snapshot(),
                "telemetry": self.telemetry_snapshot(),
                "task_queue": task_queue,
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
        self.metrics["runtime"] = self.telemetry_snapshot()
        atomic_write_json(self.metrics_path, self.metrics)

    def sweep(self) -> int:
        # World nodes act as schedulers.  Claim handlers own their queue
        # cursors, so a scheduler must not pre-scan these files in its main
        # loop or it would hide work from pull-based workers.
        if self.config.world:
            return 0
        handled = 0
        for queue in self.queue_order():
            for envelope in self.read_new(queue):
                key = self.envelope_key(envelope)
                if self.state.seen(key):
                    continue
                canonical = self.canonical_envelope(envelope)
                canonical_status = task_status(canonical.get("status"), default="")
                if canonical_status in {"running", "dispatched"} or task_status_is_terminal(canonical_status):
                    self._record_replay_skip(canonical, canonical_status)
                    self.state.mark_seen(key)
                    continue
                kind = str(canonical.get("envelope_kind") or "task")
                item_id = str(canonical.get("request_id") if kind == "request" else canonical.get("task_id", ""))
                control_origin = str(canonical.get("origin_node_id") or canonical.get("dispatched_by") or "")
                active_control = self.task_control_for(item_id, control_origin)
                if active_control is not None:
                    terminal_status = "cancelled" if active_control.get("action") == "cancel" else "expired"
                    self.update_envelope_status(canonical, terminal_status, {"task_control": active_control})
                    self._record_replay_skip(canonical, terminal_status)
                    self.state.mark_seen(key)
                    continue
                envelope = canonical
                if not self.accepts(envelope):
                    # A world node is the scheduler/broker.  It must retain
                    # work for pull-based workers instead of consuming and
                    # dead-lettering roles it does not execute itself.  The
                    # same applies while remote dispatch is disabled: another
                    # worker may still claim the canonical queued task.
                    if self.config.world or not self.config.remote_dispatch_enable:
                        continue
                    if self.try_remote_dispatch(envelope):
                        self.state.mark_seen(key)
                        handled += 1
                        if self.config.max_items > 0 and handled >= self.config.max_items:
                            return handled
                        continue
                    # Direct dispatch is only an optimisation.  With NATed
                    # workers it can fail even though the worker's regular
                    # /tasks/claim pull will succeed moments later.  Keep the
                    # canonical task pending rather than dead-lettering it.
                    continue
                self.handle(envelope)
                self.state.mark_seen(key)
                handled += 1
                if self.config.max_items > 0 and handled >= self.config.max_items:
                    return handled
        return handled

    def canonical_envelope(self, envelope: dict[str, Any]) -> dict[str, Any]:
        kind = str(envelope.get("envelope_kind") or "task")
        item_id = str(envelope.get("request_id") if kind == "request" else envelope.get("task_id", "")).strip()
        if not item_id:
            return envelope
        directory = "requests" if kind == "request" else "tasks"
        path = self.config.export_dir / directory / f"{safe_path_id(safe_id(item_id))}.json"
        current = read_json(path, {})
        if not isinstance(current, dict):
            return envelope
        current_id = str(current.get("request_id") if kind == "request" else current.get("task_id", "")).strip()
        return current if current_id == item_id else envelope

    def _record_replay_skip(self, envelope: Mapping[str, Any], status: str) -> None:
        kind = str(envelope.get("envelope_kind") or "task")
        item_id = str(envelope.get("request_id") if kind == "request" else envelope.get("task_id", ""))
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "queue_replay_skipped",
                "item_id": safe_id(item_id),
                "status": status,
            },
        )

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

    def task_activity(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(envelope.get("envelope_kind") or "task")
        body_key = "request" if kind == "request" else "task"
        body = envelope.get(body_key) if isinstance(envelope.get(body_key), Mapping) else {}
        roles = envelope.get("target_roles", []) if kind == "request" else envelope.get("required_roles", [])
        role = str(roles[0]) if isinstance(roles, list) and roles else str(body.get("kind", kind))
        item_id = str(envelope.get("request_id") if kind == "request" else envelope.get("task_id", ""))
        return {
            "item_id": safe_id(item_id),
            "kind": kind,
            "role": role.lower(),
            "activity": str(body.get("kind", role or kind)).lower(),
            "workload": str(body.get("workload", "")),
            "fragment_index": body.get("fragment_index", envelope.get("fragment_index", "")),
            "fragment_count": body.get("fragment_count", envelope.get("fragment_count", "")),
            "source_task_id": str(body.get("source_task_id", "")),
            "source_node_id": str(body.get("source_node_id", "")),
            "origin_node_id": str(envelope.get("origin_node_id") or envelope.get("dispatched_by") or ""),
            "x_start": body.get("x_start", ""),
            "x_end": body.get("x_end", ""),
            "y_start": body.get("y_start", ""),
            "y_end": body.get("y_end", ""),
            "started_utc": str(envelope.get("started_utc", "")),
        }

    def activity_snapshot(self) -> dict[str, Any]:
        with self._activity_lock:
            active_tasks = [dict(item) for item in self._active_tasks]
            last_response = dict(self._last_response)
        return {
            "status": "working" if active_tasks else "idle",
            "active_tasks": active_tasks,
            "last_response": last_response,
            "telemetry": self.telemetry_snapshot(),
        }

    def telemetry_snapshot(self) -> dict[str, Any]:
        return dict(self._telemetry)

    def update_active_task(self, **updates: Any) -> None:
        with self._activity_lock:
            if self._active_tasks:
                self._active_tasks[0].update(updates)

    def validate_task_control(self, payload: Any, *, signed_by: str) -> bool:
        if not isinstance(payload, dict):
            return False
        root_job_id = str(payload.get("root_job_id", "")).strip()
        action = str(payload.get("action", "")).strip().lower()
        issuer = str(payload.get("issuer_node_id", "")).strip()
        control_id = str(payload.get("control_id", "")).strip()
        return bool(
            root_job_id
            and control_id
            and action in {"cancel", "expire"}
            and issuer
            and safe_id(issuer) == safe_id(signed_by)
        )

    def apply_task_control(self, payload: dict[str, Any], *, signed_by: str) -> bool:
        if not self.validate_task_control(payload, signed_by=signed_by):
            return False
        control = dict(payload)
        root_job_id = safe_id(str(control["root_job_id"]))
        control["root_job_id"] = root_job_id
        control["signed_by"] = safe_id(signed_by)
        control["received_utc"] = utc_now()
        with self._task_controls_lock:
            if str(control["control_id"]) in self._task_controls:
                return True
            self._task_controls[str(control["control_id"])] = control
        append_jsonl(self._task_controls_path, control)

        matched_active = False
        with self._activity_lock:
            for activity in self._active_tasks:
                item_id = safe_id(str(activity.get("item_id", "")))
                origin_raw = str(activity.get("origin_node_id", "")).strip()
                origin = safe_id(origin_raw) if origin_raw else ""
                authorized = origin == safe_id(signed_by) if origin else safe_id(signed_by) == self.config.node_id
                if authorized and (item_id == root_job_id or item_id.startswith(root_job_id + "-")):
                    activity.update(
                        {
                            "phase": "cancelling",
                            "cancel_reason": str(control.get("reason", "")),
                            "control_id": str(control.get("control_id", "")),
                        }
                    )
                    matched_active = True
        if matched_active:
            self.runtime.cancel_task(str(control.get("reason", "task cancelled")))

        def sweep_task_directories() -> None:
            pattern = f"{safe_path_id(root_job_id)}*.json"
            for directory in (self.config.export_dir / "tasks", self.config.export_dir / "requests"):
                if not directory.exists():
                    continue
                for item_path in directory.glob(pattern):
                    envelope = read_json(item_path, {})
                    if not isinstance(envelope, dict):
                        continue
                    item_id = safe_id(str(envelope.get("task_id") or envelope.get("request_id") or ""))
                    origin_raw = str(envelope.get("origin_node_id") or envelope.get("dispatched_by") or "").strip()
                    origin = safe_id(origin_raw) if origin_raw else ""
                    if item_id != root_job_id and not item_id.startswith(root_job_id + "-"):
                        continue
                    if origin != safe_id(signed_by) and not (not origin and safe_id(signed_by) == self.config.node_id):
                        continue
                    self.update_envelope_status(
                        envelope,
                        "cancelled" if str(control.get("action")) == "cancel" else "expired",
                        {"task_control": control},
                    )

        threading.Thread(
            target=sweep_task_directories,
            name=f"silicium-task-control-sweep-{safe_path_id(root_job_id)}",
            daemon=True,
        ).start()
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "task_control",
                "item_id": root_job_id,
                "action": str(control.get("action")),
                "control_id": str(control.get("control_id")),
                "signed_by": safe_id(signed_by),
            },
        )
        self.publish_runtime_state(announce=True)
        return True

    def task_control_for(self, item_id: str, origin_node_id: str = "") -> dict[str, Any] | None:
        normalized = safe_id(item_id)
        origin_raw = str(origin_node_id).strip()
        origin = safe_id(origin_raw) if origin_raw else ""
        with self._task_controls_lock:
            controls = list(self._task_controls.values())
        for control in reversed(controls):
            root_job_id = safe_id(str(control.get("root_job_id", "")))
            signed_by = safe_id(str(control.get("signed_by") or control.get("issuer_node_id") or ""))
            authorized = signed_by == origin if origin else signed_by == self.config.node_id
            if authorized and (normalized == root_job_id or normalized.startswith(root_job_id + "-")):
                return dict(control)
        return None

    def build_compute_receipt(
        self,
        envelope: dict[str, Any],
        result: dict[str, Any],
        performance: dict[str, Any],
        *,
        started_utc: str,
        finished_utc: str,
    ) -> dict[str, Any]:
        task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
        role = str(result.get("role_result", "")).strip().lower()
        width = max(0, int(task.get("x_end", 0) or 0) - int(task.get("x_start", 0) or 0))
        height = max(0, int(task.get("y_end", 0) or 0) - int(task.get("y_start", 0) or 0))
        unit = "deterministic_operation"
        work_units = 0
        if role == "compute" and width > 0 and height > 0:
            unit = "rendered_pixel"
            work_units = width * height
        elif role == "verify" and isinstance(result.get("verification"), dict):
            verification = result["verification"]
            sample_width = max(
                0,
                int(verification.get("sample_x_end", 0) or 0)
                - int(verification.get("sample_x_start", 0) or 0),
            )
            sample_rows = max(0, int(verification.get("sample_rows", 0) or 0))
            unit = "verified_pixel"
            work_units = sample_width * sample_rows
        unsigned = {
            "schema": "silicium.compute-receipt.v1",
            "task_id": safe_id(str(envelope.get("task_id", ""))),
            "root_job_id": safe_id(str(task.get("root_job_id") or task.get("job_id") or "")),
            "worker_node_id": self.config.node_id,
            "role": role or "delegation",
            "workload": str(task.get("workload", "")),
            "billable_work_units": work_units,
            "unit": unit,
            "task_hash": sha256_json(task),
            "result_hash": str(result.get("result_hash", "")),
            "started_utc": started_utc,
            "finished_utc": finished_utc,
            "performance": performance,
        }
        receipt_hash = sha256_json(unsigned)
        return {
            **unsigned,
            "receipt_hash": receipt_hash,
            "worker_identity_id": self.peer_network.identity.identity_id,
            "worker_public_key": self.peer_network.identity.public_key_b64,
            "worker_signature": self.peer_network.identity.sign_bytes(stable_json(unsigned).encode("utf-8")),
        }

    def _task_progress_monitor(
        self,
        progress_path: Path,
        *,
        started_monotonic: float,
        timeout_seconds: int,
    ) -> None:
        sequence = 0
        while not self._task_monitor_stop.wait(1.0):
            sequence += 1
            self._telemetry = self.telemetry_sampler.sample()
            elapsed = max(0.0, time.monotonic() - started_monotonic)
            progress = read_json(progress_path, {})
            updates: dict[str, Any] = {
                "elapsed_ms": round(elapsed * 1000),
                "resource_usage": self.telemetry_snapshot(),
                "telemetry_sequence": sequence,
                "updated_utc": utc_now(),
            }
            if isinstance(progress, dict) and progress.get("schema") == "silicium.task-progress.v1":
                updates.update(
                    {
                        "phase": str(progress.get("phase", "executing")),
                        "progress_percent": max(
                            0.0, min(100.0, float(progress.get("progress_percent", 0.0) or 0.0))
                        ),
                        "progress_source": "measured",
                        "completed_units": float(progress.get("completed_units", 0.0) or 0.0),
                        "total_units": float(progress.get("total_units", 0.0) or 0.0),
                        "unit": str(progress.get("unit", "")),
                        "throughput_units_per_second": float(
                            progress.get("throughput_units_per_second", 0.0) or 0.0
                        ),
                        "eta_seconds": float(progress.get("eta_seconds", 0.0) or 0.0),
                        "worker_threads": int(progress.get("threads", 0) or 0),
                        "pixels_completed": int(progress.get("pixels_completed", 0) or 0),
                        "pixels_total": int(progress.get("pixels_total", 0) or 0),
                    }
                )
            else:
                estimated = min(
                    90.0,
                    10.0 + 80.0 * elapsed / max(1.0, float(timeout_seconds)),
                )
                updates.update(
                    {
                        "progress_percent": estimated,
                        "progress_source": "estimated",
                        "eta_seconds": max(0.0, timeout_seconds - elapsed),
                    }
                )
            self.update_active_task(**updates)
            self.peer_network.set_local_profile(activity=self.activity_snapshot())
            if sequence % 2 == 0:
                self.write_metrics()
                self.write_heartbeat()
                self.peer_network.announce()

    def task_queue_snapshot(self, limit: int = 64) -> list[dict[str, Any]]:
        items: list[tuple[float, dict[str, Any]]] = []
        for directory in (self.config.export_dir / "tasks", self.config.export_dir / "requests"):
            if not directory.exists():
                continue
            for item_path in directory.glob("*.json"):
                envelope = read_json(item_path, {})
                if not isinstance(envelope, dict):
                    continue
                status = task_status(envelope.get("status"))
                if task_status_is_terminal(status):
                    continue
                summary = self.task_activity(envelope)
                summary.update(
                    {
                        "status": status,
                        "priority": str(envelope.get("priority", "normal")),
                        "assigned_peer_id": str(
                            envelope.get("dispatched_to")
                            or envelope.get("assigned_peer_id")
                            or envelope.get("target_peer_id")
                            or ""
                        ),
                        "origin_node_id": str(envelope.get("origin_node_id") or envelope.get("dispatched_by") or ""),
                        "queued_utc": str(envelope.get("queued_utc") or envelope.get("created_utc") or ""),
                    }
                )
                try:
                    modified = item_path.stat().st_mtime
                except OSError:
                    modified = 0.0
                items.append((modified, summary))
        items.sort(key=lambda item: (-item[0], str(item[1].get("item_id", ""))))
        return [summary for _, summary in items[: max(1, int(limit))]]

    def cached_task_queue_snapshot(
        self,
        limit: int = 64,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return queue telemetry without blocking task execution on disk scans."""
        now = time.monotonic()
        with self._task_queue_cache_lock:
            cached = [dict(item) for item in self._task_queue_cache[: max(1, int(limit))]]
            stale = force_refresh or (now - self._task_queue_cache_updated_monotonic) >= 60.0
            if not stale or self._task_queue_cache_refreshing:
                return cached
            self._task_queue_cache_refreshing = True

        def refresh() -> None:
            try:
                snapshot = self.task_queue_snapshot(limit=64)
                with self._task_queue_cache_lock:
                    self._task_queue_cache = snapshot
                    self._task_queue_cache_updated_monotonic = time.monotonic()
            finally:
                with self._task_queue_cache_lock:
                    self._task_queue_cache_refreshing = False

        threading.Thread(
            target=refresh,
            name="silicium-task-queue-snapshot",
            daemon=True,
        ).start()
        return cached

    def remember_task_queue_envelope(self, envelope: dict[str, Any]) -> None:
        status = task_status(envelope.get("status"))
        item_id = safe_id(str(envelope.get("request_id") or envelope.get("task_id") or ""))
        if not item_id:
            return
        with self._task_queue_cache_lock:
            self._task_queue_cache = [
                item
                for item in self._task_queue_cache
                if safe_id(str(item.get("item_id", ""))) != item_id
            ]
            if task_status_is_terminal(status):
                return
            summary = self.task_activity(envelope)
            summary.update(
                {
                    "status": status,
                    "priority": str(envelope.get("priority", "normal")),
                    "assigned_peer_id": str(
                        envelope.get("dispatched_to")
                        or envelope.get("assigned_peer_id")
                        or envelope.get("target_peer_id")
                        or ""
                    ),
                    "origin_node_id": str(
                        envelope.get("origin_node_id") or envelope.get("dispatched_by") or ""
                    ),
                    "queued_utc": str(envelope.get("queued_utc") or envelope.get("created_utc") or ""),
                }
            )
            self._task_queue_cache.insert(0, summary)
            del self._task_queue_cache[64:]

    def publish_runtime_state(self, *, announce: bool = False) -> None:
        self.peer_network.set_local_profile(
            activity=self.activity_snapshot(),
            task_queue=self.cached_task_queue_snapshot(),
        )
        if announce:
            threading.Thread(
                target=self.peer_network.announce,
                name="silicium-peer-announce",
                daemon=True,
            ).start()

    def handle(self, envelope: dict[str, Any]) -> None:
        started = time.monotonic()
        start_telemetry = self.telemetry_sampler.sample()
        kind = str(envelope.get("envelope_kind") or "task")
        active = self.task_activity(envelope)
        active["started_utc"] = utc_now()
        body_key = "request" if kind == "request" else "task"
        body = envelope.get(body_key) if isinstance(envelope.get(body_key), dict) else {}
        item_id_for_control = str(envelope.get("request_id") or envelope.get("task_id") or "")
        control_origin = str(envelope.get("origin_node_id") or envelope.get("dispatched_by") or "")
        existing_control = self.task_control_for(item_id_for_control, control_origin)
        if existing_control is not None:
            self.update_envelope_status(
                envelope,
                "cancelled" if existing_control.get("action") == "cancel" else "expired",
                {"task_control": existing_control},
            )
            return
        self.runtime.begin_task()
        timeout_seconds = max(1, int(body.get("timeout_s", 300) or 300))
        progress_path = self.config.export_dir / f"task-progress.{safe_path_id(active['item_id'])}.json"
        envelope["_runtime_progress_path"] = str(progress_path)
        active.update(
            {
                "phase": "accepted",
                "progress_percent": 0.0,
                "progress_source": "measured",
                "elapsed_ms": 0,
                "eta_seconds": float(timeout_seconds),
                "completed_units": 0.0,
                "total_units": 0.0,
                "unit": "",
                "throughput_units_per_second": 0.0,
                "worker_threads": 0,
                "pixels_completed": 0,
                "pixels_total": 0,
                "attempt": int(envelope.get("attempt", 0) or 0),
                "max_retries": int(self.config.max_retries),
                "priority": str(envelope.get("priority", "normal")),
                "queued_utc": str(envelope.get("queued_utc") or envelope.get("created_utc") or ""),
                "resource_usage": start_telemetry,
            }
        )
        with self._activity_lock:
            self._active_tasks = [active]
        self._task_monitor_stop.clear()
        self._task_monitor_thread = threading.Thread(
            target=self._task_progress_monitor,
            args=(progress_path,),
            kwargs={"started_monotonic": started, "timeout_seconds": timeout_seconds},
            name=f"silicium-task-telemetry-{safe_path_id(active['item_id'])}",
            daemon=True,
        )
        self._task_monitor_thread.start()
        self.update_envelope_status(envelope, "running", {})
        self.remember_task_queue_envelope({**envelope, "status": "running"})
        self.publish_runtime_state(announce=True)
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
        self._task_monitor_stop.set()
        if self._task_monitor_thread is not None:
            self._task_monitor_thread.join(timeout=2.0)
        end_telemetry = self.telemetry_sampler.sample()
        self._telemetry = end_telemetry
        performance = {
            "duration_ms": duration_ms,
            "process_cpu_seconds": round(
                max(
                    0.0,
                    float(end_telemetry.get("process_cpu_seconds", 0.0) or 0.0)
                    - float(start_telemetry.get("process_cpu_seconds", 0.0) or 0.0),
                ),
                3,
            ),
            "process_peak_rss_bytes": int(end_telemetry.get("process_peak_rss_bytes", 0) or 0),
            "system_cpu_percent": float(end_telemetry.get("system_cpu_percent", 0.0) or 0.0),
            "system_memory_percent": float(end_telemetry.get("system_memory_percent", 0.0) or 0.0),
            "logical_cpu_count": int(end_telemetry.get("logical_cpu_count", 0) or 0),
        }
        finished_utc = utc_now()
        result.update(
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "roles": sorted(self.config.roles),
                "finished_utc": finished_utc,
                "duration_ms": duration_ms,
                "performance": performance,
            }
        )
        compute_receipt = self.build_compute_receipt(
            envelope,
            result,
            performance,
            started_utc=str(active.get("started_utc", "")),
            finished_utc=finished_utc,
        )
        result["compute_receipt"] = compute_receipt
        if str(result.get("role_result", "")).strip().lower() == "verify":
            accepted_receipt_hash = str(body.get("compute_receipt_hash", "")).strip()
            attestation_unsigned = {
                "schema": "silicium.receipt-attestation.v1",
                "task_id": safe_id(str(envelope.get("task_id", ""))),
                "compute_receipt_hash": accepted_receipt_hash,
                "accepted": bool(result.get("choice", result.get("verified", False))),
                "verifier_node_id": self.config.node_id,
                "finished_utc": finished_utc,
            }
            result["receipt_attestation"] = {
                **attestation_unsigned,
                "verifier_identity_id": self.peer_network.identity.identity_id,
                "verifier_public_key": self.peer_network.identity.public_key_b64,
                "verifier_signature": self.peer_network.identity.sign_bytes(
                    stable_json(attestation_unsigned).encode("utf-8")
                ),
            }
        safe_item = safe_id(item_id)
        path_item = safe_path_id(safe_item)
        log_payload = {"schema_version": 1, "item_id": safe_item, "ok": ok, "error": error, "duration_ms": duration_ms}
        atomic_write_json(self.config.export_dir / f"result.{path_item}.json", result)
        atomic_write_json(self.config.export_dir / f"logs.{path_item}.json", log_payload)
        active_control = self.task_control_for(item_id, control_origin)
        cancelled = active_control is not None or error.startswith("task_cancelled:")
        timed_out = error.startswith("task_timeout:")
        terminal_status = (
            "cancelled"
            if cancelled
            else "expired"
            if timed_out
            else "completed"
            if ok
            else "failed"
        )
        self.update_envelope_status(envelope, terminal_status, result)
        self.remember_task_queue_envelope({**envelope, "status": terminal_status})
        if ok:
            self.metrics["handled"] = int(self.metrics.get("handled", 0) or 0) + 1
        elif not cancelled and not timed_out:
            self.metrics["failed"] = int(self.metrics.get("failed", 0) or 0) + 1
            self.schedule_retry_or_dead_letter(envelope, error)
        elif timed_out:
            timeout_control = {
                "control_id": f"{safe_item}-expire-{int(time.time() * 1000)}",
                "root_job_id": safe_item,
                "action": "expire",
                "reason": error,
                "issuer_node_id": self.config.node_id,
                "issued_utc": utc_now(),
            }
            self.apply_task_control(timeout_control, signed_by=self.config.node_id)
            self.peer_network.publish("task_control", timeout_control, background=True)
        self.metrics["duration_total_ms"] = int(self.metrics.get("duration_total_ms", 0) or 0) + duration_ms
        self.metrics["duration_max_ms"] = max(int(self.metrics.get("duration_max_ms", 0) or 0), duration_ms)
        self.metrics["last_duration_ms"] = duration_ms
        handled_total = max(1, int(self.metrics.get("handled", 0) or 0) + int(self.metrics.get("failed", 0) or 0))
        self.metrics["duration_average_ms"] = round(
            int(self.metrics.get("duration_total_ms", 0) or 0) / handled_total, 2
        )
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
        # Return the authoritative result before best-effort gossip. A slow or
        # unreachable peer must never delay the scheduler from advancing the
        # job to verification or to the next fragment.
        self.return_dispatched_result(envelope, result, log_payload)
        if ok and kind == "task":
            self.peer_network.publish(
                "fragment_result",
                {
                    "item_id": safe_item,
                    "result_hash": result.get("result_hash", ""),
                    "proof_ref": result.get("proof_ref", {}),
                },
                background=True,
            )
            if str(result.get("role_result", "")).strip().lower() == "verify":
                self.peer_network.publish(
                    "worker_handoff",
                    {
                        "item_id": safe_item,
                        "source_task_id": str(body.get("source_task_id", "")),
                        "compute_node_id": str(body.get("source_node_id", "")),
                        "verify_node_id": self.config.node_id,
                        "content_id": str(
                            (body.get("source_output_ref") or {}).get("content_id", "")
                            if isinstance(body.get("source_output_ref"), dict)
                            else ""
                        ),
                        "receipt_hash": str(body.get("compute_receipt_hash", "")),
                        "verified": bool(result.get("choice", result.get("verified", False))),
                    },
                    background=True,
                )
        self.update_reputation(ok, kind, result)
        if ok and result.get("on_chain"):
            self.refresh_local_onchain_profile(force=True)
        with self._activity_lock:
            completed_activity = dict(self._active_tasks[0]) if self._active_tasks else dict(active)
            self._active_tasks = []
            self._last_response = {
                **completed_activity,
                "ok": ok,
                "error": error,
                "duration_ms": duration_ms,
                "progress_percent": 100.0 if ok else completed_activity.get("progress_percent", 0.0),
                "phase": terminal_status,
                "timestamp_utc": utc_now(),
                "performance": performance,
            }
        try:
            progress_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.publish_runtime_state(announce=True)

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
        role = str(result.get("role_result", "")).strip().lower()
        if role not in {"compute", "verify", "storage"}:
            role = "delegation"
        integrity_violation = bool(result.get("integrity_violation") or result.get("proof_invalid") or result.get("hash_mismatch"))
        event_class = "integrity" if integrity_violation else ("verified" if ok else "transient")
        self.reputation.observe_resource(role, ok, event_class=event_class)
        input_metadata = result.get("input") if isinstance(result.get("input"), dict) else {}
        if str(input_metadata.get("source", "")).startswith("silicium-"):
            self.reputation.observe_resource("connection", ok, event_class="verified" if ok else "transient", weight=0.5)
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
        excluded_peer_ids = {
            optional_peer_id(value)
            for value in (envelope.get("excluded_peer_ids", []) if isinstance(envelope.get("excluded_peer_ids"), list) else [])
        }
        excluded_peer_ids.discard("")
        peer = self.peer_network.select_peers(
            required_roles={str(role).lower() for role in required_roles},
            limit=1,
            exclude={self.config.node_id, *excluded_peer_ids},
            constraints=_peer_constraints(body, envelope),
        )
        if not peer:
            self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
            return False
        payload = dict(envelope)
        payload["dispatch_hops"] = dispatch_hops + 1
        payload["dispatched_by"] = self.config.node_id
        payload["dispatched_utc"] = utc_now()
        payload["result_return_url"] = self.peer_network.advertised_http_base_url.rstrip("/") + "/results/dispatch"
        base_urls = []
        primary_url = str(peer[0].get("http_base_url", "")).rstrip("/")
        if primary_url:
            base_urls.append(primary_url)
        for cand in peer[0].get("candidates", []):
            if isinstance(cand, dict) and cand.get("ip") and cand.get("port"):
                ip = str(cand["ip"])
                port = cand["port"]
                formatted_ip = f"[{ip}]" if ":" in ip else ip
                cand_url = f"http://{formatted_ip}:{port}".rstrip("/")
                if cand_url not in base_urls:
                    base_urls.append(cand_url)

        if not base_urls:
            self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
            return False

        path = "/requests/dispatch" if kind == "request" else "/tasks/dispatch"
        raw = stable_json(payload).encode("utf-8")

        ok = False
        dispatched_url = ""
        for base_url in base_urls:
            request = urllib.request.Request(
                base_url + path,
                data=raw,
                method="POST",
                headers=self.peer_network._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    if response.status in {200, 202}:
                        ok = True
                        dispatched_url = base_url
                        break
            except Exception:
                continue
        if ok:
            self.metrics["dispatched"] = int(self.metrics.get("dispatched", 0) or 0) + 1
            item_id = str(envelope.get("request_id") or envelope.get("task_id") or "unknown")
            safe_item = safe_id(item_id)
            self.update_envelope_status(envelope, "dispatched", {"result_hash": "", "dispatched_to": peer[0].get("node_id", "")})
            append_jsonl(
                self.events_path,
                {
                    "schema_version": 1,
                    "timestamp_utc": utc_now(),
                    "node_id": self.config.node_id,
                    "kind": "dispatch",
                    "item_id": safe_item,
                    "target_peer": peer[0].get("node_id", ""),
                    "roles": required_roles,
                },
            )
            return True
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
        content_blobs: list[dict[str, str]] = []
        seen_content: set[str] = set()
        # A NATed worker can POST its result to the scheduler but cannot in
        # general accept a later inbound HTTP fetch of its P2P content. Attach
        # bounded result artifacts to that already-authenticated return so the
        # scheduler becomes a durable, reachable content source.
        for ref_name in ("output_ref", "proof_ref"):
            ref = result.get(ref_name)
            if not isinstance(ref, dict):
                continue
            candidates = [ref]
            shared_ref = ref.get("shared_ref")
            if isinstance(shared_ref, dict):
                candidates.append(shared_ref)
            for candidate in candidates:
                content_id = str(candidate.get("content_id", "")).strip()
                if content_id in seen_content or len(content_id) != 64 or any(char not in "0123456789abcdef" for char in content_id.lower()):
                    continue
                content_path = self.config.export_dir / "p2p" / content_id
                try:
                    content = content_path.read_bytes()
                except OSError:
                    continue
                if len(content) > 16 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != content_id:
                    continue
                content_blobs.append({"content_id": content_id, "data_b64": base64.b64encode(content).decode("ascii")})
                seen_content.add(content_id)
                break
        payload = {
            "schema_version": 1,
            "item_id": safe_item,
            "envelope_kind": str(envelope.get("envelope_kind") or "task"),
            "result": result,
            "log": log_payload,
            "handled_by": self.config.node_id,
            "status": "completed" if bool(result.get("success", True)) else "failed",
        }
        if content_blobs:
            payload["content_blobs"] = content_blobs
        raw = stable_json(payload).encode("utf-8")
        path = urlparse(return_url).path or "/results/dispatch"
        request = urllib.request.Request(
            return_url,
            data=raw,
            method="POST",
            headers=self.peer_network._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        http_status = 0
        error = ""
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                http_status = int(response.status)
                ok = http_status in {200, 202}
        except (urllib.error.URLError, OSError) as exc:
            ok = False
            error = str(exc)
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
                "http_status": http_status,
                "error": error,
                "return_url": return_url,
            },
        )

    def ingest_content_blobs(self, payload: dict[str, Any]) -> list[str]:
        return ingest_content_blobs(self.config.export_dir, payload)

    def ingest_dispatched_result(self, payload: dict[str, Any]) -> None:
        item_id = safe_id(str(payload.get("item_id", "")))
        if not item_id:
            raise ValueError("missing_item_id")
        path_item = safe_path_id(item_id)
        result = payload.get("result")
        log_payload = payload.get("log")
        if not isinstance(result, dict) or not isinstance(log_payload, dict):
            raise ValueError("missing_result_payload")
        self.ingest_content_blobs(payload)
        kind = str(payload.get("envelope_kind") or "task")
        atomic_write_json(self.config.export_dir / f"result.{path_item}.json", result)
        atomic_write_json(self.config.export_dir / f"logs.{path_item}.json", log_payload)
        target_dir = self.config.export_dir / ("requests" if kind == "request" else "tasks")
        envelope_path = target_dir / f"{path_item}.json"
        current = read_json(envelope_path, {})
        if not isinstance(current, dict):
            current = {}
        current["status"] = str(payload.get("status", "completed"))
        current["handled_by"] = str(payload.get("handled_by", result.get("node_id", "")))
        current["handled_utc"] = utc_now()
        current["result_hash"] = result.get("result_hash") or result.get("input_hash", "")
        current["result_resource"] = f"resources://silicium/results/by-task/{item_id}"
        atomic_write_json(envelope_path, current)
        emit_rpc_event(
            self.config.export_dir,
            "task.terminal",
            item_id,
            status=current["status"],
            handled_by=current["handled_by"],
            result_hash=str(current.get("result_hash", "")),
            result_resource=current["result_resource"],
        )
        self.return_dispatched_result(current, result, log_payload)
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "result_ingest",
                "item_id": item_id,
                "source_node": str(payload.get("handled_by", result.get("node_id", ""))),
            },
        )

    def claim_task_for_worker(
        self,
        worker_id: str,
        worker_roles: set[str],
        worker_features: set[str] | None = None,
    ) -> dict[str, Any] | None:
        if not worker_id or not worker_roles:
            return None
        worker_features = worker_features or set()

        def preferred_worker(
            current: Mapping[str, Any],
            required_roles: set[str],
            excluded_peer_ids: set[str],
        ) -> str:
            now = int(time.time())
            compatible: set[str] = set()
            for peer in self.peer_network.peers_snapshot().get("peers", []):
                if not isinstance(peer, dict):
                    continue
                peer_id = optional_peer_id(peer.get("node_id", ""))
                if not peer_id or peer_id in excluded_peer_ids or peer.get("self"):
                    continue
                last_seen = int(peer.get("last_seen_unix", 0) or 0)
                if last_seen <= 0 or now - last_seen > 45:
                    continue
                roles = {
                    str(role).lower()
                    for role in peer.get("roles", [])
                    if str(role).strip()
                }
                if required_roles and not required_roles.issubset(roles):
                    continue
                required_features = {
                    str(feature).strip()
                    for feature in (current.get("required_features", []) if isinstance(current.get("required_features", []), list) else [])
                    if str(feature).strip()
                }
                body = current.get("request" if str(current.get("envelope_kind") or "task") == "request" else "task")
                if isinstance(body, Mapping):
                    required_features.update(
                        str(feature).strip()
                        for feature in (body.get("required_features", []) if isinstance(body.get("required_features", []), list) else [])
                        if str(feature).strip()
                    )
                peer_features = {str(feature).strip() for feature in peer.get("features", []) if str(feature).strip()}
                if not required_features.issubset(peer_features):
                    continue
                compatible.add(peer_id)

            safe_worker_id = safe_id(worker_id)
            if safe_worker_id not in excluded_peer_ids and (
                not required_roles or required_roles.issubset(worker_roles)
            ):
                compatible.add(safe_worker_id)
            ordered = sorted(compatible)
            if len(ordered) <= 1:
                return ordered[0] if ordered else ""

            body_key = "request" if str(current.get("envelope_kind") or "task") == "request" else "task"
            body = current.get(body_key) if isinstance(current.get(body_key), Mapping) else {}
            fragment_index = body.get("fragment_index", current.get("fragment_index"))
            try:
                slot = int(fragment_index)
            except (TypeError, ValueError):
                item_id = str(current.get("request_id") or current.get("task_id") or "")
                role_key = ",".join(sorted(required_roles))
                slot = int(sha256_bytes(f"{item_id}|{role_key}".encode("utf-8"))[:16], 16)
            return ordered[slot % len(ordered)]

        def try_claim(envelope: dict[str, Any]) -> dict[str, Any] | None:
            """Claim one canonical pending envelope for a compatible worker."""
            kind = str(envelope.get("envelope_kind") or "task")
            item_id = str(envelope.get("request_id") if kind == "request" else envelope.get("task_id", ""))
            if not item_id:
                return None
            item_path = self.config.export_dir / ("requests" if kind == "request" else "tasks") / f"{safe_path_id(safe_id(item_id))}.json"
            # Queue files are append-only. A stale in-memory marker must not
            # hide a task whose canonical state is still pending after an
            # interrupted claim.
            current = read_json(item_path, envelope)
            if not isinstance(current, dict):
                current = envelope
            status = task_status(current.get("status"), default="")
            if status == "dispatched" or task_status_is_terminal(status):
                return None
            control_origin = str(current.get("origin_node_id") or current.get("dispatched_by") or "")
            active_control = self.task_control_for(item_id, control_origin)
            if active_control is not None:
                self.update_envelope_status(
                    current,
                    "cancelled" if active_control.get("action") == "cancel" else "expired",
                    {"task_control": active_control},
                )
                append_jsonl(
                    self.events_path,
                    {
                        "schema_version": 1,
                        "timestamp_utc": utc_now(),
                        "node_id": self.config.node_id,
                        "kind": "claim_rejected_task_control",
                        "item_id": safe_id(item_id),
                        "control_id": str(active_control.get("control_id", "")),
                    },
                )
                return None
            assigned_raw = str(current.get("assigned_peer_id", "") or current.get("target_peer_id", "")).strip()
            assigned_peer_id = safe_id(assigned_raw) if assigned_raw else ""
            if assigned_peer_id and assigned_peer_id != safe_id(worker_id):
                return None
            excluded_peer_ids = {
                safe_id(str(value))
                for value in (current.get("excluded_peer_ids", []) if isinstance(current.get("excluded_peer_ids"), list) else [])
                if str(value).strip()
            }
            required_roles = current.get("target_roles", []) if kind == "request" else current.get("required_roles", [])
            if not isinstance(required_roles, list):
                required_roles = []
            req_set = {str(role).lower() for role in required_roles if str(role).strip()}
            if req_set and not req_set.issubset(worker_roles):
                return None
            body = current.get("request" if kind == "request" else "task")
            required_features = {
                str(feature).strip()
                for feature in (current.get("required_features", []) if isinstance(current.get("required_features", []), list) else [])
                if str(feature).strip()
            }
            if isinstance(body, Mapping):
                required_features.update(
                    str(feature).strip()
                    for feature in (body.get("required_features", []) if isinstance(body.get("required_features", []), list) else [])
                    if str(feature).strip()
                )
            # Older job controllers may exclude the compute worker because a
            # legacy verifier is merely visible.  If that verifier cannot
            # satisfy the required capability, permit the compatible compute
            # worker rather than leave verification permanently queued.
            if required_features and safe_id(worker_id) in excluded_peer_ids:
                excluded_peer_ids.discard(safe_id(worker_id))
            if safe_id(worker_id) in excluded_peer_ids:
                return None
            if not required_features.issubset(worker_features):
                return None
            selected_worker = preferred_worker(current, req_set, excluded_peer_ids)
            if selected_worker and selected_worker != safe_id(worker_id):
                return None

            key = self.envelope_key(current)
            dispatch_hops = int(current.get("dispatch_hops", 0) or 0)
            payload = dict(current)
            payload["dispatch_hops"] = dispatch_hops + 1
            payload["dispatched_by"] = self.config.node_id
            payload["dispatched_to"] = worker_id
            payload["dispatched_utc"] = utc_now()
            origin_return_url = str(current.get("origin_result_return_url", "")).strip()
            payload["result_return_url"] = origin_return_url if origin_return_url.startswith(("http://", "https://")) else self.peer_network.advertised_http_base_url.rstrip("/") + "/results/dispatch"

            self.update_envelope_status(current, "dispatched", {"result_hash": "", "dispatched_to": worker_id})
            emit_rpc_event(
                self.config.export_dir,
                "task.claimed",
                item_id,
                worker_id=worker_id,
                required_roles=sorted(req_set),
            )
            self.state.mark_seen(key)
            self.metrics["dispatched"] = int(self.metrics.get("dispatched", 0) or 0) + 1
            append_jsonl(
                self.events_path,
                {
                    "schema_version": 1,
                    "timestamp_utc": utc_now(),
                    "node_id": self.config.node_id,
                    "kind": "claim_dispatch",
                    "item_id": safe_id(str(current.get("request_id") or current.get("task_id") or "unknown")),
                    "target_peer": worker_id,
                    "roles": sorted(worker_roles),
                },
            )
            return payload

        with self.peer_network._lock:
            for queue_path in self.queue_order():
                for envelope in self.read_new(queue_path):
                    if not isinstance(envelope, dict):
                        continue
                    claimed = try_claim(envelope)
                    if claimed is not None:
                        return claimed

            # Queue cursors are persisted across restarts. If a cursor was
            # advanced while a prior process died before dispatching, recover
            # from the authoritative task files instead of leaving work stuck
            # forever in compute_queued. Oldest files are attempted first.
            for directory in (self.config.export_dir / "tasks", self.config.export_dir / "requests"):
                if not directory.exists():
                    continue
                # The append-only queue is authoritative for new work. The
                # directory scan is only crash recovery; bounding it to the
                # newest entries prevents thousands of historical results from
                # turning every worker claim into an O(total-history) pause.
                recovery_paths = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:1024]
                for item_path in recovery_paths:
                    envelope = read_json(item_path, {})
                    if not isinstance(envelope, dict):
                        continue
                    claimed = try_claim(envelope)
                    if claimed is not None:
                        return claimed
        return None

    def _start_pull_tasks_loop(self) -> None:
        self._pull_stop_event.clear()

        def _loop() -> None:
            interval = max(0.25, float(self.config.pull_tasks_interval_s))
            while not self._pull_stop_event.wait(interval):
                try:
                    self._poll_and_claim_tasks_once()
                except Exception:
                    pass

        self._pull_thread = threading.Thread(target=_loop, name=f"silicium-pull-tasks-{self.config.node_id}", daemon=True)
        self._pull_thread.start()

    def _stop_pull_tasks_loop(self) -> None:
        self._pull_stop_event.set()
        if self._pull_thread is not None:
            self._pull_thread.join(timeout=1)
            self._pull_thread = None

    def _poll_and_claim_tasks_once(self) -> None:
        targets: set[str] = set()
        for seed in self.config.seed_peers + self.config.discovery_seeds:
            normalized = self.peer_network._normalize_http_target(seed)
            if normalized and normalized != self.peer_network.advertised_http_base_url:
                targets.add(normalized)

        polled_at = utc_now()
        attempts: list[dict[str, Any]] = []
        claimed_item_id = ""
        candidates = self.peer_network.refresh_candidates()
        raw_payload = stable_json({
            "node_id": self.config.node_id,
            "roles": sorted(self.config.roles),
            "app_version": self.config.app_version,
            "release_channel": self.config.release_channel,
            "release_build": self.config.release_build,
            "features": sorted({*self.peer_network.direct_transport.features(), "raytracer_fastpath_v1"}),
            "transport_attestations": self.peer_network.recent_transport_attestations(4),
            "http_base_url": self.peer_network.advertised_http_base_url,
            "mesh_post_url": self.peer_network.mesh_post_url,
            "gossip_bind": self.peer_network._advertised_gossip_host(),
            "gossip_port": self.peer_network._advertised_gossip_port(),
            "candidates": candidates,
            "relay_capable": bool(self.config.relay_enable),
            "capacity": build_capacity_snapshot(self.config),
            "reputation_score": self.reputation.local_score(),
            "resource_reputation": self.reputation.resource_snapshot(),
        }).encode("utf-8")

        for base_url in sorted(targets):
            # Signaling and task-control anti-entropy run in the peer-sync
            # loop. Doing either synchronously in the claim hot path makes a
            # stale peer (or TURN endpoint) block dispatch for several seconds.
            path = "/tasks/claim"
            url = base_url.rstrip("/") + path
            attempt: dict[str, Any] = {"target": base_url, "url": url, "result": "unknown"}
            request = urllib.request.Request(
                url,
                data=raw_payload,
                method="POST",
                headers=self.peer_network._signed_headers("POST", path, raw_payload, {"Content-Type": "application/json"}),
            )
            try:
                with urllib.request.urlopen(request, timeout=1.5) as response:
                    attempt["http_status"] = int(response.status)
                    response_raw = response.read()
                    payload = json.loads(response_raw.decode("utf-8"))
                    if not isinstance(payload, dict) or not bool(payload.get("ok")):
                        attempt["result"] = "invalid_response"
                    elif not isinstance(payload.get("task"), dict):
                        attempt["result"] = "no_task_available"
                    else:
                        claimed_task = payload["task"]
                        # The claim request just proved that this scheduler URL
                        # is reachable from the worker. Prefer that direct path
                        # for locally originated tasks instead of routing the
                        # result through a potentially slow public reverse
                        # proxy. Explicit origin callbacks are preserved.
                        if not str(claimed_task.get("origin_result_return_url", "")).strip():
                            claimed_task["result_return_url"] = base_url.rstrip("/") + "/results/dispatch"
                        kind = str(claimed_task.get("envelope_kind") or "task")
                        candidate_item_id = safe_id(
                            str(claimed_task.get("request_id") or claimed_task.get("task_id") or "unknown")
                        )
                        # Controls are reconciled by the background sync loop;
                        # do not add a blocking network round-trip here.
                        control_origin = str(
                            claimed_task.get("origin_node_id") or claimed_task.get("dispatched_by") or ""
                        )
                        active_control = self.task_control_for(candidate_item_id, control_origin)
                        if active_control is not None:
                            attempt["result"] = "rejected_task_control"
                            attempt["item_id"] = candidate_item_id
                            attempt["control_id"] = str(active_control.get("control_id", ""))
                        else:
                            self.ingest_content_blobs(claimed_task)
                            claimed_item_id = candidate_item_id
                            if kind == "request":
                                enqueue_request_envelope(self.config.export_dir, claimed_task)
                            else:
                                enqueue_task_envelope(self.config.export_dir, claimed_task)
                            self.remember_task_queue_envelope(claimed_task)
                            attempt["result"] = "claimed"
                            attempt["item_id"] = claimed_item_id
                            target_peer = next(
                                (
                                    peer
                                    for peer in self.peer_network.peers_snapshot().get("peers", [])
                                    if str(peer.get("http_base_url", "")).rstrip("/") == base_url.rstrip("/")
                                ),
                                {},
                            )
                            self.peer_network.record_transport_attestation(
                                route="central",
                                transport_backend="scheduler-http",
                                remote_peer_id=str(target_peer.get("node_id", "")),
                                proof_scope="task_delivery",
                                task_id=claimed_item_id,
                                content_sha256=sha256_bytes(response_raw),
                                size_bytes=len(response_raw),
                                endpoint=base_url,
                                success=True,
                            )
                            append_jsonl(
                                self.events_path,
                                {
                                    "schema_version": 1,
                                    "timestamp_utc": polled_at,
                                    "node_id": self.config.node_id,
                                    "kind": "claimed_task_received",
                                    "item_id": claimed_item_id,
                                    "from_seed": base_url,
                                },
                            )
            except urllib.error.HTTPError as error:
                attempt["result"] = "http_error"
                attempt["http_status"] = int(error.code)
                attempt["error"] = str(error.reason or error)
            except Exception as error:
                attempt["result"] = "request_error"
                attempt["error"] = f"{type(error).__name__}:{error}"
            attempts.append(attempt)

        errors = [f"{item.get('target')}: {item.get('error') or item.get('http_status')}" for item in attempts if item.get("result") in {"http_error", "request_error", "invalid_response"}]
        result = "claimed" if claimed_item_id else (str(attempts[0].get("result")) if attempts else "no_scheduler_target")
        self._last_claim_poll_unix = time.time()
        self._last_claim_poll_utc = polled_at
        self._last_claim_error = "; ".join(errors)
        self._last_claim_result = result
        self._last_claim_targets = attempts
        atomic_write_json(
            self.config.export_dir / "claim-poll.health.json",
            {
                "schema_version": 2,
                "timestamp_utc": polled_at,
                "node_id": self.config.node_id,
                "targets_count": len(targets),
                "roles": sorted(self.config.roles),
                "app_version": self.config.app_version,
                "release_channel": self.config.release_channel,
                "release_build": self.config.release_build,
                "result": result,
                "claimed_item_id": claimed_item_id,
                "last_error": self._last_claim_error,
                "attempts": attempts,
            },
        )
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": polled_at,
                "node_id": self.config.node_id,
                "kind": "claim_poll",
                "status": result,
                "item_id": claimed_item_id,
                "targets": attempts,
                "error": self._last_claim_error,
            },
        )

    def handle_task(self, envelope: dict[str, Any]) -> dict[str, Any]:
        task = dict(envelope.get("task")) if isinstance(envelope.get("task"), dict) else {}
        task["_runtime_progress_path"] = str(envelope.get("_runtime_progress_path", ""))
        self.update_active_task(phase="fetching_input", progress_percent=2.0, progress_source="measured")
        inline_input = task.get("inline_input")
        if isinstance(inline_input, dict):
            p2p_data = stable_json(inline_input).encode("utf-8")
            p2p_meta = {"source": "inline-task", "size_bytes": len(p2p_data)}
        else:
            p2p_data, p2p_meta = self.p2p.fetch(envelope.get("p2p_ref"))
        self.update_active_task(
            phase="executing",
            progress_percent=10.0,
            progress_source="estimated",
            input_bytes=len(p2p_data),
        )
        role_output = self.runtime.run_task(envelope, task, p2p_data, p2p_meta)
        self.update_active_task(phase="publishing_result", progress_percent=92.0)
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
        # Workloads such as raytracer publish their actual binary artifact.
        # Preserve that reference instead of replacing it with this JSON
        # manifest; downstream reassembly expects the PPM bytes themselves.
        output_ref = role_output.get("output_ref") if isinstance(role_output.get("output_ref"), dict) else None
        if output_ref is None:
            output_ref = self.p2p.put_local(stable_json(output).encode("utf-8"))
        self.update_active_task(phase="finalizing", progress_percent=98.0)
        output["output_ref"] = output_ref
        output["proof_ref"] = role_output.get("proof_ref") if isinstance(role_output.get("proof_ref"), dict) else output_ref
        on_chain = self.submit_task_on_chain(envelope, task, output, output_ref)
        if on_chain:
            output["on_chain"] = on_chain
        return output

    def handle_request(self, envelope: dict[str, Any]) -> dict[str, Any]:
        request = envelope.get("request") if isinstance(envelope.get("request"), dict) else {}
        self.update_active_task(phase="fetching_input", progress_percent=2.0, progress_source="measured")
        p2p_data, p2p_meta = self.p2p.fetch(envelope.get("p2p_ref"))
        self.update_active_task(
            phase="executing",
            progress_percent=10.0,
            progress_source="estimated",
            input_bytes=len(p2p_data),
        )
        request_kind = str(envelope.get("kind", "request"))
        role_response = self.runtime.run_request(envelope, request, p2p_data, p2p_meta)
        self.update_active_task(phase="publishing_result", progress_percent=92.0)
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
        self.update_active_task(phase="finalizing", progress_percent=98.0)
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
            path = self.config.export_dir / "requests" / f"{safe_path_id(item_id)}.json"
        else:
            item_id = safe_id(str(envelope.get("task_id", "")))
            path = self.config.export_dir / "tasks" / f"{safe_path_id(item_id)}.json"
        current = read_json(path, envelope)
        if not isinstance(current, dict):
            current = envelope
        current["status"] = status
        current["handled_by"] = self.config.node_id
        current["handled_utc"] = utc_now()
        current["result_hash"] = result.get("result_hash") or result.get("input_hash", "")
        current["result_resource"] = f"resources://silicium/results/by-task/{item_id}"
        if isinstance(result.get("task_control"), dict):
            current["task_control"] = dict(result["task_control"])
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
    parser.add_argument("--app-version", default=os.environ.get("SILICIUM_APP_VERSION", "unknown"))
    parser.add_argument("--release-channel", default=os.environ.get("SILICIUM_RELEASE_CHANNEL", "dev"), choices=["dev", "prod"])
    parser.add_argument("--release-build", default=os.environ.get("SILICIUM_RELEASE_BUILD", ""))
    parser.add_argument("--idle-ms", type=int, default=int(os.environ.get("SILICIUM_NODE_IDLE_MS", "250")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-items", type=int, default=int(os.environ.get("SILICIUM_NODE_MAX_ITEMS", "0")))
    parser.add_argument("--p2p-gateway", default=os.environ.get("SILICIUM_P2P_GATEWAY", "http://127.0.0.1:5001"))
    parser.add_argument("--state-dir", default="")
    parser.add_argument("--solana-enable", action="store_true", default=os.environ.get("SILICIUM_SOLANA_ENABLE", "0") == "1")
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument(
        "--solana-program-id",
        default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"),
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
    parser.add_argument("--peer-advertise-url", default=os.environ.get("SILICIUM_PEER_ADVERTISE_URL", ""))
    parser.add_argument("--peer-advertise-host", default=os.environ.get("SILICIUM_PEER_ADVERTISE_HOST", ""))
    parser.add_argument("--peer-advertise-port", type=int, default=int(os.environ.get("SILICIUM_PEER_ADVERTISE_PORT", "0")))
    parser.add_argument("--gossip-advertise-host", default=os.environ.get("SILICIUM_GOSSIP_ADVERTISE_HOST", ""))
    parser.add_argument("--gossip-advertise-port", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_ADVERTISE_PORT", "0")))
    parser.add_argument("--seed-peers", default=os.environ.get("SILICIUM_SEED_PEERS", ""))
    parser.add_argument("--mesh-key", default=os.environ.get("SILICIUM_MESH_KEY", ""))
    parser.add_argument("--peer-sync-interval-s", type=int, default=int(os.environ.get("SILICIUM_PEER_SYNC_INTERVAL_S", "15")))
    parser.add_argument("--peer-event-limit", type=int, default=int(os.environ.get("SILICIUM_PEER_EVENT_LIMIT", "128")))
    parser.add_argument("--gossip-max-hops", type=int, default=int(os.environ.get("SILICIUM_GOSSIP_MAX_HOPS", "8")))
    parser.add_argument("--peer-stale-after-s", type=int, default=int(os.environ.get("SILICIUM_PEER_STALE_AFTER_S", "300")))
    parser.add_argument("--relay-enable", action="store_true", default=os.environ.get("SILICIUM_RELAY_ENABLE", "0") == "1")
    parser.add_argument("--relay-hops", type=int, default=int(os.environ.get("SILICIUM_RELAY_HOPS", "2")))
    parser.add_argument("--identity-key-path", default=os.environ.get("SILICIUM_IDENTITY_KEY_PATH", ""))
    parser.add_argument(
        "--identity-dev-mesh-auth",
        action="store_true",
        default=os.environ.get("SILICIUM_IDENTITY_DEV_MESH_AUTH", "0") == "1",
        help="Allow bearer-only mesh-key HTTP auth for local development. Production peers must use signed identity headers.",
    )
    parser.add_argument("--reputation-score", type=float, default=float(os.environ.get("SILICIUM_REPUTATION_SCORE", "0")))
    parser.add_argument("--short-half-life-s", type=float, default=float(os.environ.get("SILICIUM_SHORT_HALF_LIFE_S", "3600")))
    parser.add_argument("--long-half-life-s", type=float, default=float(os.environ.get("SILICIUM_LONG_HALF_LIFE_S", "86400")))
    parser.add_argument("--replication-factor", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_FACTOR", "0")))
    parser.add_argument("--replication-quorum", type=int, default=int(os.environ.get("SILICIUM_REPLICATION_QUORUM", "0")))
    parser.add_argument("--discovery-seeds", default=os.environ.get("SILICIUM_DISCOVERY_SEEDS", ""))
    parser.add_argument("--discovery-sync-interval-s", type=int, default=int(os.environ.get("SILICIUM_DISCOVERY_SYNC_INTERVAL_S", "30")))
    parser.add_argument("--remote-dispatch-enable", action="store_true", default=os.environ.get("SILICIUM_REMOTE_DISPATCH_ENABLE", "0") == "1")
    parser.add_argument("--remote-dispatch-limit", type=int, default=int(os.environ.get("SILICIUM_REMOTE_DISPATCH_LIMIT", "3")))
    parser.add_argument("--pull-tasks-enable", action="store_true", default=os.environ.get("SILICIUM_PULL_TASKS_ENABLE", "0") == "1")
    parser.add_argument("--pull-tasks-interval-s", type=float, default=float(os.environ.get("SILICIUM_PULL_TASKS_INTERVAL_S", "0.25")))
    parser.add_argument("--nat-punch-enable", action="store_true", default=os.environ.get("SILICIUM_NAT_PUNCH_ENABLE", "0") == "1")
    parser.add_argument("--p2p-candidate-ttl-s", type=int, default=int(os.environ.get("SILICIUM_P2P_CANDIDATE_TTL_S", "60")))
    parser.add_argument("--p2p-candidate-refresh-s", type=int, default=int(os.environ.get("SILICIUM_P2P_CANDIDATE_REFRESH_S", "20")))
    parser.add_argument("--p2p-session-ttl-s", type=int, default=int(os.environ.get("SILICIUM_P2P_SESSION_TTL_S", "120")))
    parser.add_argument("--p2p-punch-retry-count", type=int, default=int(os.environ.get("SILICIUM_P2P_PUNCH_RETRY_COUNT", "8")))
    parser.add_argument("--p2p-punch-interval-ms", type=int, default=int(os.environ.get("SILICIUM_P2P_PUNCH_INTERVAL_MS", "120")))
    parser.add_argument("--p2p-session-timeout-ms", type=int, default=int(os.environ.get("SILICIUM_P2P_SESSION_TIMEOUT_MS", "2500")))
    parser.add_argument("--p2p-direct-transport-backend", default=os.environ.get("SILICIUM_P2P_DIRECT_TRANSPORT_BACKEND", "auto"))
    parser.add_argument("--p2p-stun-server", default=os.environ.get("SILICIUM_P2P_STUN_SERVER", ""))
    parser.add_argument("--p2p-turn-server", default=os.environ.get("SILICIUM_P2P_TURN_SERVER") or "turn:vps-910c1dbc.vps.ovh.net:3478")
    parser.add_argument("--p2p-turn-username", default=os.environ.get("SILICIUM_P2P_TURN_USERNAME", "silicium"))
    parser.add_argument("--p2p-turn-password", default=os.environ.get("SILICIUM_P2P_TURN_PASSWORD", os.environ.get("SILICIUM_MESH_KEY", "")))
    parser.add_argument("--p2p-turn-transport", default=os.environ.get("SILICIUM_P2P_TURN_TRANSPORT", "udp"), choices=["udp", "tcp"])
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
            args.identity_key_path = (Path(".silicium") / "world-identities" / safe_id(str(args.node_id)) / "ed25519.pem").as_posix()
    args = apply_nat_traversal_defaults(args)
    export_dir = Path(args.export_dir).expanduser().resolve()
    state_dir = Path(args.state_dir).expanduser().resolve() if args.state_dir else export_dir / "node-state" / safe_path_id(safe_id(args.node_id))
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
        peer_advertise_url=str(args.peer_advertise_url),
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
        identity_dev_mesh_auth=bool(args.identity_dev_mesh_auth),
        reputation_score=float(args.reputation_score),
        replication_factor=max(0, int(args.replication_factor)),
        replication_quorum=max(0, int(args.replication_quorum)),
        discovery_seeds=[item.strip() for item in str(args.discovery_seeds).split(",") if item.strip()],
        discovery_sync_interval_s=max(0, int(args.discovery_sync_interval_s)),
        remote_dispatch_enable=bool(args.remote_dispatch_enable),
        short_half_life_s=float(args.short_half_life_s),
        long_half_life_s=float(args.long_half_life_s),
        remote_dispatch_limit=max(1, int(args.remote_dispatch_limit)),
        pull_tasks_enable=bool(args.pull_tasks_enable),
        pull_tasks_interval_s=max(0.25, float(args.pull_tasks_interval_s)),
        app_version=str(args.app_version).strip() or "unknown",
        release_channel=str(args.release_channel).strip().lower() or "dev",
        release_build=str(args.release_build).strip(),
        gossip_max_hops=max(1, min(32, int(args.gossip_max_hops))),
        nat_punch_enable=bool(args.nat_punch_enable),
        p2p_candidate_ttl_s=max(1, int(args.p2p_candidate_ttl_s)),
        p2p_candidate_refresh_s=max(1, int(args.p2p_candidate_refresh_s)),
        p2p_session_ttl_s=max(1, int(args.p2p_session_ttl_s)),
        p2p_punch_retry_count=max(1, int(args.p2p_punch_retry_count)),
        p2p_punch_interval_ms=max(1, int(args.p2p_punch_interval_ms)),
        p2p_session_timeout_ms=max(1, int(args.p2p_session_timeout_ms)),
        p2p_direct_transport_backend=str(args.p2p_direct_transport_backend),
        p2p_stun_server=str(args.p2p_stun_server),
        p2p_turn_server=str(args.p2p_turn_server),
        p2p_turn_username=str(args.p2p_turn_username),
        p2p_turn_password=str(args.p2p_turn_password),
        p2p_turn_transport=str(args.p2p_turn_transport),
        solana_reputation_enable=bool(args.solana_reputation_enable),
        solana_reputation_refresh_s=max(1, int(args.solana_reputation_refresh_s)),
        scheduler_onchain_weight=float(args.scheduler_onchain_weight),
        scheduler_offchain_weight=float(args.scheduler_offchain_weight),
        scheduler_capacity_weight=float(args.scheduler_capacity_weight),
        world=bool(args.world),
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    NetworkNode(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
