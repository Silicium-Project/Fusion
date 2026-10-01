"""Signaling client side: open ICE content sessions and answer pending sessions."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from tools.node.util import safe_id, stable_json


class SignalingClientMixin:
    """Drive signaling sessions against a rendezvous node."""

    def _open_ice_content_session(self, peer: dict[str, Any], content_id: str) -> str:
        target_peer_id = safe_id(str(peer.get("node_id", "")))
        if not target_peer_id:
            return ""
        signaling_targets = self._signaling_targets()
        if not signaling_targets:
            direct_target = str(peer.get("http_base_url", "")).rstrip("/")
            if direct_target:
                signaling_targets.append(direct_target)
        request_payload = {
            "peer_id": self.node_id,
            "target_peer_id": target_peer_id,
            "purpose": "content_fetch",
            "content_id": content_id,
            "allowed_transports": ["ice"],
        }
        for base_url in signaling_targets:
            try:
                response = self._post_peer_json(base_url, "/p2p/sessions/request", request_payload)
                session = response.get("session") if isinstance(response.get("session"), dict) else {}
                session_id = str(session.get("session_id", "")).strip()
                if not session_id:
                    continue
                ready = self.build_session_ready_payload(session)
                self._signaling_ready_payloads[session_id] = ready
                deadline = time.monotonic() + max(8.0, float(self.config.p2p_session_timeout_ms) / 1000.0)
                while time.monotonic() < deadline:
                    ready_response = self._post_peer_json(base_url, f"/p2p/sessions/{session_id}/ready", ready)
                    ready_session = ready_response.get("session") if isinstance(ready_response.get("session"), dict) else {}
                    punch_start = ready_response.get("punch_start") if isinstance(ready_response.get("punch_start"), dict) else {}
                    ice = punch_start.get("ice") if isinstance(punch_start.get("ice"), dict) else {}
                    ice_peers = ice.get("peers") if isinstance(ice.get("peers"), dict) else {}
                    if str(ready_session.get("status", "")) == "punching" and len(ice_peers) >= 2:
                        result = self.establish_direct_udp_session(punch_start)
                        self._report_signaling_result(base_url, session_id, result)
                        return session_id if result.get("status") == "direct" else ""
                    time.sleep(0.1)
            except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError):
                continue
        return ""

    def _signaling_targets(self) -> list[str]:
        targets: set[str] = set()
        for seed in self.config.discovery_seeds + self.config.seed_peers:
            normalized = self._normalize_http_target(seed)
            if normalized and normalized != self.advertised_http_base_url:
                targets.add(normalized)
        return sorted(targets)

    def _poll_signaling_sessions(self, base_url: str) -> None:
        path = "/p2p/sessions/pending"
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            headers=self._signed_headers("GET", path, b""),
        )
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            return
        sessions = payload.get("sessions") if isinstance(payload, dict) else None
        if not isinstance(sessions, list):
            return
        for session in sessions:
            if not isinstance(session, dict) or safe_id(str(session.get("target_peer_id", ""))) != self.node_id:
                continue
            session_id = str(session.get("session_id", "")).strip()
            if not session_id:
                continue
            with self._lock:
                if session_id in self._started_direct_sessions:
                    continue
            ready = self._signaling_ready_payloads.get(session_id)
            if ready is None:
                ready = self.build_session_ready_payload(session)
                self._signaling_ready_payloads[session_id] = ready
            try:
                ready_response = self._post_peer_json(base_url, f"/p2p/sessions/{session_id}/ready", ready)
            except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError):
                continue
            ready_session = ready_response.get("session") if isinstance(ready_response.get("session"), dict) else {}
            punch_start = ready_response.get("punch_start") if isinstance(ready_response.get("punch_start"), dict) else {}
            if str(ready_session.get("status", "")) == "punching":
                self._start_direct_session_background(punch_start, base_url)

    def _post_peer_json(self, base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        raw = stable_json(payload).encode("utf-8")
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=raw,
            method="POST",
            headers=self._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("peer_response_not_object")
        return body

    def _report_signaling_result(self, base_url: str, session_id: str, result: Mapping[str, Any]) -> None:
        pair = result.get("selected_candidate_pair") if isinstance(result.get("selected_candidate_pair"), Mapping) else {}
        path_attestation = next(
            (
                item
                for item in self.recent_transport_attestations(16)
                if str(item.get("session_id", "")) == session_id
                and str(item.get("proof_scope", "")) == "connectivity_check"
            ),
            {},
        )
        try:
            self._post_peer_json(
                base_url,
                f"/p2p/sessions/{session_id}/result",
                {
                    "ok": result.get("status") == "direct",
                    "transport": "direct" if result.get("status") == "direct" else "failed",
                    "error": result.get("failure_reason", ""),
                    "selected_local_candidate_id": pair.get("local_candidate_id", ""),
                    "selected_remote_candidate_id": pair.get("remote_candidate_id", ""),
                    "path_attestation": path_attestation,
                },
            )
        except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            pass
