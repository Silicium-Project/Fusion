"""Heartbeat/metrics files and the activity/telemetry snapshots they publish."""

from __future__ import annotations

import threading
from typing import Any

from tools.node.util import atomic_write_json, utc_now


class HeartbeatMixin:
    """Publish liveness, metrics and current activity."""

    def write_heartbeat(self) -> None:
        """Refresh the announced profile and write ``node.<id>.heartbeat.json``."""
        self.refresh_local_onchain_profile()
        self.refresh_known_peer_onchain_reputations()
        capacity = self.runtime.capacity()
        current_reputation = self.reputation.local_score()
        resource_reputation = self.reputation.resource_snapshot()
        self._telemetry = self.telemetry_sampler.sample()
        task_queue = self.cached_task_queue_snapshot()
        self.config.reputation_score = current_reputation
        self.peer_network.set_local_profile(
            capacity=capacity,
            reputation_score=current_reputation,
            resource_reputation=resource_reputation,
            onchain_reputation=self._solana_onchain_reputation,
            onchain_global_reputation=self._solana_onchain_reputation,
            onchain_compute_reputation=getattr(self, "_solana_onchain_compute_reputation", 0.0),
            onchain_verify_reputation=getattr(self, "_solana_onchain_verify_reputation", 0.0),
            onchain_storage_reputation=getattr(self, "_solana_onchain_storage_reputation", 0.0),
            onchain_stake_amount=getattr(self, "_solana_onchain_stake_amount", 0.0),
            onchain_status=getattr(self, "_solana_onchain_status", ""),
            solana_owner=self._solana_owner,
            solana_worker=self._solana_worker,
            activity=self.activity_snapshot(),
            task_queue=task_queue,
        )
        p2p_candidates = self.peer_network.candidate_diagnostics()
        p2p_sessions = self.peer_network.sessions_snapshot()
        p2p_direct_sessions = self.peer_network.direct_sessions_snapshot()
        atomic_write_json(
            self.heartbeat_path,
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "timestamp_utc": utc_now(),
                "roles": sorted(self.config.roles),
                "app_version": self.config.app_version,
                "release_channel": self.config.release_channel,
                "release_build": self.config.release_build,
                "capacity": capacity,
                "reputation_score": current_reputation,
                "resource_reputation": resource_reputation,
                **self._heartbeat_peer_fields(p2p_candidates, p2p_sessions, p2p_direct_sessions),
                "activity": self.activity_snapshot(),
                "telemetry": self.telemetry_snapshot(),
                "task_queue": task_queue,
                "solana_owner": self._solana_owner,
                "solana_worker": self._solana_worker,
                "onchain_reputation": self._solana_onchain_reputation,
                "onchain_compute_reputation": self._solana_onchain_compute_reputation,
                "onchain_verify_reputation": self._solana_onchain_verify_reputation,
                "onchain_storage_reputation": self._solana_onchain_storage_reputation,
                "onchain_stake_amount": self._solana_onchain_stake_amount,
                "onchain_status": self._solana_onchain_status,
            },
        )

    def _heartbeat_peer_fields(
        self,
        p2p_candidates: dict[str, Any],
        p2p_sessions: dict[str, Any],
        p2p_direct_sessions: dict[str, Any],
    ) -> dict[str, Any]:
        """Networking and pull-claim part of the heartbeat (keys kept in order)."""
        return {
            "peer_http_base_url": self.peer_network.http_base_url,
            "peer_public_base_url": self.peer_network.advertised_http_base_url,
            # Heartbeats are emitted on the node's idle cadence. Do not
            # serialize and persist the full routed peer graph on every
            # heartbeat; sync/announce paths own durable peer snapshots.
            "peer_count": int(self.peer_network.peers_snapshot(persist=False, include_routes=False).get("count", 0)),
            "gossip_enabled": self.config.gossip_enable,
            "peer_sync_interval_s": self.config.peer_sync_interval_s,
            "peer_sync_fanout": self.config.peer_sync_fanout,
            "peer_http_max_workers": self.config.peer_http_max_workers,
            "pull_tasks_interval_s": self.config.pull_tasks_interval_s,
            "pull_tasks_batch_size": self.config.pull_tasks_batch_size,
            "mesh_auth_enabled": bool(self.config.mesh_key),
            "identity_id": self.peer_network.identity.identity_id,
            "relay_enabled": self.config.relay_enable,
            "p2p_candidate_count": p2p_candidates["candidate_count"],
            "p2p_candidate_types": p2p_candidates["candidate_types"],
            "p2p_selected_candidate": p2p_candidates["selected_candidate"],
            "p2p_observed_public_address": p2p_candidates["observed_public_address"],
            "p2p_nat_behavior": p2p_candidates["nat_behavior"],
            "p2p_session_count": int(p2p_sessions.get("count", 0) or 0),
            "p2p_direct_session_count": int(p2p_direct_sessions.get("count", 0) or 0),
            "p2p_transport_attestations": self.peer_network.recent_transport_attestations(8),
            "last_claim_poll_unix": self._last_claim_poll_unix,
            "last_claim_poll_utc": self._last_claim_poll_utc,
            "last_claim_error": self._last_claim_error,
            "last_claim_result": self._last_claim_result,
            "last_claim_targets": self._last_claim_targets,
        }

    def write_metrics(self) -> None:
        """Write ``node.<id>.metrics.json`` (counters plus runtime telemetry)."""
        self.metrics["updated_utc"] = utc_now()
        self.metrics["runtime"] = self.telemetry_snapshot()
        atomic_write_json(self.metrics_path, self.metrics)

    def activity_snapshot(self) -> dict[str, Any]:
        """Current status, active tasks and last response."""
        with self._activity_lock:
            active_tasks = [dict(item) for item in self._active_tasks]
            last_response = dict(self._last_response)
        return {
            "status": "working" if active_tasks else "idle",
            "active_tasks": active_tasks,
            "last_response": last_response,
            "telemetry": self.telemetry_snapshot(),
        }

    def telemetry_snapshot(self) -> dict[str, Any]:
        """Copy of the latest runtime telemetry sample."""
        return dict(self._telemetry)

    def update_active_task(self, **updates: Any) -> None:
        """Merge ``updates`` into the active task entry (if any)."""
        with self._activity_lock:
            if self._active_tasks:
                self._active_tasks[0].update(updates)

    def publish_runtime_state(self, *, announce: bool = False) -> None:
        """Push activity and queue to the peer profile; optionally announce it."""
        self.peer_network.set_local_profile(
            activity=self.activity_snapshot(),
            task_queue=self.cached_task_queue_snapshot(),
        )
        if announce:
            threading.Thread(
                target=self.peer_network.schedule_announce,
                name="silicium-peer-announce",
                daemon=True,
            ).start()
