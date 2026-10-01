"""Role runtime: executes compute/storage/verify/resource tasks and requests."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any

from tools.node.config import NodeConfig, _peer_constraints, build_capacity_snapshot
from tools.node.p2p_client import P2PClient
from tools.node.util import sha256_bytes, sha256_json, stable_json
from workloads.registry import WorkloadContext, run_workload, unsupported_reason
from workloads.standard.handlers import hash_audit


class RoleRuntime:
    """Execute tasks/requests for the node's roles (workloads via the registry)."""

    def __init__(self, config: NodeConfig, p2p: P2PClient) -> None:
        self.config = config
        self.p2p = p2p
        self._cancel_event = threading.Event()
        self._cancel_reason = ""

    def begin_task(self) -> None:
        """Reset the cancellation state before a new task."""
        self._cancel_reason = ""
        self._cancel_event.clear()

    def cancel_task(self, reason: str) -> None:
        """Cancel the running subprocess (see ``run_process``)."""
        self._cancel_reason = str(reason or "task cancelled")
        self._cancel_event.set()

    def run_process(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        """Run a command, killing it on cancellation or timeout."""
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
        """Current capacity snapshot."""
        return build_capacity_snapshot(self.config)

    def run_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        """Route a task to the storage, verify, resource or compute runner."""
        roles = {str(role).lower() for role in envelope.get("required_roles", [])}
        task_kind = str(task.get("kind", task.get("type", ""))).strip().lower()
        if "storage" in roles or task_kind in {"storage", "store", "pin", "replicate"}:
            return self.run_storage_task(envelope, task, p2p_data, p2p_meta)
        if "verify" in roles or task_kind in {"verify", "verification"}:
            return self.run_verify_task(envelope, task, p2p_data, p2p_meta)
        if "resource" in roles or task_kind in {"resource", "health", "capacity"}:
            return self.run_resource_task(envelope, task, p2p_data, p2p_meta)
        return self.run_compute_task(envelope, task, p2p_data, p2p_meta)

    def _workload_context(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "task": task,
            "p2p_data": p2p_data,
            "p2p_meta": p2p_meta,
            "put_output": lambda data: self.p2p.put_local(data),
            "envelope": envelope,
            "fetch": lambda ref: self.p2p.fetch(ref),
            "run_process": self.run_process,
        }

    def run_compute_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        # Which workloads exist and how they run is declared by their manifests
        # (workloads/<category>/.../manifest.yaml, `runtime.handler`).
        """Run the task's workload, or report it unsupported."""
        workload = task.get("workload", "")
        result = run_workload(workload, "compute", self._workload_context(envelope, task, p2p_data, p2p_meta))
        if result is not None:
            return result
        compute_result = {
            "mode": "network-workload",
            "executed": False,
            "reason": unsupported_reason(workload),
        }
        material = {
            "task": task,
            "p2p_hash": sha256_bytes(p2p_data),
            "compute_result": compute_result,
        }
        return {
            "role_result": "compute",
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            "compute": compute_result,
            "result_hash": sha256_json(material),
        }

    def run_storage_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        """Store (and replicate) the input; return the storage manifest."""
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
        """Run the workload verifier, else a hash audit."""
        context = self._workload_context(envelope, task, p2p_data, p2p_meta)
        result = run_workload(task.get("workload", ""), "verify", context)
        if result is not None:
            return result
        # No dedicated verifier: compare hashes (verification/hash-audit/sha256).
        return hash_audit(WorkloadContext(workload="verification/hash-audit/sha256", **context))

    def run_resource_task(self, envelope: dict[str, Any], task: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        """Report this node's capacity."""
        capacity = self.capacity()
        return {
            "role_result": "resource",
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            "capacity": capacity,
            "result_hash": sha256_json(capacity),
        }

    def run_request(self, envelope: dict[str, Any], request: dict[str, Any], p2p_data: bytes, p2p_meta: dict[str, Any]) -> dict[str, Any]:
        """Answer health/pin/unpin/retrieve requests, else audit the input hash."""
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
