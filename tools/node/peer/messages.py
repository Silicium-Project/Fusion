"""UDP gossip listener and dispatch of inbound mesh messages."""

from __future__ import annotations

import json
import socket
import threading
from typing import Any

from tools.node.util import safe_id, utc_now


class MessagesMixin:
    """Receive and dispatch signed mesh messages (UDP and HTTP /mesh)."""

    def _start_udp_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.config.gossip_bind, self.config.gossip_port))
        sock.settimeout(0.5)
        self._udp_socket = sock
        self.config.gossip_port = int(sock.getsockname()[1])

        def _loop() -> None:
            while self._udp_socket is sock:
                try:
                    payload, addr = sock.recvfrom(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    message = json.loads(payload.decode("utf-8"))
                except Exception:
                    continue
                self._handle_udp_message(message, f"{addr[0]}:{addr[1]}")

        self._udp_thread = threading.Thread(target=_loop, name=f"silicium-gossip-{self.node_id}", daemon=True)
        self._udp_thread.start()

    def _handle_network_message(self, message: dict[str, Any], sender: str) -> None:
        """Verify then dispatch one inbound mesh message by ``message_type``."""
        if not self._verify_message(message):
            return
        message_type = str(message.get("message_type", ""))
        if message_type == "peer_announce":
            changed = self._record_peer(message, refresh_liveness=False, persist_snapshot=False)
            if changed and safe_id(str(message.get("node_id", ""))) != self.node_id:
                # Never make the inbound HTTP handler fan out synchronously:
                # one peer announcement must not consume the whole request
                # pool while it waits on every other peer.
                self.schedule_announce()
            return
        if message_type == "candidate_announce":
            self._record_candidate_announce(message, refresh_liveness=False)
            return
        if message_type == "punch_probe":
            self._handle_punch_probe_message(message, sender)
            return
        if message_type == "punch_ack":
            self._handle_punch_ack(message)
            return
        if message_type != "gossip_event":
            return
        self._handle_gossip_event(message, sender)

    def _handle_punch_probe_message(self, message: dict[str, Any], sender: str) -> None:
        """Relay-coordinated probe: answer with a signed announce to the target."""
        requester_handshake = message.get("requester_handshake")
        if not isinstance(requester_handshake, dict):
            self._handle_direct_punch_probe(message, sender)
            return
        if isinstance(requester_handshake, dict) and safe_id(str(requester_handshake.get("peer_id", ""))) != self.node_id:
            ok, _reason = self.verify_session_handshake(requester_handshake, expected_target_peer_id=self.node_id)
            if not ok:
                return
        target_host = str(message.get("target_host", "")).strip()
        target_port = int(message.get("target_port", 0) or 0)
        if target_host and target_port > 0:
            probe = self._punch_probe_announce()
            self._sign_message(probe)
            self._send_udp(f"{target_host}:{target_port}", target_host, target_port, probe)

    def _punch_probe_announce(self) -> dict[str, Any]:
        return {
            "message_type": "peer_announce",
            "node_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "roles": sorted(self.config.roles),
            "app_version": self.config.app_version,
            "release_channel": self.config.release_channel,
            "release_build": self.config.release_build,
            "http_base_url": self.advertised_http_base_url,
            "mesh_post_url": self.mesh_post_url,
            "gossip_bind": self._advertised_gossip_host(),
            "gossip_port": self._advertised_gossip_port(),
            "candidates": self.refresh_candidates(),
            "relay_capable": bool(self.config.relay_enable),
            "capacity": self.local_capacity,
            "reputation_score": self.local_reputation_score,
            "resource_reputation": self.local_resource_reputation,
            "activity": self.local_activity,
            "task_queue": self.local_task_queue,
            "timestamp_utc": utc_now(),
        }

    def _handle_gossip_event(self, message: dict[str, Any], sender: str) -> None:
        """Apply a new gossip event locally, then forward it (bounded hops)."""
        if not self._record_event(message):
            return
        topic = str(message.get("topic", ""))
        if topic == "software_update":
            self._record_update_announcement(message.get("payload"), str(message.get("node_id", "")))
        elif topic == "task_control" and self.node is not None:
            payload = message.get("payload")
            if isinstance(payload, dict):
                self.node.apply_task_control(payload, signed_by=str(message.get("node_id", "")))
        hops = int(message.get("hops", 0) or 0)
        if hops >= max(1, int(self.config.gossip_max_hops)):
            return
        forwarded = dict(message)
        forwarded["hops"] = hops + 1
        self._schedule_gossip_broadcast(forwarded, exclude=sender)

    def _handle_udp_message(self, message: dict[str, Any], sender: str) -> None:
        self._handle_network_message(message, sender)
