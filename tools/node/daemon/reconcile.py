"""Fail tasks left running/dispatched after a crash or a lost worker."""

from __future__ import annotations

import time
from typing import Any

from tools.node.util import optional_peer_id, read_json, safe_id, task_status


class ReconcileMixin:
    """Reconcile orphaned running or dispatched tasks."""

    def reconcile_orphaned_running_tasks(self) -> None:
        """Close tasks left active after a crash or worker disconnect."""
        with self._activity_lock:
            active_ids = {
                safe_id(str(item.get("item_id", "")))
                for item in self._active_tasks
                if str(item.get("item_id", "")).strip()
            }
        self_id = safe_id(str(self.config.node_id))
        stale_after = int(self.config.peer_stale_after_s)
        live_peer_ids = self._live_peer_ids(self_id, stale_after)
        for directory in (self.config.export_dir / "tasks", self.config.export_dir / "requests"):
            if not directory.exists():
                continue
            for item_path in directory.glob("*.json"):
                envelope = read_json(item_path, {})
                if not isinstance(envelope, dict):
                    continue
                kind = str(envelope.get("envelope_kind") or "task")
                raw_item_id = str(
                    envelope.get("request_id") if kind == "request" else envelope.get("task_id", "")
                ).strip()
                item_id = safe_id(raw_item_id) if raw_item_id else ""
                if not item_id or item_id in active_ids:
                    continue
                result = self._orphan_failure(envelope, self_id, stale_after, live_peer_ids)
                if result is None:
                    continue
                self.update_envelope_status(envelope, "failed", result)
                self.remember_task_queue_envelope({**envelope, "status": "failed"})

    def _live_peer_ids(self, self_id: str, stale_after: int) -> set[str]:
        """This node plus every peer seen within the liveness window."""
        now = int(time.time())
        live_peer_ids = {self_id}
        for peer in self.peer_network.peers_snapshot().get("peers", []):
            if not isinstance(peer, dict):
                continue
            peer_id = safe_id(str(peer.get("node_id", "")))
            last_seen = int(peer.get("last_seen_unix", 0) or 0)
            if peer_id and (
                peer.get("self")
                or stale_after <= 0
                or (last_seen > 0 and now - last_seen <= stale_after)
            ):
                live_peer_ids.add(peer_id)
        return live_peer_ids

    def _orphan_failure(
        self,
        envelope: dict[str, Any],
        self_id: str,
        stale_after: int,
        live_peer_ids: set[str],
    ) -> dict[str, Any] | None:
        """Failure result for an orphaned running/dispatched envelope, else None."""
        status = task_status(envelope.get("status"))
        # optional_peer_id, not safe_id: safe_id("") returns a random
        # id, which made an unassigned running task look like a lost
        # remote worker and failed it.
        handled_by = optional_peer_id(envelope.get("handled_by"))
        assigned_worker = optional_peer_id(
            envelope.get("dispatched_to")
            or envelope.get("assigned_peer_id")
            or envelope.get("target_peer_id")
        )
        if status == "running":
            worker_id = handled_by or assigned_worker
            if worker_id == self_id:
                return {
                    "error": "task_interrupted",
                    "error_type": "TaskInterrupted",
                    "traceback": "The local node stopped before the task reached a terminal state.",
                }
            if not worker_id or stale_after <= 0 or worker_id in live_peer_ids:
                # A remote worker with a recent heartbeat may still be
                # running the task. Keep it visible until it goes stale.
                return None
            return {
                "error": "task_worker_lost",
                "error_type": "TaskWorkerLost",
                "traceback": f"The worker {worker_id} has not sent a heartbeat within the liveness window.",
            }
        if status == "dispatched":
            target_raw = str(
                envelope.get("dispatched_to") or envelope.get("assigned_peer_id") or ""
            ).strip()
            target_id = safe_id(target_raw) if target_raw else ""
            owner_id = handled_by or optional_peer_id(envelope.get("dispatched_by"))
            if not target_id:
                return {
                    "error": "task_dispatch_target_missing",
                    "error_type": "TaskDispatchTargetMissing",
                    "traceback": "The task is marked as dispatched but has no target worker.",
                }
            if owner_id != self.config.node_id or target_id in live_peer_ids:
                return None
            return {
                "error": "task_worker_lost",
                "error_type": "TaskWorkerLost",
                "traceback": f"The dispatched worker {target_id} has not sent a heartbeat within the liveness window.",
            }
        return None
