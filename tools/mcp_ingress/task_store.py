"""Durable ingress for tasks submitted to the network.

Files written in the export directory:

- ``tasks/<task_id>.json``          the task envelope (registry, rewritten on cancel);
- ``tasks.queue.ndjson``            canonical queue, one envelope per line;
- ``tasks.<role>.queue.ndjson``     per-role acceleration queue (first required role).

The network node (tools/network_node.py), the RPC server and the CLI consume
these files; their format is a contract.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from .constants import MAX_ENVELOPE_BYTES, RESOURCE_TASK_PREFIX
from .persistence import append_line, atomic_write_text, compact_json, utc_now
from .validation import (
    default_task_roles,
    normalized_priority,
    normalized_roles,
    priority_rank,
    sanitize_task_id,
    validate_on_chain,
    validate_p2p_ref,
)

# Authenticated scheduler routing metadata copied verbatim from the submission.
# These fields are consumed by pull-based workers and must survive local
# durable ingress.
_ROUTING_FIELDS = (
    "assigned_peer_id",
    "excluded_peer_ids",
    "origin_result_return_url",
    "requester_peer_id",
)

_RESPONSE_MODES = ("p2p_ref", "inline", "on_chain_ref")
_TERMINAL_STATUSES = {"completed", "failed", "dead_lettered", "cancelled"}


class McpTaskStore:
    """
    Durable ingress for network-submitted tasks.

    The HTTP/MCP server owns acceptance and persistence. Workers can consume
    tasks.queue.ndjson without needing clients to launch ad-hoc runner scripts.
    """

    def __init__(self, export_dir: Path) -> None:
        self._tasks_dir = export_dir / "tasks"
        self._queue_path = export_dir / "tasks.queue.ndjson"
        self._lock = threading.Lock()
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

    def submit(self, args: Any) -> dict[str, Any]:
        """Validate, persist and enqueue a task; returns the acceptance summary."""
        payload = self._build_envelope(args)
        task_id = payload["task_id"]
        required_roles = payload["required_roles"]
        encoded = compact_json(payload)
        if len(encoded.encode("utf-8")) > MAX_ENVELOPE_BYTES:
            raise ValueError("task_too_large")

        with self._lock:
            self._persist_locked(payload, encoded)

        return {
            "status": "queued",
            "task_id": task_id,
            "priority": payload["priority"],
            "required_roles": required_roles,
            "resource": RESOURCE_TASK_PREFIX + task_id,
            "queue": str(self._queue_path),
        }

    def _build_envelope(self, args: Any) -> dict[str, Any]:
        # Validation order is observable (first error wins), keep it stable.
        if not isinstance(args, dict):
            raise ValueError("args_not_object")
        raw_task_id = args.get("task_id")
        task_id = sanitize_task_id(str(raw_task_id)) if raw_task_id is not None else ""
        if not task_id:
            task_id = uuid.uuid4().hex

        # A submission is either {"task": {...}, ...} or the task object itself.
        task = args.get("task", args)
        if not isinstance(task, dict):
            raise ValueError("task_not_object")

        required_roles = normalized_roles(
            args.get("required_roles", task.get("required_roles")),
            default=default_task_roles(task),
        )
        priority = normalized_priority(args.get("priority", task.get("priority")))
        p2p_ref = validate_p2p_ref(args.get("p2p_ref", task.get("p2p_ref")), required=False)
        on_chain = validate_on_chain(args.get("on_chain", task.get("on_chain")))
        response_mode = str(args.get("response_mode", task.get("response_mode", "p2p_ref"))).strip().lower()
        if response_mode not in _RESPONSE_MODES:
            raise ValueError("unsupported_response_mode")

        payload = {
            "schema_version": 1,
            "envelope_kind": "task",
            "task_id": task_id,
            "status": "queued",
            "submitted_utc": utc_now(),
            "priority": priority,
            "priority_rank": priority_rank(priority),
            "required_roles": required_roles,
            "p2p_ref": p2p_ref,
            "response_mode": response_mode,
            "task": task,
        }
        for field in _ROUTING_FIELDS:
            if field in args:
                payload[field] = args[field]
        if on_chain is not None:
            payload["on_chain"] = on_chain
        return payload

    def _persist_locked(self, payload: dict[str, Any], encoded: str) -> None:
        final_path = self._tasks_dir / f"{payload['task_id']}.json"
        atomic_write_text(final_path, encoded)
        try:
            append_line(self._queue_path, encoded)
        except OSError as error:
            self._mark_ingress_failed(final_path, payload, error)
            raise
        self._append_role_queue(payload["required_roles"][0], encoded)

    def _mark_ingress_failed(self, final_path: Path, payload: dict[str, Any], error: OSError) -> None:
        # The scheduler recovers queued work from tasks/*.json when a
        # queue cursor is stale. Mark this registry entry terminal when
        # durable queue ingress is rejected, otherwise a worker can
        # execute work that the submitting job saw fail. Keeping the
        # terminal entry also protects against an append whose outcome
        # is uncertain (for example, an error raised while flushing).
        failed_payload = {
            **payload,
            "status": "failed",
            "failed_utc": utc_now(),
            "error_type": type(error).__name__,
            "error": f"queue_ingress_failed:{error}",
        }
        atomic_write_text(final_path, compact_json(failed_payload))

    def _append_role_queue(self, role: str, encoded: str) -> None:
        role_queue_path = self._queue_path.with_name(f"tasks.{role}.queue.ndjson")
        try:
            append_line(role_queue_path, encoded)
        except OSError:
            # The canonical queue already durably accepted the task. Role
            # queues are an acceleration path; workers also consume the
            # canonical queue, so reporting a submission failure here
            # would be incorrect and could trigger duplicate retries.
            pass

    def read(self, task_id: str) -> str:
        """Return the raw JSON envelope of ``task_id``."""
        safe_task_id = sanitize_task_id(task_id)
        if not safe_task_id:
            raise FileNotFoundError("missing_task_id")
        return (self._tasks_dir / f"{safe_task_id}.json").read_text(encoding="utf-8")

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return up to ``limit`` (clamped to 1..1000) envelopes, newest first."""
        entries: list[dict[str, Any]] = []
        paths = sorted(
            self._tasks_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for path in paths[: max(1, min(1000, int(limit)))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def cancel(self, task_id: str) -> dict[str, Any]:
        """Mark a not-yet-dispatched task as cancelled; terminal tasks are returned as is."""
        safe_task_id = sanitize_task_id(task_id)
        if not safe_task_id:
            raise FileNotFoundError("missing_task_id")
        path = self._tasks_dir / f"{safe_task_id}.json"
        with self._lock:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                raise
            if not isinstance(payload, dict):
                raise ValueError("task_invalid")
            status = str(payload.get("status", "")).strip().lower()
            if status in _TERMINAL_STATUSES:
                return payload
            if status == "dispatched":
                raise ValueError("task_already_dispatched")
            payload["status"] = "cancelled"
            payload["cancelled_utc"] = utc_now()
            atomic_write_text(path, compact_json(payload))
        return payload
