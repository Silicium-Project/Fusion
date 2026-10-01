"""Gossip events: publish, deduplicate, fan out over UDP/HTTP and read back history."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from tools.node.util import append_jsonl, sha256_bytes, utc_now


class GossipMixin:
    """Epidemic broadcast of signed events across the mesh."""

    def publish(self, topic: str, payload: dict[str, Any], *, background: bool = False) -> None:
        """Sign, record and broadcast a gossip event (optionally in the background)."""
        message = {
            "message_type": "gossip_event",
            "event_id": uuid.uuid4().hex,
            "node_id": self.node_id,
            "topic": topic,
            "payload": payload,
            "timestamp_utc": utc_now(),
            "hops": 0,
        }
        self._sign_message(message)
        self._record_event(message)
        if background:
            self._schedule_gossip_broadcast(message)
        else:
            self._broadcast(message)

    def _record_event(self, message: dict[str, Any]) -> bool:
        event_id = str(message.get("event_id", "")).strip()
        if not event_id:
            return False
        with self._lock:
            if event_id in self._seen_events:
                return False
            self._seen_events.add(event_id)
        append_jsonl(self.gossip_events_path, message)
        if str(message.get("topic", "")).strip() == "task_control":
            append_jsonl(self.task_control_events_path, message)
        return True

    def _schedule_gossip_broadcast(self, message: dict[str, Any], exclude: str = "") -> None:
        """Queue best-effort gossip without consuming request-handler threads."""
        with self._gossip_forward_lock:
            if self._gossip_forward_executor is None:
                self._gossip_forward_executor = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix=f"silicium-gossip-{self.node_id}",
                )
            executor = self._gossip_forward_executor
        try:
            executor.submit(self._broadcast, dict(message), exclude)
        except RuntimeError:
            # Shutdown races are harmless; anti-entropy will retry durable
            # announcements and task results remain authoritative locally.
            return

    def _broadcast(self, message: dict[str, Any], exclude: str = "") -> None:
        seed_udp_targets: set[str] = set()
        seed_http_targets: set[str] = set()
        for seed in self.config.seed_peers:
            host, port = self._parse_udp_target(seed)
            if host and port > 0:
                seed_udp_targets.add(f"{host}:{port}")
                continue
            http_base = self._normalize_http_target(seed)
            if http_base:
                seed_http_targets.add(http_base)
        peer_udp_targets: set[str] = set()
        peer_http_targets: set[str] = set()
        with self._lock:
            for peer in self._peers.values():
                bind = str(peer.get("gossip_bind", "")).strip()
                port = int(peer.get("gossip_port", 0) or 0)
                if bind and port:
                    peer_udp_targets.add(f"{bind}:{port}")
                http_base = str(peer.get("http_base_url", "")).strip()
                if http_base:
                    peer_http_targets.add(http_base)

        def bounded_targets(targets: set[str]) -> set[str]:
            candidates = sorted(target for target in targets if target and target != exclude)
            fanout = int(self.config.peer_sync_fanout)
            if fanout <= 0 or len(candidates) <= fanout:
                return set(candidates)
            # Rotate a deterministic window per event/node so a bounded mesh
            # still reaches the whole world over successive announcements.
            event_key = str(message.get("event_id") or message.get("node_id") or message.get("message_type") or "")
            digest = sha256_bytes(f"{self.node_id}|{event_key}".encode("utf-8"))
            offset = int(digest[:16], 16) % len(candidates)
            return {candidates[(offset + index) % len(candidates)] for index in range(fanout)}

        udp_targets = seed_udp_targets | bounded_targets(peer_udp_targets)
        http_targets = seed_http_targets | bounded_targets(peer_http_targets)
        for target in sorted(udp_targets):
            host, _, port_raw = target.partition(":")
            try:
                port = int(port_raw)
            except ValueError:
                continue
            if not host or port <= 0:
                continue
            if exclude and target == exclude:
                continue
            self._send_udp(target, host, port, message)
        for base_url in sorted(http_targets):
            if not base_url or base_url == self.advertised_http_base_url:
                continue
            if exclude and base_url == exclude:
                continue
            self._send_http(base_url, message)

    def _send_udp(self, target: str, host: str, port: int, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if self._udp_socket is not None:
            try:
                self._udp_socket.sendto(payload, (host, port))
                return
            except OSError:
                pass
        family = socket.AF_INET6 if ":" in str(host) else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            try:
                sock.sendto(payload, (host, port))
            except OSError:
                # A stale LAN/ICE candidate or a transient route failure must
                # never terminate gossip reconciliation.
                return
        finally:
            sock.close()

    def _send_http(self, base_url: str, message: dict[str, Any]) -> None:
        url = base_url.rstrip("/") + "/mesh"
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers=self._signed_headers("POST", "/mesh", data, {"Content-Type": "application/json"}))
        try:
            with urllib.request.urlopen(req, timeout=1):
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            return

    def recent_events(self, limit: int) -> list[dict[str, Any]]:
        """Last ``limit`` events of the gossip journal."""
        if limit <= 0 or not self.gossip_events_path.exists():
            return []
        try:
            lines = self.gossip_events_path.read_text(encoding="utf-8").splitlines()[-limit:]
        except Exception:
            return []
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events

    def recent_task_control_events(self, limit: int) -> list[dict[str, Any]]:
        """Return durable signed controls even when normal gossip history is noisy.

        Older nodes only persisted controls in the general event log. Bootstrap
        the dedicated anti-entropy index from that log once so upgrades retain
        every still-relevant cancellation.
        """
        if limit <= 0:
            return []
        with self._lock:
            if not self.task_control_events_path.exists():
                controls: list[dict[str, Any]] = []
                if self.gossip_events_path.exists():
                    try:
                        lines = self.gossip_events_path.read_text(encoding="utf-8").splitlines()
                    except Exception:
                        lines = []
                    for line in lines:
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(payload, dict) and str(payload.get("topic", "")).strip() == "task_control":
                            controls.append(payload)
                self.task_control_events_path.parent.mkdir(parents=True, exist_ok=True)
                for control in controls:
                    append_jsonl(self.task_control_events_path, control)
                if not controls:
                    self.task_control_events_path.touch(exist_ok=True)
            try:
                lines = self.task_control_events_path.read_text(encoding="utf-8").splitlines()[-limit:]
            except Exception:
                return []
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and str(payload.get("topic", "")).strip() == "task_control":
                events.append(payload)
        return events
