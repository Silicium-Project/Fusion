"""Worker side of pull-based work: poll schedulers and enqueue claimed tasks."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
import urllib.error
import urllib.request
from typing import Any

from tools.node.config import build_capacity_snapshot
from tools.node.envelopes import enqueue_request_envelope, enqueue_task_envelope
from tools.node.util import (
    append_jsonl,
    atomic_write_json,
    safe_id,
    sha256_bytes,
    stable_json,
    utc_now,
)


@dataclass
class _ClaimAttempt:
    """State of one claim request to one scheduler."""

    base_url: str
    attempt: dict[str, Any]
    started: float
    poll_started_utc: str
    # Shared across all targets of one poll.
    claimed_item_ids: list[str]
    # Items claimed from this target only.
    item_ids: list[str] = field(default_factory=list)
    response_raw: bytes = b""


class PullLoopMixin:
    """Poll schedulers for work when this node cannot be reached directly."""

    def _start_pull_tasks_loop(self) -> None:
        self._pull_stop_event.clear()

        def _loop() -> None:
            interval = max(0.25, float(self.config.pull_tasks_interval_s))
            # Workers are often started in waves. A deterministic phase keeps
            # those waves from producing a synchronized claim burst against a
            # scheduler, while remaining stable across restarts of the same
            # node identity. The cap prevents a slow first claim on a busy
            # scheduler from delaying a worker indefinitely.
            phase_window = max(interval, min(5.0, interval * 5.0))
            phase_seed = hashlib.sha256(str(self.config.node_id).encode("utf-8")).digest()
            phase_ratio = int.from_bytes(phase_seed[:8], "big") / float(1 << 64)
            if self._pull_stop_event.wait(phase_ratio * phase_window):
                return
            while not self._pull_stop_event.wait(interval):
                try:
                    self._poll_and_claim_tasks_once()
                except Exception:
                    pass
                # Empty/error polls should yield to the scheduler instead of
                # forming a permanent hot loop when many idle workers share a
                # broker. A successful claim immediately returns to the
                # configured cadence so queued work stays responsive.
                if self._last_claim_result == "claimed":
                    next_interval = interval
                else:
                    next_interval = min(5.0, max(interval * 2.0, interval + 0.25))
                if self._pull_stop_event.wait(next_interval):
                    return

        self._pull_thread = threading.Thread(target=_loop, name=f"silicium-pull-tasks-{self.config.node_id}", daemon=True)
        self._pull_thread.start()

    def _stop_pull_tasks_loop(self) -> None:
        self._pull_stop_event.set()
        if self._pull_thread is not None:
            self._pull_thread.join(timeout=1)
            self._pull_thread = None

    def _poll_and_claim_tasks_once(self) -> None:
        """Ask every scheduler seed for work once and enqueue what is granted."""
        poll_started = time.monotonic()
        targets: set[str] = set()
        for seed in self.config.seed_peers + self.config.discovery_seeds:
            normalized = self.peer_network._normalize_http_target(seed)
            if normalized and normalized != self.peer_network.advertised_http_base_url:
                targets.add(normalized)

        poll_started_utc = utc_now()
        attempts: list[dict[str, Any]] = []
        claimed_item_ids: list[str] = []
        raw_payload = self._claim_request_body()
        for base_url in sorted(targets):
            attempts.append(self._claim_from_target(base_url, raw_payload, poll_started_utc, claimed_item_ids))
        self._record_claim_poll(targets, attempts, claimed_item_ids, poll_started, poll_started_utc)

    def _claim_request_body(self) -> bytes:
        """Signed-claim body: this worker's profile and the batch size."""
        # Candidate discovery is network-bound and already refreshed by the
        # dedicated peer sync loop. A claim only needs the latest local
        # snapshot; forcing discovery here can delay task pickup by several
        # seconds when a rendezvous endpoint is slow or unreachable.
        candidates = self.peer_network.local_candidates_snapshot()
        return stable_json({
            "node_id": self.config.node_id,
            "roles": sorted(self.config.roles),
            "app_version": self.config.app_version,
            "release_channel": self.config.release_channel,
            "release_build": self.config.release_build,
            "features": self.peer_network.direct_transport.features(),
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
            "max_tasks": max(1, min(32, int(self.config.pull_tasks_batch_size))),
        }).encode("utf-8")

    def _claim_from_target(
        self,
        base_url: str,
        raw_payload: bytes,
        poll_started_utc: str,
        claimed_item_ids: list[str],
    ) -> dict[str, Any]:
        """POST /tasks/claim to one scheduler; return the attempt diagnostics."""
        # Signaling and task-control anti-entropy already run in the peer
        # sync loop. Repeating their bounded HTTP calls here added several
        # network timeouts to every claim. The scheduler rejects controlled
        # tasks atomically, and the local check below still covers controls
        # learned before the claim response.
        path = "/tasks/claim"
        url = base_url.rstrip("/") + path
        context = _ClaimAttempt(
            base_url=base_url,
            attempt={"target": base_url, "url": url, "result": "unknown"},
            started=time.monotonic(),
            poll_started_utc=poll_started_utc,
            claimed_item_ids=claimed_item_ids,
        )
        attempt = context.attempt
        request = urllib.request.Request(
            url,
            data=raw_payload,
            method="POST",
            headers=self.peer_network._signed_headers("POST", path, raw_payload, {"Content-Type": "application/json"}),
        )
        try:
            # Claims are serialized per scheduler for atomic reservation;
            # allow a busy but healthy scheduler to drain its queue rather
            # than turning contention into a false worker-loss signal.
            with urllib.request.urlopen(request, timeout=10) as response:
                attempt["http_status"] = int(response.status)
                context.response_raw = response.read()
                payload = json.loads(context.response_raw.decode("utf-8"))
                if not isinstance(payload, dict) or not bool(payload.get("ok")):
                    attempt["result"] = "invalid_response"
                else:
                    self._accept_claim_response(payload, context)
        except urllib.error.HTTPError as error:
            attempt["result"] = "http_error"
            attempt["http_status"] = int(error.code)
            attempt["error"] = str(error.reason or error)
        except Exception as error:
            attempt["result"] = "request_error"
            attempt["error"] = f"{type(error).__name__}:{error}"
        attempt["duration_ms"] = round((time.monotonic() - context.started) * 1000)
        return attempt

    def _accept_claim_response(self, payload: dict[str, Any], context: _ClaimAttempt) -> None:
        """Enqueue every granted task (``tasks``, or legacy ``task``)."""
        attempt = context.attempt
        response_tasks = payload.get("tasks")
        if not isinstance(response_tasks, list):
            response_tasks = []
        if not response_tasks and isinstance(payload.get("task"), dict):
            response_tasks = [payload["task"]]
        response_tasks = [item for item in response_tasks if isinstance(item, dict)]
        if not response_tasks:
            attempt["result"] = "no_task_available"
            attempt["claimed_count"] = 0
            response_tasks = []
        for claimed_task in response_tasks:
            self._accept_claimed_task(claimed_task, context)
        if context.item_ids:
            attempt["result"] = "claimed"
            attempt["item_id"] = context.item_ids[0]
            attempt["item_ids"] = list(context.item_ids)
            attempt["claimed_count"] = len(context.item_ids)
        elif attempt.get("result") in {"", "unknown", None}:
            attempt["result"] = "no_task_available"

    def _accept_claimed_task(self, claimed_task: dict[str, Any], context: _ClaimAttempt) -> None:
        """Enqueue one granted envelope unless a known task control rejects it."""
        attempt = context.attempt
        base_url = context.base_url
        # The claim request just proved that this scheduler
        # URL is reachable from the worker. Prefer that
        # direct path for locally originated tasks instead
        # of routing the result through a public proxy.
        if not str(claimed_task.get("origin_result_return_url", "")).strip():
            claimed_task["result_return_url"] = base_url.rstrip("/") + "/results/dispatch"
        kind = str(claimed_task.get("envelope_kind") or "task")
        candidate_item_id = safe_id(
            str(claimed_task.get("request_id") or claimed_task.get("task_id") or "unknown")
        )
        control_origin = str(
            claimed_task.get("origin_node_id") or claimed_task.get("dispatched_by") or ""
        )
        active_control = self.task_control_for(candidate_item_id, control_origin)
        if active_control is not None:
            attempt["result"] = "rejected_task_control"
            attempt.setdefault("rejected_item_ids", []).append(candidate_item_id)
            attempt["control_id"] = str(active_control.get("control_id", ""))
            return
        self.ingest_content_blobs(claimed_task)
        if kind == "request":
            enqueue_request_envelope(self.config.export_dir, claimed_task)
        else:
            enqueue_task_envelope(self.config.export_dir, claimed_task)
        self.remember_task_queue_envelope(claimed_task)
        # Count the item as claimed before the best-effort bookkeeping below
        # (an exception there still leaves it enqueued and counted).
        context.claimed_item_ids.append(candidate_item_id)
        context.item_ids.append(candidate_item_id)
        self._attest_task_delivery(candidate_item_id, context.response_raw, base_url)
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "claimed_task_received",
                "item_id": candidate_item_id,
                "from_seed": base_url,
                "poll_started_utc": context.poll_started_utc,
                "claim_duration_ms": round((time.monotonic() - context.started) * 1000),
            },
        )

    def _attest_task_delivery(self, candidate_item_id: str, response_raw: bytes, base_url: str) -> None:
        """Record a ``central`` transport attestation for the claim response."""
        target_peer = next(
            (
                peer
                for peer in self.peer_network.peers_snapshot(persist=False, include_routes=False).get("peers", [])
                if str(peer.get("http_base_url", "")).rstrip("/") == base_url.rstrip("/")
            ),
            {},
        )
        self.peer_network.record_transport_attestation(
            route="central",
            transport_backend="scheduler-http",
            remote_peer_id=str(target_peer.get("node_id", "")),
            proof_scope="task_delivery",
            task_id=candidate_item_id,
            content_sha256=sha256_bytes(response_raw),
            size_bytes=len(response_raw),
            endpoint=base_url,
            success=True,
        )

    def _record_claim_poll(
        self,
        targets: set[str],
        attempts: list[dict[str, Any]],
        claimed_item_ids: list[str],
        poll_started: float,
        poll_started_utc: str,
    ) -> None:
        """Expose the poll outcome (heartbeat fields, health file, event log)."""
        claimed_item_id = claimed_item_ids[0] if claimed_item_ids else ""
        completed_at = utc_now()
        poll_duration_ms = round((time.monotonic() - poll_started) * 1000)
        errors = [f"{item.get('target')}: {item.get('error') or item.get('http_status')}" for item in attempts if item.get("result") in {"http_error", "request_error", "invalid_response"}]
        result = "claimed" if claimed_item_id else (str(attempts[0].get("result")) if attempts else "no_scheduler_target")
        self._last_claim_poll_unix = time.time()
        self._last_claim_poll_utc = completed_at
        self._last_claim_error = "; ".join(errors)
        self._last_claim_result = result
        self._last_claim_targets = attempts
        atomic_write_json(
            self.config.export_dir / "claim-poll.health.json",
            {
                "schema_version": 2,
                "timestamp_utc": completed_at,
                "started_utc": poll_started_utc,
                "duration_ms": poll_duration_ms,
                "node_id": self.config.node_id,
                "targets_count": len(targets),
                "roles": sorted(self.config.roles),
                "app_version": self.config.app_version,
                "release_channel": self.config.release_channel,
                "release_build": self.config.release_build,
                "result": result,
                "claimed_item_id": claimed_item_id,
                "claimed_item_ids": list(claimed_item_ids),
                "claimed_count": len(claimed_item_ids),
                "batch_size": max(1, min(32, int(self.config.pull_tasks_batch_size))),
                "last_error": self._last_claim_error,
                "attempts": attempts,
            },
        )
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": completed_at,
                "started_utc": poll_started_utc,
                "duration_ms": poll_duration_ms,
                "node_id": self.config.node_id,
                "kind": "claim_poll",
                "status": result,
                "item_id": claimed_item_id,
                "targets": attempts,
                "error": self._last_claim_error,
            },
        )
