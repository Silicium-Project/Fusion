"""Local peer profile and its announcements (peer_announce, candidate_announce)."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from tools.node.util import utc_now


class AnnounceMixin:
    """Publish this node's profile to the mesh."""

    def set_local_profile(
        self,
        *,
        capacity: dict[str, Any] | None = None,
        reputation_score: float | None = None,
        resource_reputation: dict[str, Any] | None = None,
        onchain_reputation: float | None = None,
        onchain_global_reputation: float | None = None,
        onchain_compute_reputation: float | None = None,
        onchain_verify_reputation: float | None = None,
        onchain_storage_reputation: float | None = None,
        onchain_stake_amount: float | None = None,
        onchain_status: str | None = None,
        solana_owner: str | None = None,
        solana_worker: str | None = None,
        activity: dict[str, Any] | None = None,
        task_queue: list[dict[str, Any]] | None = None,
    ) -> None:
        """Update the announced profile fields that are not None."""
        if capacity is not None:
            self.local_capacity = capacity
        if reputation_score is not None:
            self.local_reputation_score = float(reputation_score)
        if resource_reputation is not None:
            self.local_resource_reputation = dict(resource_reputation)
        if onchain_reputation is not None:
            self.local_onchain_reputation = float(onchain_reputation)
        if onchain_global_reputation is not None:
            self.local_onchain_global_reputation = float(onchain_global_reputation)
        if onchain_compute_reputation is not None:
            self.local_onchain_compute_reputation = float(onchain_compute_reputation)
        if onchain_verify_reputation is not None:
            self.local_onchain_verify_reputation = float(onchain_verify_reputation)
        if onchain_storage_reputation is not None:
            self.local_onchain_storage_reputation = float(onchain_storage_reputation)
        if onchain_stake_amount is not None:
            self.local_onchain_stake_amount = float(onchain_stake_amount)
        if onchain_status is not None:
            self.local_onchain_status = str(onchain_status)
        if solana_owner is not None:
            self.local_solana_owner = str(solana_owner)
        if solana_worker is not None:
            self.local_solana_worker = str(solana_worker)
        if activity is not None:
            self.local_activity = dict(activity)
        if task_queue is not None:
            self.local_task_queue = [dict(item) for item in task_queue[:64] if isinstance(item, dict)]
        # Heartbeats update the in-memory local peer profile on every idle
        # cycle. Durable peer snapshots are owned by announce/sync paths;
        # writing the full peer-book here serializes the node under load.
        self._record_self_peer(persist_snapshot=False)

    def set_peer_score_sink(self, callback: Any) -> None:
        """Register ``callback(node_id, score)`` called when a peer's score changes."""
        self._peer_score_sink = callback

    def _record_self_peer(self, *, persist_snapshot: bool = True) -> None:
        candidates = self.local_candidates_snapshot()
        transport_attestations = self.recent_transport_attestations(4)
        with self._lock:
            self._peers[self.node_id] = {
                "node_id": self.node_id,
                "identity_id": self.identity.identity_id,
                "public_key": self.identity.public_key_b64,
                "roles": sorted(self.config.roles),
                "app_version": self.config.app_version,
                "release_channel": self.config.release_channel,
                "release_build": self.config.release_build,
                "features": self.direct_transport.features(),
                "transport_attestations": transport_attestations,
                "http_base_url": self.advertised_http_base_url,
                "mesh_post_url": self.mesh_post_url,
                "gossip_bind": self._advertised_gossip_host(),
                "gossip_port": self._advertised_gossip_port(),
                "candidates": candidates,
                "relay_capable": bool(self.config.relay_enable),
                "capacity": self.local_capacity,
                "reputation_score": self.local_reputation_score,
                "resource_reputation": self.local_resource_reputation,
                "activity": self.local_activity,
                "task_queue": self.local_task_queue,
                "onchain_reputation": self.local_onchain_reputation,
                "onchain_global_reputation": self.local_onchain_global_reputation,
                "onchain_compute_reputation": self.local_onchain_compute_reputation,
                "onchain_verify_reputation": self.local_onchain_verify_reputation,
                "onchain_storage_reputation": self.local_onchain_storage_reputation,
                "onchain_stake_amount": self.local_onchain_stake_amount,
                "onchain_status": self.local_onchain_status,
                "solana_owner": self.local_solana_owner,
                "solana_worker": self.local_solana_worker,
                "last_seen_unix": int(time.time()),
                "updated_utc": utc_now(),
                "self": True,
            }
        if persist_snapshot:
            self.peers_snapshot()

    def announce(self) -> None:
        """Broadcast a signed ``peer_announce`` and our candidates."""
        candidates = self.refresh_candidates()
        message = {
            "message_type": "peer_announce",
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "roles": sorted(self.config.roles),
            "app_version": self.config.app_version,
            "release_channel": self.config.release_channel,
            "release_build": self.config.release_build,
            "features": self.direct_transport.features(),
            "transport_attestations": self.recent_transport_attestations(4),
            "http_base_url": self.advertised_http_base_url,
            "mesh_post_url": self.mesh_post_url,
            "gossip_bind": self._advertised_gossip_host(),
            "gossip_port": self._advertised_gossip_port(),
            "candidates": candidates,
            "relay_capable": bool(self.config.relay_enable),
            "capacity": self.local_capacity,
            "reputation_score": self.local_reputation_score,
            "resource_reputation": self.local_resource_reputation,
            "activity": self.local_activity,
            "task_queue": self.local_task_queue,
            "onchain_reputation": self.local_onchain_reputation,
            "onchain_global_reputation": self.local_onchain_global_reputation,
            "onchain_compute_reputation": self.local_onchain_compute_reputation,
            "onchain_verify_reputation": self.local_onchain_verify_reputation,
            "onchain_storage_reputation": self.local_onchain_storage_reputation,
            "onchain_stake_amount": self.local_onchain_stake_amount,
            "onchain_status": self.local_onchain_status,
            "solana_owner": self.local_solana_owner,
            "solana_worker": self.local_solana_worker,
            "timestamp_utc": utc_now(),
        }
        self._sign_message(message)
        self._record_self_peer()
        self._broadcast(message)
        self.announce_candidates(candidates)

    def schedule_announce(self) -> None:
        """Coalesce peer announcements away from inbound HTTP handlers."""
        with self._announce_schedule_lock:
            if self._announce_scheduled or self._stop_event.is_set():
                return
            self._announce_scheduled = True

        def _run() -> None:
            try:
                self.announce()
            except Exception:
                # Announcement is best effort; the periodic sync loop remains
                # responsible for eventual peer-book convergence.
                pass
            finally:
                with self._announce_schedule_lock:
                    self._announce_scheduled = False

        threading.Thread(
            target=_run,
            name=f"silicium-peer-announce-{self.node_id}",
            daemon=True,
        ).start()

    def announce_candidates(self, candidates: list[dict[str, Any]] | None = None) -> None:
        """Broadcast a signed ``candidate_announce``."""
        candidate_list = candidates if candidates is not None else self.refresh_candidates()
        message = {
            "message_type": "candidate_announce",
            "peer_id": self.node_id,
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "candidates": candidate_list,
            "timestamp_utc": utc_now(),
            "timestamp_unix": int(time.time()),
            "nonce": uuid.uuid4().hex,
        }
        self._sign_message(message)
        self._broadcast(message)
