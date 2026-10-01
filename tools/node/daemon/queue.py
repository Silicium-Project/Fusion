"""Local queue sweep: read append-only queues, filter, execute or forward envelopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.node.util import (
    append_jsonl,
    atomic_write_json,
    read_json,
    safe_id,
    safe_path_id,
    task_status,
    task_status_is_terminal,
    utc_now,
)


class QueueMixin:
    """Consume the append-only queue files produced by the MCP ingress."""

    def sweep(self) -> int:
        # World nodes act as schedulers.  Claim handlers own their queue
        # cursors, so a scheduler must not pre-scan these files in its main
        # loop or it would hide work from pull-based workers.
        """Process newly appended envelopes; return how many were handled or forwarded."""
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
        """Current on-disk version of an envelope (queue lines may be stale)."""
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
        """Queue files by priority: urgent, retries, per-role requests, requests, tasks."""
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
        """Envelopes appended to ``path`` since the saved cursor (advances it)."""
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
        """Idempotency key: kind, id and attempt."""
        kind = str(envelope.get("envelope_kind") or "task")
        attempt = int(envelope.get("attempt", 0) or 0)
        if kind == "request":
            return f"request:{envelope.get('request_id', '')}:{attempt}"
        return f"task:{envelope.get('task_id', '')}:{attempt}"

    def accepts(self, envelope: dict[str, Any]) -> bool:
        """Whether this node's roles can execute the envelope."""
        kind = str(envelope.get("envelope_kind") or "task")
        if kind == "request":
            target_roles = set(str(role) for role in envelope.get("target_roles", []))
            return not target_roles or bool(target_roles.intersection(self.config.roles))
        required_roles = set(str(role) for role in envelope.get("required_roles", ["compute"]))
        return bool(required_roles.intersection(self.config.roles))

    def update_envelope_status(self, envelope: dict[str, Any], status: str, result: dict[str, Any]) -> None:
        """Write status, handler and result fields into the canonical envelope file."""
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
        for key in ("dispatched_to", "assigned_peer_id"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                current[key] = value.strip()
        for key in ("error", "error_type", "traceback"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                current[key] = value
        if isinstance(result.get("task_control"), dict):
            current["task_control"] = dict(result["task_control"])
        atomic_write_json(path, current)
