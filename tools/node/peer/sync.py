"""Anti-entropy loop: periodic peer-table, event and discovery reconciliation."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from tools.node.util import append_jsonl, stable_json, utc_now


class SyncMixin:
    """Periodically reconcile state with seeds and peers."""

    def _start_sync_loop(self) -> None:
        def _loop() -> None:
            while not self._stop_event.wait(max(1, self.config.peer_sync_interval_s)):
                try:
                    self.sync_once()
                except Exception as exc:
                    # Peer discovery is a permanent background responsibility.
                    # Persist the incident for diagnostics, then keep reconciling.
                    try:
                        append_jsonl(
                            self.export_dir / "peer-sync-errors.ndjson",
                            {
                                "schema_version": 1,
                                "timestamp_utc": utc_now(),
                                "node_id": self.node_id,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                        )
                    except OSError:
                        pass

        self._sync_thread = threading.Thread(target=_loop, name=f"silicium-peer-sync-{self.node_id}", daemon=True)
        self._sync_thread.start()

    def sync_once(self) -> None:
        """One anti-entropy round against every sync target and discovery seed."""
        self._prune_stale_peers()
        self.refresh_candidates()
        self._record_self_peer()
        targets = self._sync_targets()
        for base_url in targets:
            self._sync_peer_table(base_url)
            self._sync_task_controls(base_url)
            self._sync_recent_events(base_url)
            self._sync_update_manifest(base_url)
            self._poll_signaling_sessions(base_url)
        self._sync_discovery()

    def _sync_discovery(self) -> None:
        # A public HTTP seed is also a discovery rendezvous. Desktop nodes only
        # receive --seed-peers from the installer, so restricting registration
        # to --discovery-seeds left their ICE candidates local-only.
        seeds = {
            seed.strip()
            for seed in self.config.discovery_seeds + self.config.seed_peers
            if seed.strip()
        }
        for seed in sorted(seeds):
            base_url = self._normalize_http_target(seed)
            if not base_url:
                continue
            self._register_with_discovery(base_url)
            self._fetch_discovery_snapshot(base_url)

    def _register_with_discovery(self, base_url: str) -> None:
        candidates = self.refresh_candidates()
        payload = {
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
            "timestamp_utc": utc_now(),
        }
        raw = stable_json(payload).encode("utf-8")
        path = "/discovery/register"
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=raw,
            method="POST",
            headers=self._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        try:
            with urllib.request.urlopen(request, timeout=5):
                return
        except Exception:
            return

    def _fetch_discovery_snapshot(self, base_url: str) -> None:
        path = "/discovery/snapshot"
        request = urllib.request.Request(base_url.rstrip("/") + path, headers=self._signed_headers("GET", path, b""))
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        peers = payload.get("peers") if isinstance(payload, dict) else None
        if not isinstance(peers, list):
            return
        for peer in peers:
            if isinstance(peer, dict):
                self._record_peer(peer, refresh_liveness=False, persist_snapshot=False)
        if peers:
            self.peers_snapshot()

    def _sync_targets(self) -> list[str]:
        seed_targets: set[str] = set()
        for seed in self.config.seed_peers:
            http_base = self._normalize_http_target(seed)
            if http_base:
                seed_targets.add(http_base)
        peer_targets: set[str] = set()
        with self._lock:
            for peer in self._peers.values():
                http_base = str(peer.get("http_base_url", "")).strip()
                if http_base:
                    peer_targets.add(http_base)
        seed_targets.discard("")
        peer_targets.discard("")
        seed_targets.discard(self.advertised_http_base_url)
        peer_targets.discard(self.advertised_http_base_url)
        # A bounded deterministic fan-out avoids O(N²) HTTP anti-entropy in a
        # world mesh. The rendezvous/seed path remains authoritative for task
        # claims and is never evicted by this limit.
        peer_targets.difference_update(seed_targets)
        fanout = int(self.config.peer_sync_fanout)
        if fanout > 0:
            peer_targets = set(sorted(peer_targets)[:fanout])
        return sorted(seed_targets | peer_targets)

    def _sync_peer_table(self, base_url: str) -> None:
        path = "/peers"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(base_url.rstrip("/") + path, headers=self._signed_headers("GET", path, b"")), timeout=5
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        peers = payload.get("peers") if isinstance(payload, dict) else None
        if not isinstance(peers, list):
            return
        for peer in peers:
            if isinstance(peer, dict):
                self._record_peer(peer, refresh_liveness=False, persist_snapshot=False)
        if peers:
            self.peers_snapshot()

    def _sync_recent_events(self, base_url: str) -> None:
        path = f"/events/recent?limit={max(1, self.config.peer_event_limit)}"
        url = f"{base_url.rstrip('/')}{path}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=self._signed_headers("GET", path, b"")), timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return
        for event in events:
            if isinstance(event, dict):
                self._handle_network_message(event, base_url)

    def _sync_task_controls(self, base_url: str) -> None:
        """Reconcile signed cancellation controls outside the bounded event feed."""
        path = "/events/task-controls?limit=2048"
        url = f"{base_url.rstrip('/')}{path}"
        try:
            request = urllib.request.Request(url, headers=self._signed_headers("GET", path, b""))
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return
        for event in events:
            if isinstance(event, dict):
                self._handle_network_message(event, base_url)
