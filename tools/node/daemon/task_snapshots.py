"""Queue telemetry: per-task activity summaries and the cached queue snapshot."""

from __future__ import annotations

import threading
import time
from typing import Any, Mapping

from tools.node.util import read_json, safe_id, task_status, task_status_is_terminal


class TaskSnapshotsMixin:
    """Summarise queued work for heartbeats and peer announcements."""

    def task_activity(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        """Compact activity summary of an envelope (shown in heartbeats and peers)."""
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

    def _queue_summary(self, envelope: Mapping[str, Any], status: str) -> dict[str, Any]:
        """Activity summary of a queued envelope plus its queue fields."""
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
        return summary

    def task_queue_snapshot(self, limit: int = 64) -> list[dict[str, Any]]:
        """Scan task/request files: non-terminal items, most recently modified first."""
        self.reconcile_orphaned_running_tasks()
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
                summary = self._queue_summary(envelope, status)
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
        if force_refresh:
            return self._refresh_task_queue_cache_now(limit)

        now = time.monotonic()
        with self._task_queue_cache_lock:
            cached = [dict(item) for item in self._task_queue_cache[: max(1, int(limit))]]
            stale = (now - self._task_queue_cache_updated_monotonic) >= 5.0
            if not stale or self._task_queue_cache_refreshing:
                return cached
            refresh_generation = self._task_queue_cache_generation
            self._task_queue_cache_refreshing = True

        threading.Thread(
            target=self._refresh_task_queue_cache_background,
            args=(refresh_generation,),
            name="silicium-task-queue-snapshot",
            daemon=True,
        ).start()
        return cached

    def _refresh_task_queue_cache_now(self, limit: int) -> list[dict[str, Any]]:
        """Synchronous rescan, merged with in-memory updates made meanwhile."""
        with self._task_queue_cache_lock:
            refresh_generation = self._task_queue_cache_generation
            self._task_queue_cache_refreshing = True
        try:
            snapshot = self.task_queue_snapshot(limit=64)
        finally:
            with self._task_queue_cache_lock:
                self._task_queue_cache_refreshing = False
        with self._task_queue_cache_lock:
            if self._task_queue_cache_generation == refresh_generation:
                self._task_queue_cache = snapshot
            else:
                # Preserve an in-memory terminal/removal update that
                # happened while the disk scan was in flight.
                current = {
                    safe_id(str(item.get("item_id", ""))): dict(item)
                    for item in self._task_queue_cache
                    if str(item.get("item_id", "")).strip()
                }
                for item in snapshot:
                    current.setdefault(safe_id(str(item.get("item_id", ""))), dict(item))
                self._task_queue_cache = list(current.values())[:64]
            self._task_queue_cache_updated_monotonic = time.monotonic()
            return [dict(item) for item in self._task_queue_cache[: max(1, int(limit))]]

    def _refresh_task_queue_cache_background(self, refresh_generation: int) -> None:
        try:
            snapshot = self.task_queue_snapshot(limit=64)
            with self._task_queue_cache_lock:
                # A task can be remembered while the disk scan is in
                # flight. Do not let that older snapshot erase the newer
                # in-memory announcement.
                if self._task_queue_cache_generation == refresh_generation:
                    self._task_queue_cache = snapshot
                self._task_queue_cache_updated_monotonic = time.monotonic()
        finally:
            with self._task_queue_cache_lock:
                self._task_queue_cache_refreshing = False

    def remember_task_queue_envelope(self, envelope: dict[str, Any]) -> None:
        """Update the cached queue in memory (newest first, at most 64 items)."""
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
            self._task_queue_cache_generation += 1
            if task_status_is_terminal(status):
                return
            summary = self._queue_summary(envelope, status)
            self._task_queue_cache.insert(0, summary)
            del self._task_queue_cache[64:]
