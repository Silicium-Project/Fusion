"""Scheduler side of pull-based work: atomic task claims for workers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from networked.networked_runtime import attach_network_content_blobs
from tools.node.util import (
    append_jsonl,
    optional_peer_id,
    read_json,
    safe_id,
    safe_path_id,
    sha256_bytes,
    task_status,
    task_status_is_terminal,
    utc_now,
)


@dataclass
class _ClaimBatch:
    """One claim request: the worker, its roles, the limit and what it got."""

    worker_id: str
    worker_roles: set[str]
    limit: int
    claimed_items: list[dict[str, Any]] = field(default_factory=list)
    claimed_ids: set[str] = field(default_factory=set)


class ClaimsMixin:
    """Reserve queued work for pull-based workers."""

    def claim_tasks_for_worker(
        self,
        worker_id: str,
        worker_roles: set[str],
        *,
        limit: int = 1,
    ) -> list[dict[str, Any]]:
        """Atomically reserve up to ``limit`` (1..32) compatible envelopes.

        Sources, in order: envelopes left pending by previous claims, the
        append-only queues (from their cursors), then - once per process -
        the canonical task/request files to recover work stranded by a crash.
        """
        if not worker_id or not worker_roles:
            return []

        requested_limit = max(1, min(32, int(limit)))
        batch = _ClaimBatch(worker_id, worker_roles, requested_limit)
        with self._task_claim_lock:
            pending = self._claim_pending_envelopes
            self._claim_pending_envelopes = []
            if self._consume_claim_envelopes(pending, batch):
                self._queue_recovery_attempted = True
                return batch.claimed_items
            for queue_path in self.queue_order():
                if self._consume_claim_envelopes(self.read_new(queue_path), batch):
                    # The append-only queues are authoritative while the
                    # process is alive. Do not rescan every canonical task
                    # file after a successful queue read: that recovery pass
                    # is only needed once after startup/crash recovery.
                    self._queue_recovery_attempted = True
                    return batch.claimed_items

            # Queue cursors are persisted across restarts. If a cursor was
            # advanced while a prior process died before dispatching, recover
            # from the authoritative task files instead of leaving work stuck
            # forever in compute_queued. Oldest files are attempted first.
            if self._queue_recovery_attempted or self._claim_pending_envelopes:
                return batch.claimed_items
            self._queue_recovery_attempted = True
            self._recover_claims_from_files(batch)
        return batch.claimed_items

    def _consume_claim_envelopes(self, envelopes: Iterable[dict[str, Any]], batch: _ClaimBatch) -> bool:
        """Claim compatible entries and retain unclaimable queue items.

        Returns True once the batch is full; the unread rest is kept pending.
        """
        materialized = list(envelopes)
        for index, envelope in enumerate(materialized):
            if not isinstance(envelope, dict):
                continue
            item_id = safe_id(
                str(envelope.get("request_id") or envelope.get("task_id") or "")
            )
            if not item_id or item_id in batch.claimed_ids:
                continue
            claimed = self._try_claim(envelope, batch)
            if claimed is None:
                self._claim_pending_envelopes.append(envelope)
                continue
            batch.claimed_items.append(claimed)
            batch.claimed_ids.add(item_id)
            if len(batch.claimed_items) >= batch.limit:
                self._claim_pending_envelopes.extend(materialized[index + 1 :])
                return True
        return False

    def _recover_claims_from_files(self, batch: _ClaimBatch) -> None:
        """One-off recovery pass over the canonical files, oldest first."""
        for directory in (self.config.export_dir / "tasks", self.config.export_dir / "requests"):
            if not directory.exists():
                continue
            for item_path in sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=False):
                envelope = read_json(item_path, {})
                if not isinstance(envelope, dict):
                    continue
                item_id = safe_id(
                    str(envelope.get("request_id") or envelope.get("task_id") or "")
                )
                if not item_id or item_id in batch.claimed_ids:
                    continue
                claimed = self._try_claim(envelope, batch)
                if claimed is None:
                    continue
                batch.claimed_items.append(claimed)
                batch.claimed_ids.add(item_id)
                if len(batch.claimed_items) >= batch.limit:
                    return

    def _try_claim(self, envelope: dict[str, Any], batch: _ClaimBatch) -> dict[str, Any] | None:
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
        if self._reject_controlled_claim(current, item_id):
            return None
        if not self._claim_matches_worker(current, kind, batch):
            return None
        return self._reserve_claim(current, batch)

    def _reject_controlled_claim(self, current: dict[str, Any], item_id: str) -> bool:
        """Close (and log) an envelope covered by a task control; True if so."""
        control_origin = str(current.get("origin_node_id") or current.get("dispatched_by") or "")
        active_control = self.task_control_for(item_id, control_origin)
        if active_control is None:
            return False
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
        return True

    def _claim_matches_worker(self, current: dict[str, Any], kind: str, batch: _ClaimBatch) -> bool:
        """Assignment, exclusion, role and fragment-balancing checks."""
        worker_id = batch.worker_id
        assigned_raw = str(current.get("assigned_peer_id", "") or current.get("target_peer_id", "")).strip()
        assigned_peer_id = safe_id(assigned_raw) if assigned_raw else ""
        if assigned_peer_id and assigned_peer_id != safe_id(worker_id):
            return False
        excluded_peer_ids = {
            safe_id(str(value))
            for value in (current.get("excluded_peer_ids", []) if isinstance(current.get("excluded_peer_ids"), list) else [])
            if str(value).strip()
        }
        if safe_id(worker_id) in excluded_peer_ids:
            return False
        required_roles = current.get("target_roles", []) if kind == "request" else current.get("required_roles", [])
        if not isinstance(required_roles, list):
            required_roles = []
        req_set = {str(role).lower() for role in required_roles if str(role).strip()}
        if req_set and not req_set.issubset(batch.worker_roles):
            return False
        body_key = "request" if kind == "request" else "task"
        body = current.get(body_key) if isinstance(current.get(body_key), Mapping) else {}
        fragment_index = body.get("fragment_index", current.get("fragment_index"))
        if fragment_index is None or str(fragment_index).strip() == "":
            # Generic tasks are pull-balanced by the workers themselves.
            # Recomputing a rendezvous target from the complete peer book
            # makes every idle worker scan the whole queue and causes
            # avoidable scheduler contention at high fanout. Fragments
            # keep deterministic assignment below for render balancing.
            selected_worker = safe_id(worker_id)
        else:
            selected_worker = self._preferred_claim_worker(current, req_set, excluded_peer_ids, batch)
        return not (selected_worker and selected_worker != safe_id(worker_id))

    def _preferred_claim_worker(
        self,
        current: Mapping[str, Any],
        required_roles: set[str],
        excluded_peer_ids: set[str],
        batch: _ClaimBatch,
    ) -> str:
        """Deterministic owner of a fragment among live compatible workers."""
        now = int(time.time())
        compatible: set[str] = set()
        for peer in self.peer_network.peers_snapshot(persist=False, include_routes=False).get("peers", []):
            if not isinstance(peer, dict):
                continue
            peer_id = optional_peer_id(peer.get("node_id", ""))
            if not peer_id or peer_id in excluded_peer_ids or peer.get("self"):
                continue
            last_seen = int(peer.get("last_seen_unix", 0) or 0)
            stale_after = int(self.config.peer_stale_after_s)
            if last_seen <= 0 or (stale_after > 0 and now - last_seen > stale_after):
                continue
            roles = {
                str(role).lower()
                for role in peer.get("roles", [])
                if str(role).strip()
            }
            if required_roles and not required_roles.issubset(roles):
                continue
            compatible.add(peer_id)

        safe_worker_id = safe_id(batch.worker_id)
        if safe_worker_id not in excluded_peer_ids and (
            not required_roles or required_roles.issubset(batch.worker_roles)
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

    def _reserve_claim(self, current: dict[str, Any], batch: _ClaimBatch) -> dict[str, Any]:
        """Mark ``current`` dispatched to the worker and build its claim payload."""
        worker_id = batch.worker_id
        key = self.envelope_key(current)
        dispatch_hops = int(current.get("dispatch_hops", 0) or 0)
        payload = dict(current)
        payload["dispatch_hops"] = dispatch_hops + 1
        payload["dispatched_by"] = self.config.node_id
        payload["dispatched_to"] = worker_id
        payload["dispatched_utc"] = utc_now()
        origin_return_url = str(current.get("origin_result_return_url", "")).strip()
        payload["result_return_url"] = origin_return_url if origin_return_url.startswith(("http://", "https://")) else self.peer_network.advertised_http_base_url.rstrip("/") + "/results/dispatch"
        # The scheduler owns the durable input cache. Attach referenced
        # content to the authenticated claim response so a newly started
        # or NATed worker does not depend on peer discovery converging
        # before it can execute its first fragment.
        payload = attach_network_content_blobs(self.config.export_dir, payload)

        self.update_envelope_status(current, "dispatched", {"result_hash": "", "dispatched_to": worker_id})
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
                "roles": sorted(batch.worker_roles),
            },
        )
        return payload

    def claim_task_for_worker(self, worker_id: str, worker_roles: set[str]) -> dict[str, Any] | None:
        """Backward-compatible single-task claim used by older callers."""
        claimed = self.claim_tasks_for_worker(worker_id, worker_roles, limit=1)
        return claimed[0] if claimed else None
