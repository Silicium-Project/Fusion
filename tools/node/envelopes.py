"""Queue envelopes on disk: enqueue tasks/requests and ingest inline content blobs."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.node.util import safe_id, safe_path_id


def ingest_content_blobs(export_dir: Path, payload: dict[str, Any]) -> list[str]:
    """Store verified inline ``content_blobs`` (<= 16 MiB in total) in ``p2p/``; return their ids."""
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


def enqueue_task_envelope(export_dir: Path, envelope: dict[str, Any]) -> None:
    """Write ``tasks/<id>.json`` and append the envelope to the task queues."""
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
    """Write ``requests/<id>.json`` and append the envelope to the request queues."""
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
