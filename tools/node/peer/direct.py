"""Direct (ICE / native UDP) sessions and relayed UDP hole punching."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
import uuid
from typing import Any, Mapping

from tools.node.util import stable_json, utc_now


class DirectSessionsMixin:
    """Establish direct peer sessions through the configured transport backend."""

    def direct_sessions_snapshot(self) -> dict[str, Any]:
        """Direct sessions known to the transport backend."""
        return self.direct_transport.direct_sessions_snapshot()

    def direct_transport_snapshot(self) -> dict[str, Any]:
        """Backend, features and latest route (served on /p2p/transport)."""
        requested = str(self.config.p2p_direct_transport_backend or "auto").strip().lower() or "auto"
        features = self.direct_transport.features()
        attestations = self.recent_transport_attestations(8)
        return {
            "schema_version": 1,
            "node_id": self.node_id,
            "requested_backend": requested,
            "active_backend": self.direct_transport.name,
            "features": features,
            "ice_enabled": "ice_v1" in features,
            "nat_punch_enabled": bool(self.config.nat_punch_enable),
            "stun_configured": bool(self.config.p2p_stun_server),
            "turn_configured": bool(self.config.p2p_turn_server),
            "latest_transport_route": str(attestations[0].get("route", "")) if attestations else "",
            "transport_attestations": attestations,
            "updated_utc": utc_now(),
        }

    def establish_direct_udp_session(self, punch_start: Mapping[str, Any]) -> dict[str, Any]:
        """Run the backend's connectivity checks for a ``punch_start``."""
        return self.direct_transport.establish_session(punch_start)

    def _start_direct_session_background(self, punch_start: Mapping[str, Any], signaling_base_url: str = "") -> None:
        if not isinstance(punch_start, Mapping):
            return
        ice = punch_start.get("ice") if isinstance(punch_start.get("ice"), Mapping) else {}
        peers = ice.get("peers") if isinstance(ice.get("peers"), Mapping) else {}
        if len(peers) < 2:
            return
        session_id = str(punch_start.get("session_id", "")).strip()
        if not session_id:
            return
        with self._lock:
            if session_id in self._started_direct_sessions:
                return
            self._started_direct_sessions.add(session_id)

        def _establish_target_session() -> None:
            result = self.establish_direct_udp_session(punch_start)
            if signaling_base_url:
                self._report_signaling_result(signaling_base_url, session_id, result)
            else:
                pair = result.get("selected_candidate_pair") if isinstance(result.get("selected_candidate_pair"), dict) else {}
                path_attestation = next(
                    (
                        item
                        for item in self.recent_transport_attestations(16)
                        if str(item.get("session_id", "")) == session_id
                        and str(item.get("proof_scope", "")) == "connectivity_check"
                    ),
                    {},
                )
                self.record_session_result(
                    session_id,
                    {
                        "ok": result.get("status") == "direct",
                        "transport": "direct" if result.get("status") == "direct" else "failed",
                        "error": result.get("failure_reason", ""),
                        "selected_local_candidate_id": pair.get("local_candidate_id", ""),
                        "selected_remote_candidate_id": pair.get("remote_candidate_id", ""),
                        "path_attestation": path_attestation,
                    },
                    self.node_id,
                )

        threading.Thread(target=_establish_target_session, name=f"ice-target-{session_id}", daemon=True).start()

    def build_session_ready_payload(self, session: Mapping[str, Any]) -> dict[str, Any]:
        """Backend-specific payload for a session ``ready`` call."""
        return self.direct_transport.build_session_ready_payload(session)

    def _handle_direct_punch_probe(self, message: Mapping[str, Any], sender: str) -> None:
        self.direct_transport.handle_punch_probe(message, sender)

    def _handle_punch_ack(self, message: Mapping[str, Any]) -> None:
        self.direct_transport.handle_punch_ack(message)

    def request_udp_punch(self, target_peer_id: str) -> bool:
        """Ask the target (or a relay) to coordinate a UDP punch; True if accepted."""
        if not self.config.nat_punch_enable:
            return False
        session_id = "punch-" + uuid.uuid4().hex
        handshake = self.create_session_handshake(
            target_peer_id=target_peer_id,
            session_id=session_id,
            purpose="nat_punch",
            candidate_fingerprints=[
                {"candidate_id": str(candidate.get("candidate_id", "")), "expires_unix": int(candidate.get("expires_unix", 0) or 0)}
                for candidate in self.refresh_candidates()
            ],
        )

        target_urls: list[str] = []
        target_peers = [
            peer
            for peer in self.peers_snapshot().get("peers", [])
            if str(peer.get("node_id", "")) == target_peer_id
        ]
        if target_peers:
            target_peer = target_peers[0]
            if target_peer.get("http_base_url"):
                target_urls.append(str(target_peer["http_base_url"]).rstrip("/"))
            for cand in target_peer.get("candidates", []):
                if isinstance(cand, dict) and cand.get("ip") and cand.get("port"):
                    ip = str(cand["ip"])
                    port = cand["port"]
                    formatted_ip = f"[{ip}]" if ":" in ip else ip
                    cand_url = f"http://{formatted_ip}:{port}".rstrip("/")
                    if cand_url not in target_urls:
                        target_urls.append(cand_url)

        relays = self.select_peers(required_roles=set(), limit=max(1, self.config.relay_hops), require_relay=True, exclude={target_peer_id})
        for relay in relays:
            relay_url = str(relay.get("http_base_url", "")).rstrip("/")
            if relay_url and relay_url not in target_urls:
                target_urls.append(relay_url)

        payload = {"target_peer_id": target_peer_id, "session_id": session_id, "handshake": handshake}
        raw = stable_json(payload).encode("utf-8")
        path = "/relay/punch"

        for base_url in target_urls:
            request = urllib.request.Request(
                base_url + path,
                data=raw,
                method="POST",
                headers=self._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    if response.status in {200, 202}:
                        return True
            except Exception:
                continue
        return False
