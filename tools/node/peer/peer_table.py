"""Peer book: record, merge, load, prune and snapshot known peers."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Mapping

from tools.node.util import (
    atomic_write_json,
    normalize_release_channel,
    read_json,
    safe_id,
    utc_now,
)


# On-chain reputation fields copied (as floats) from announcements, in the
# order they appear in a peer record.
_ONCHAIN_FLOAT_FIELDS = (
    "onchain_reputation",
    "onchain_global_reputation",
    "onchain_compute_reputation",
    "onchain_verify_reputation",
    "onchain_storage_reputation",
    "onchain_stake_amount",
)


class PeerTableMixin:
    """Maintain the in-memory peer book and its durable snapshots."""

    def peers_snapshot(self, *, persist: bool = True, include_routes: bool = True) -> dict[str, Any]:
        """Prune, then return (and by default persist) the peer table of our channel."""
        self._prune_stale_peers()
        self._prune_expired_peer_candidates()
        with self._lock:
            peers = sorted(
                (peer for peer in self._peers.values() if self._peer_channel_matches(peer)),
                key=lambda item: str(item.get("node_id", "")),
            )
        channel_counts: dict[str, int] = {}
        for peer in peers:
            channel = normalize_release_channel(peer.get("release_channel"), default="unknown") or "unknown"
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
        payload = {
            "schema_version": 1,
            "node_id": self.node_id,
            "count": len(peers),
            "peers": peers,
            "release_channel": self.config.release_channel,
            "release_channels": channel_counts,
            "routes": self.route_table_snapshot() if include_routes else [],
            "updated_utc": utc_now(),
        }
        if persist:
            atomic_write_json(self.peers_path, payload)
            atomic_write_json(self.discovery_registry_path, payload)
        return payload

    def update_peer_metadata(self, node_id: str, updates: dict[str, Any]) -> None:
        """Merge ``updates`` into a peer entry and persist the table."""
        if not node_id:
            return
        with self._lock:
            current = dict(self._peers.get(node_id, {}))
            current.update(dict(updates))
            current.setdefault("node_id", node_id)
            current.setdefault("last_seen_unix", int(time.time()))
            current.setdefault("updated_utc", utc_now())
            self._peers[node_id] = current
        self.peers_snapshot()

    def _peer_channel_matches(self, peer: Mapping[str, Any]) -> bool:
        raw_channel = str(peer.get("release_channel", "") or "").strip().lower()
        return not raw_channel or raw_channel == self.config.release_channel

    @staticmethod
    def _peer_seen_unix(message: Mapping[str, Any]) -> int:
        raw_seen = message.get("last_seen_unix")
        try:
            seen = int(raw_seen or 0)
        except (TypeError, ValueError):
            seen = 0
        if seen > 0:
            return seen
        timestamp = str(message.get("timestamp_utc", "")).strip()
        if not timestamp:
            return 0
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int(parsed.timestamp()))
        except ValueError:
            return 0

    def _record_peer(
        self,
        message: dict[str, Any],
        *,
        refresh_liveness: bool = True,
        persist_snapshot: bool = True,
    ) -> bool:
        """Merge a peer profile into the peer book; return whether it changed."""
        node_id = safe_id(str(message.get("node_id", "")))
        if not node_id:
            return False
        remote_channel = str(message.get("release_channel", "") or "").strip().lower()
        if node_id != self.node_id and remote_channel and remote_channel != self.config.release_channel:
            return False
        changed = False
        candidates = self._normalize_candidate_list(message.get("candidates", []), node_id)
        transport_attestations = self._verified_peer_transport_attestations(
            node_id,
            message.get("transport_attestations", []),
        )
        with self._lock:
            current = dict(self._peers.get(node_id, {}))
            last_seen_unix = self._merged_last_seen(current, message, refresh_liveness)
            merged = self._merged_peer_profile(node_id, current, message, candidates, transport_attestations, last_seen_unix)
            try:
                score_changed = current.get("reputation_score") is None or float(current.get("reputation_score", 0.0) or 0.0) != float(merged["reputation_score"])
            except (TypeError, ValueError):
                score_changed = True
            changed = any(current.get(key) != value for key, value in merged.items() if key not in {"updated_utc", "last_seen_unix"})
            current.update(merged)
            self._peers[node_id] = current
        if persist_snapshot:
            self.peers_snapshot()
        if node_id != self.node_id and score_changed and self._peer_score_sink is not None:
            try:
                self._peer_score_sink(node_id, float(merged.get("reputation_score", 0.0) or 0.0))
            except Exception:
                pass
        return changed

    def _merged_last_seen(self, current: Mapping[str, Any], message: Mapping[str, Any], refresh_liveness: bool) -> int:
        # A transitive peer snapshot is evidence of the snapshot
        # publisher being alive, not of every peer in that snapshot.
        # Only direct registrations/claims may refresh liveness with
        # the receiver's clock.
        observed_seen = self._peer_seen_unix(message)
        current_seen = int(current.get("last_seen_unix", 0) or 0)
        if refresh_liveness:
            return max(current_seen, observed_seen, int(time.time()))
        return max(current_seen, observed_seen)

    def _merged_peer_profile(
        self,
        node_id: str,
        current: Mapping[str, Any],
        message: Mapping[str, Any],
        candidates: list[dict[str, Any]],
        transport_attestations: list[dict[str, Any]],
        last_seen_unix: int,
    ) -> dict[str, Any]:
        """Combine the stored profile with ``message`` (see field comments)."""
        roles = message.get("roles") if isinstance(message.get("roles"), list) else []
        features = message.get("features") if isinstance(message.get("features"), list) else []
        capacity = message.get("capacity") if isinstance(message.get("capacity"), dict) else {}
        resource_reputation = message.get("resource_reputation") if isinstance(message.get("resource_reputation"), dict) else {}
        activity = message.get("activity") if isinstance(message.get("activity"), dict) else {}
        task_queue = message.get("task_queue") if isinstance(message.get("task_queue"), list) else []
        return {
            "node_id": node_id,
            # Peer tables are transitive and are not proof that a third
            # party is authorised to change another peer's identity or
            # routing profile. Keep established fields; signed candidate
            # announcements refresh the mutable NAT addresses separately.
            "identity_id": str(current.get("identity_id", "") or message.get("identity_id", "")),
            "public_key": str(current.get("public_key", "") or message.get("public_key", "")),
            "roles": list(current.get("roles", []) or roles),
            "app_version": str(message.get("app_version", "") or current.get("app_version", "")),
            "release_channel": str(message.get("release_channel", "") or current.get("release_channel", "")),
            "release_build": str(message.get("release_build", "") or current.get("release_build", "")),
            "features": [str(feature) for feature in (current.get("features", []) or features)],
            "transport_attestations": transport_attestations or current.get("transport_attestations", []),
            "http_base_url": str(current.get("http_base_url", "") or message.get("http_base_url", "")),
            "mesh_post_url": str(current.get("mesh_post_url", "") or message.get("mesh_post_url", "")),
            "gossip_bind": str(current.get("gossip_bind", "") or message.get("gossip_bind", "")),
            "gossip_port": int(current.get("gossip_port", 0) or message.get("gossip_port", 0) or 0),
            "candidates": candidates or current.get("candidates", []),
            "relay_capable": bool(message.get("relay_capable", current.get("relay_capable", False))),
            "capacity": capacity or current.get("capacity", {}),
            "reputation_score": float(message.get("reputation_score", current.get("reputation_score", 0.0)) or 0.0),
            "resource_reputation": resource_reputation or current.get("resource_reputation", {}),
            "activity": activity if "activity" in message else current.get("activity", {}),
            "task_queue": (
                [dict(item) for item in task_queue[:64] if isinstance(item, dict)]
                if "task_queue" in message
                else current.get("task_queue", [])
            ),
            **{key: float(message.get(key, current.get(key, 0.0)) or 0.0) for key in _ONCHAIN_FLOAT_FIELDS},
            "onchain_status": str(message.get("onchain_status", "") or current.get("onchain_status", "")),
            "solana_owner": str(message.get("solana_owner", "") or current.get("solana_owner", "")),
            "solana_worker": str(message.get("solana_worker", "") or current.get("solana_worker", "")),
            "updated_utc": str(message.get("timestamp_utc", utc_now())),
            "last_seen_unix": last_seen_unix,
            "self": node_id == self.node_id,
        }

    def _verified_peer_transport_attestations(self, node_id: str, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        verified: list[dict[str, Any]] = []
        for item in raw[-8:]:
            if not isinstance(item, Mapping) or str(item.get("observer_peer_id", "")) != node_id:
                continue
            claim_hash = str(item.get("claim_hash", "")).strip().lower()
            if not claim_hash:
                continue
            with self._lock:
                known = claim_hash in self._verified_transport_claims
            if known and not self._transport_attestation_hash_valid(item):
                continue
            if not known and not self.verify_transport_attestation(item):
                continue
            with self._lock:
                self._verified_transport_claims.add(claim_hash)
            verified.append(dict(item))
        verified.sort(key=lambda item: int(item.get("timestamp_unix", 0) or 0), reverse=True)
        return verified[:8]

    def _record_candidate_announce(self, message: dict[str, Any], *, refresh_liveness: bool = True) -> bool:
        node_id = safe_id(str(message.get("peer_id", message.get("node_id", ""))))
        if not node_id:
            return False
        candidates = self._normalize_candidate_list(message.get("candidates", []), node_id)
        with self._lock:
            current = dict(self._peers.get(node_id, {"node_id": node_id}))
            existing = current.get("candidates", []) if isinstance(current.get("candidates"), list) else []
            current["candidates"] = self._merge_candidate_list([*existing, *candidates], node_id, int(time.time()))
            observed_seen = self._peer_seen_unix(message)
            current_seen = int(current.get("last_seen_unix", 0) or 0)
            current["last_seen_unix"] = (
                max(current_seen, observed_seen, int(time.time()))
                if refresh_liveness
                else max(current_seen, observed_seen)
            )
            current["updated_utc"] = str(message.get("timestamp_utc", utc_now()))
            current["self"] = node_id == self.node_id
            self._peers[node_id] = current
        self.peers_snapshot()
        return True

    def _load_persisted_peers(self) -> None:
        snapshot = read_json(self.peers_path, {})
        peers = snapshot.get("peers") if isinstance(snapshot, dict) else None
        if not isinstance(peers, list):
            return
        with self._lock:
            for peer in peers:
                if not isinstance(peer, dict):
                    continue
                node_id = safe_id(str(peer.get("node_id", "")))
                if not node_id or node_id == self.node_id:
                    continue
                loaded = dict(peer)
                loaded["node_id"] = node_id
                if not self._peer_channel_matches(loaded):
                    continue
                # Persisted peer data is historical until a fresh direct
                # registration or signed announcement is observed.
                loaded["last_seen_unix"] = int(peer.get("last_seen_unix", 0) or 0)
                self._peers[node_id] = loaded

    def _prune_stale_peers(self) -> None:
        if self.config.peer_stale_after_s <= 0:
            return
        cutoff = int(time.time()) - int(self.config.peer_stale_after_s)
        removed = False
        with self._lock:
            for node_id in list(self._peers.keys()):
                peer = self._peers[node_id]
                if peer.get("self"):
                    continue
                if int(peer.get("last_seen_unix", 0) or 0) < cutoff:
                    self._peers.pop(node_id, None)
                    removed = True
        if removed:
            atomic_write_json(self.peers_path, {"schema_version": 1, "node_id": self.node_id, "count": len(self._peers), "peers": list(self._peers.values()), "updated_utc": utc_now()})
