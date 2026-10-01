"""Inbox for role-targeted post-job requests (audit, retrieval, challenge...).

Files written in the export directory:

- ``requests/<request_id>.json``      the request envelope;
- ``requests.queue.ndjson``           canonical queue;
- ``requests.urgent.ndjson``          copy of ``high``/``urgent`` requests;
- ``requests.<role>.queue.ndjson``    one copy per target role.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from .constants import MAX_ENVELOPE_BYTES, REQUEST_KINDS, RESOURCE_REQUEST_PREFIX
from .persistence import append_line, atomic_write_text, compact_json, utc_now
from .validation import (
    normalized_priority,
    normalized_roles,
    priority_rank,
    sanitize_task_id,
    validate_on_chain,
    validate_p2p_ref,
)

# Request kinds that point at content and therefore need a p2p_ref.
_KINDS_REQUIRING_P2P_REF = {"audit", "resource", "challenge", "replicate", "retrieve"}
_URGENT_PRIORITIES = {"high", "urgent"}


class McpRequestStore:
    """
    Fast post-job request inbox for audits, resource retrieval, replication,
    challenges, and other role-targeted messages.
    """

    def __init__(self, export_dir: Path) -> None:
        self._requests_dir = export_dir / "requests"
        self._queue_path = export_dir / "requests.queue.ndjson"
        self._urgent_path = export_dir / "requests.urgent.ndjson"
        self._lock = threading.Lock()
        self._requests_dir.mkdir(parents=True, exist_ok=True)

    def submit(self, args: Any) -> dict[str, Any]:
        """Validate, persist and enqueue a request; returns the acceptance summary."""
        payload = self._build_envelope(args)
        encoded = compact_json(payload)
        if len(encoded.encode("utf-8")) > MAX_ENVELOPE_BYTES:
            raise ValueError("request_too_large")

        with self._lock:
            self._persist_locked(payload, encoded)

        return {
            "status": "queued",
            "request_id": payload["request_id"],
            "kind": payload["kind"],
            "priority": payload["priority"],
            "target_roles": payload["target_roles"],
            "resource": RESOURCE_REQUEST_PREFIX + payload["request_id"],
            "queue": str(self._queue_path),
        }

    def _build_envelope(self, args: Any) -> dict[str, Any]:
        # Validation order is observable (first error wins), keep it stable.
        if not isinstance(args, dict):
            raise ValueError("args_not_object")
        request = args.get("request", args)
        if not isinstance(request, dict):
            raise ValueError("request_not_object")

        raw_request_id = args.get("request_id", request.get("request_id"))
        request_id = sanitize_task_id(str(raw_request_id)) if raw_request_id is not None else ""
        if not request_id:
            request_id = uuid.uuid4().hex

        kind = str(args.get("kind", request.get("kind", ""))).strip().lower()
        if kind not in REQUEST_KINDS:
            raise ValueError("unsupported_request_kind")
        priority = normalized_priority(args.get("priority", request.get("priority", "high")))
        target_roles = normalized_roles(
            args.get("target_roles", request.get("target_roles")),
            default=["audit" if kind == "audit" else "resource"],
        )
        p2p_ref = validate_p2p_ref(
            args.get("p2p_ref", request.get("p2p_ref")),
            required=kind in _KINDS_REQUIRING_P2P_REF,
        )
        on_chain = validate_on_chain(args.get("on_chain", request.get("on_chain")))

        payload = {
            "schema_version": 1,
            "envelope_kind": "request",
            "request_id": request_id,
            "kind": kind,
            "status": "queued",
            "submitted_utc": utc_now(),
            "priority": priority,
            "priority_rank": priority_rank(priority),
            "target_roles": target_roles,
            "target_worker": _text_field(args, request, "target_worker"),
            "job_id": _text_field(args, request, "job_id"),
            "fragment_id": _text_field(args, request, "fragment_id"),
            "p2p_ref": p2p_ref,
            "request": request,
        }
        if on_chain is not None:
            payload["on_chain"] = on_chain
        return payload

    def _persist_locked(self, payload: dict[str, Any], encoded: str) -> None:
        # Unlike tasks, any queue append failure propagates to the client.
        atomic_write_text(self._requests_dir / f"{payload['request_id']}.json", encoded)
        append_line(self._queue_path, encoded)
        if payload["priority"] in _URGENT_PRIORITIES:
            append_line(self._urgent_path, encoded)
        for role in payload["target_roles"]:
            append_line(self._queue_path.with_name(f"requests.{role}.queue.ndjson"), encoded)

    def read(self, request_id: str) -> str:
        """Return the raw JSON envelope of ``request_id``."""
        safe_request_id = sanitize_task_id(request_id)
        if not safe_request_id:
            raise FileNotFoundError("missing_request_id")
        return (self._requests_dir / f"{safe_request_id}.json").read_text(encoding="utf-8")


def _text_field(args: dict[str, Any], request: dict[str, Any], key: str) -> str:
    """Read an optional string field, top-level args taking precedence."""
    return str(args.get(key, request.get(key, ""))).strip()
