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
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


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
    tmp = path.with_suffix(path.suffix + ".tmp")
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
    def __init__(self, gateway: str, export_dir: Path) -> None:
        self.gateway = gateway.rstrip("/")
        self.export_dir = export_dir

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

    def put_local(self, data: bytes) -> dict[str, Any]:
        digest = sha256_bytes(data)
        path = self.export_dir / "p2p" / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return {
            "protocol": "file",
            "content_id": str(path),
            "hash": "sha256:" + digest,
            "size_bytes": len(data),
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
        disk = shutil.disk_usage(self.config.export_dir)
        return {
            "node_id": self.config.node_id,
            "roles": sorted(self.config.roles),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count() or 1,
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
            "solana_enabled": self.config.solana_enable,
            "worker_binary": self.config.worker_binary,
            "worker_mode": self.config.worker_mode,
        }

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
        stored_ref = self.p2p.put_local(p2p_data if p2p_data else stable_json(task).encode("utf-8"))
        manifest = {
            "task_id": envelope.get("task_id", ""),
            "kind": "storage",
            "source": p2p_meta,
            "stored_ref": stored_ref,
            "replication_factor": int(task.get("replication_factor", 1) or 1),
        }
        manifest_ref = self.p2p.put_local(stable_json(manifest).encode("utf-8"))
        return {
            "role_result": "storage",
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            "stored_ref": stored_ref,
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
            return {"request_result": kind, "storage": self.p2p.pin(envelope.get("p2p_ref") or request.get("p2p_ref")), "choice": True}
        if kind == "unpin":
            return {"request_result": kind, "storage": self.p2p.unpin(envelope.get("p2p_ref") or request.get("p2p_ref")), "choice": True}
        if kind == "retrieve":
            stored = self.p2p.put_local(p2p_data)
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
        self.p2p = P2PClient(config.p2p_gateway, config.export_dir)
        self.solana = SolanaBridge(config)
        self.runtime = RoleRuntime(config, self.p2p)
        self.events_path = config.export_dir / "node.events.ndjson"
        self.heartbeat_path = config.export_dir / f"node.{safe_id(config.node_id)}.heartbeat.json"
        self.metrics_path = config.export_dir / f"node.{safe_id(config.node_id)}.metrics.json"
        self.metrics = read_json(self.metrics_path, {"schema_version": 1, "handled": 0, "failed": 0, "retried": 0, "dead_lettered": 0})

    def run(self) -> None:
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
        atomic_write_json(
            self.heartbeat_path,
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "timestamp_utc": utc_now(),
                "roles": sorted(self.config.roles),
                "capacity": self.runtime.capacity(),
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
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    NetworkNode(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
