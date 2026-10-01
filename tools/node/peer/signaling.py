"""Rendezvous signaling sessions (server side): create, ready, result, close, expire."""

from __future__ import annotations

import time
import uuid
from typing import Any, Mapping

from tools.node.util import (
    append_jsonl,
    atomic_write_json,
    optional_peer_id,
    read_json,
    safe_id,
    safe_path_id,
    utc_now,
)


class SignalingMixin:
    """Broker direct-connection sessions between two registered peers."""

    def sessions_snapshot(self) -> dict[str, Any]:
        """Persist and return the live signaling sessions."""
        self._prune_expired_sessions()
        with self._lock:
            sessions = sorted(self._sessions.values(), key=lambda item: str(item.get("session_id", "")))
        payload = {"schema_version": 1, "node_id": self.node_id, "count": len(sessions), "sessions": sessions, "updated_utc": utc_now()}
        atomic_write_json(self.sessions_path, payload)
        return payload

    def create_signaling_session(self, payload: Mapping[str, Any], requester_node_id: str) -> tuple[int, dict[str, Any]]:
        """Open a session between the requester and a target; ``(status, body)``."""
        self._prune_expired_sessions()
        requester_id = safe_id(str(payload.get("peer_id", requester_node_id)))
        requester_node_id = safe_id(requester_node_id)
        target_peer_id = safe_id(str(payload.get("target_peer_id", "")))
        task_id = safe_id(str(payload.get("task_id", ""))) if str(payload.get("task_id", "")).strip() else ""
        purpose = safe_id(str(payload.get("purpose", "direct_session")))
        content_id = str(payload.get("content_id", "") or payload.get("payload_id", "")).strip()
        allowed_transports = {
            safe_id(str(item)).lower()
            for item in (payload.get("allowed_transports", []) if isinstance(payload.get("allowed_transports", []), list) else [])
            if str(item).strip()
        }
        if requester_node_id and requester_id != requester_node_id:
            return 403, {"ok": False, "error": "requester_mismatch"}
        if not requester_id or not target_peer_id or requester_id == target_peer_id:
            return 400, {"ok": False, "error": "invalid_peer_pair"}
        allowed, reason = self._authorize_session_pair(requester_id, target_peer_id, task_id, purpose, content_id)
        if not allowed:
            return 403, {"ok": False, "error": reason}
        requester_peer = self._peer_for_signaling(requester_id)
        target_peer = self._peer_for_signaling(target_peer_id)
        if requester_peer is None or target_peer is None:
            return 404, {"ok": False, "error": "peer_not_registered"}
        candidate_pairs = self._candidate_pairs(requester_peer, target_peer)
        allow_ice_ready_candidates = "ice" in allowed_transports or (
            "ice_v1" in set(requester_peer.get("features", [])) and "ice_v1" in set(target_peer.get("features", []))
        )
        if not candidate_pairs and not allow_ice_ready_candidates:
            return 409, {"ok": False, "error": "no_valid_candidate_pair"}
        now = int(time.time())
        ttl_s = max(1, int(self.config.p2p_session_ttl_s))
        session_id = "p2p-sess-" + uuid.uuid4().hex
        session = {
            "schema_version": 1,
            "session_id": session_id,
            "status": "signaling",
            "initiator_peer_id": requester_id,
            "target_peer_id": target_peer_id,
            "purpose": purpose,
            "task_id": task_id,
            "content_id": content_id,
            "candidate_pairs": candidate_pairs,
            "allowed_transports": sorted(allowed_transports),
            "ready_peers": [],
            "ready_transports": {},
            "results": [],
            "created_unix": now,
            "expires_unix": now + ttl_s,
            "updated_utc": utc_now(),
        }
        with self._lock:
            self._sessions[session_id] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_created", session)
        return 201, {"ok": True, "session": self._session_response(session)}

    def mark_session_ready(self, session_id: str, requester_node_id: str, payload: Mapping[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        """Mark a participant ready; returns the signed ``punch_start``."""
        session, error = self._session_for_peer(session_id, requester_node_id)
        if session is None:
            return error
        if str(session.get("status", "")) in {"direct", "relay", "completed"}:
            return 200, {"ok": True, "session": self._session_response(session), "punch_start": self._punch_start_message(session)}
        payload = payload or {}
        peer_id = safe_id(requester_node_id)
        ready = list(session.get("ready_peers", [])) if isinstance(session.get("ready_peers"), list) else []
        if peer_id not in ready:
            ready.append(peer_id)
        session["ready_peers"] = sorted(ready)
        if isinstance(payload, Mapping) and payload:
            ready_transports = dict(session.get("ready_transports", {})) if isinstance(session.get("ready_transports"), dict) else {}
            transport_payload = {
                "direct_transport_backend": str(payload.get("direct_transport_backend", "")),
                "ice": payload.get("ice", {}) if isinstance(payload.get("ice", {}), Mapping) else {},
            }
            ready_transports[peer_id] = transport_payload
            session["ready_transports"] = ready_transports
        session["status"] = "punching" if {session["initiator_peer_id"], session["target_peer_id"]}.issubset(set(ready)) else "ready_wait"
        session["updated_utc"] = utc_now()
        with self._lock:
            self._sessions[str(session["session_id"])] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_ready", session, {"peer_id": peer_id})
        return 200, {"ok": True, "session": self._session_response(session), "punch_start": self._punch_start_message(session)}

    def record_session_result(self, session_id: str, payload: Mapping[str, Any], requester_node_id: str) -> tuple[int, dict[str, Any]]:
        """Record a participant's connectivity result (attestation checked)."""
        session, error = self._session_for_peer(session_id, requester_node_id)
        if session is None:
            return error
        peer_id = safe_id(requester_node_id)
        ok = bool(payload.get("ok", False))
        transport = safe_id(str(payload.get("transport", "direct")))
        path_attestation = payload.get("path_attestation")
        if path_attestation:
            if (
                not isinstance(path_attestation, Mapping)
                or str(path_attestation.get("observer_peer_id", "")) != peer_id
                or str(path_attestation.get("session_id", "")) != str(session_id)
                or str(path_attestation.get("route", "")) != (transport if ok else "failed")
                or not self.verify_transport_attestation(path_attestation)
            ):
                return 400, {"ok": False, "error": "transport_attestation_invalid"}
        result = {
            "peer_id": peer_id,
            "ok": ok,
            "transport": transport,
            "selected_local_candidate_id": str(payload.get("selected_local_candidate_id", "")),
            "selected_remote_candidate_id": str(payload.get("selected_remote_candidate_id", "")),
            "error": str(payload.get("error", "")),
            "path_attestation": dict(path_attestation) if isinstance(path_attestation, Mapping) else {},
            "attestation_verified": bool(path_attestation) and isinstance(path_attestation, Mapping),
            "timestamp_unix": int(time.time()),
        }
        results = list(session.get("results", [])) if isinstance(session.get("results"), list) else []
        results.append(result)
        session["results"] = results[-8:]
        session["status"] = transport if ok and transport in {"direct", "relay"} else ("failed" if not ok else "completed")
        session["updated_utc"] = utc_now()
        with self._lock:
            self._sessions[str(session["session_id"])] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_result", session, result)
        return 200, {"ok": True, "session": self._session_response(session)}

    def close_session(self, session_id: str, payload: Mapping[str, Any], requester_node_id: str) -> tuple[int, dict[str, Any]]:
        """Close a session on behalf of a participant."""
        session, error = self._session_for_peer(session_id, requester_node_id)
        if session is None:
            return error
        peer_id = safe_id(requester_node_id)
        session["status"] = "closed"
        session["closed_by"] = peer_id
        session["close_reason"] = safe_id(str(payload.get("reason", "closed")))
        session["updated_utc"] = utc_now()
        with self._lock:
            self._sessions[str(session["session_id"])] = session
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_closed", session, {"peer_id": peer_id, "reason": session["close_reason"]})
        return 200, {"ok": True, "session": self._session_response(session)}

    def _load_persisted_sessions(self) -> None:
        snapshot = read_json(self.sessions_path, {})
        sessions = snapshot.get("sessions") if isinstance(snapshot, dict) else None
        if not isinstance(sessions, list):
            return
        now = int(time.time())
        with self._lock:
            for session in sessions:
                if not isinstance(session, dict):
                    continue
                session_id = str(session.get("session_id", "")).strip()
                if not session_id or int(session.get("expires_unix", 0) or 0) <= now:
                    continue
                if str(session.get("status", "")) in {"closed", "failed"}:
                    continue
                self._sessions[session_id] = dict(session)

    def _write_sessions_snapshot(self) -> None:
        with self._lock:
            sessions = sorted(self._sessions.values(), key=lambda item: str(item.get("session_id", "")))
        atomic_write_json(
            self.sessions_path,
            {"schema_version": 1, "node_id": self.node_id, "count": len(sessions), "sessions": sessions, "updated_utc": utc_now()},
        )

    def _emit_signaling_event(self, event_type: str, session: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> None:
        payload = {
            "schema_version": 1,
            "timestamp_utc": utc_now(),
            "node_id": self.node_id,
            "event_type": event_type,
            "session_id": str(session.get("session_id", "")),
            "status": str(session.get("status", "")),
            "initiator_peer_id": str(session.get("initiator_peer_id", "")),
            "target_peer_id": str(session.get("target_peer_id", "")),
            "task_id": str(session.get("task_id", "")),
        }
        if extra:
            payload.update(dict(extra))
        append_jsonl(self.session_events_path, payload)

    def _authorize_session_pair(
        self,
        requester_id: str,
        target_peer_id: str,
        task_id: str,
        purpose: str,
        content_id: str = "",
    ) -> tuple[bool, str]:
        if not task_id:
            if purpose == "content_fetch" and content_id:
                return True, "ok"
            return (purpose in {"nat_punch", "diagnostic"}), "task_required"
        for directory in ("tasks", "requests"):
            path = self.export_dir / directory / f"{safe_path_id(safe_id(task_id))}.json"
            envelope = read_json(path, {})
            if not isinstance(envelope, dict) or not envelope:
                continue
            assigned = {
                self._optional_peer_id(envelope.get("dispatched_to", "")),
                self._optional_peer_id(envelope.get("assigned_peer_id", "")),
                self._optional_peer_id(envelope.get("target_peer_id", "")),
                self._optional_peer_id(envelope.get("handled_by", "")),
            }
            assigned.discard("")
            owners = {
                self._optional_peer_id(envelope.get("node_id", "")),
                self._optional_peer_id(envelope.get("dispatched_by", "")),
                self._optional_peer_id(envelope.get("requester_peer_id", "")),
                self.node_id,
            }
            owners.discard("")
            pair = {requester_id, target_peer_id}
            if assigned.intersection(pair) and (owners.intersection(pair) or self.node_id in pair):
                return True, "ok"
            if {requester_id, target_peer_id}.issubset(assigned):
                return True, "ok"
            return False, "task_peer_pair_unauthorized"
        return False, "task_not_found"

    def _optional_peer_id(self, value: Any) -> str:
        return optional_peer_id(value)

    def _peer_for_signaling(self, peer_id: str) -> dict[str, Any] | None:
        safe_peer_id = safe_id(peer_id)
        if safe_peer_id == self.node_id:
            self._record_self_peer()
        with self._lock:
            peer = self._peers.get(safe_peer_id)
            return dict(peer) if isinstance(peer, dict) else None

    def _candidate_pairs(self, initiator_peer: Mapping[str, Any], target_peer: Mapping[str, Any]) -> list[dict[str, Any]]:
        now = int(time.time())
        local = self._normalize_candidate_list(initiator_peer.get("candidates", []), str(initiator_peer.get("node_id", "")), now)
        remote = self._normalize_candidate_list(target_peer.get("candidates", []), str(target_peer.get("node_id", "")), now)
        pairs: list[dict[str, Any]] = []
        for local_candidate in local:
            for remote_candidate in remote:
                if str(local_candidate.get("transport", "")) != str(remote_candidate.get("transport", "")):
                    continue
                if str(local_candidate.get("address_family", "")) != str(remote_candidate.get("address_family", "")):
                    continue
                priority = self._candidate_pair_priority(local_candidate, remote_candidate)
                pairs.append(
                    {
                        "local_candidate_id": str(local_candidate.get("candidate_id", "")),
                        "remote_candidate_id": str(remote_candidate.get("candidate_id", "")),
                        "transport": str(local_candidate.get("transport", "udp")),
                        "address_family": str(local_candidate.get("address_family", "")),
                        "priority": priority,
                        "local_candidate": local_candidate,
                        "remote_candidate": remote_candidate,
                    }
                )
        pairs.sort(key=lambda pair: int(pair.get("priority", 0) or 0), reverse=True)
        return pairs

    def _candidate_pair_priority(self, local_candidate: Mapping[str, Any], remote_candidate: Mapping[str, Any]) -> int:
        score = int(local_candidate.get("priority", 0) or 0) + int(remote_candidate.get("priority", 0) or 0)
        if bool(local_candidate.get("internet_routable", False)):
            score += 1000
        if bool(remote_candidate.get("internet_routable", False)):
            score += 1000
        if str(local_candidate.get("candidate_type", "")) == "srflx":
            score += 200
        if str(remote_candidate.get("candidate_type", "")) == "srflx":
            score += 200
        return score

    def _session_response(self, session: Mapping[str, Any]) -> dict[str, Any]:
        response = dict(session)
        response["candidate_pairs"] = list(session.get("candidate_pairs", [])) if isinstance(session.get("candidate_pairs"), list) else []
        return response

    def _punch_start_message(self, session: Mapping[str, Any]) -> dict[str, Any]:
        message = {
            "message_type": "punch_start",
            "session_id": str(session.get("session_id", "")),
            "peer_id": self.node_id,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
            "initiator_peer_id": str(session.get("initiator_peer_id", "")),
            "target_peer_id": str(session.get("target_peer_id", "")),
            "candidate_pairs": list(session.get("candidate_pairs", [])) if isinstance(session.get("candidate_pairs"), list) else [],
            "retry": {
                "count": max(1, int(self.config.p2p_punch_retry_count)),
                "interval_ms": max(1, int(self.config.p2p_punch_interval_ms)),
                "timeout_ms": max(1, int(self.config.p2p_session_timeout_ms)),
            },
            "timestamp_unix": int(time.time()),
            "nonce": uuid.uuid4().hex,
        }
        ready_transports = session.get("ready_transports", {}) if isinstance(session.get("ready_transports"), Mapping) else {}
        ice_peers: dict[str, Any] = {}
        for peer_id in (str(session.get("initiator_peer_id", "")), str(session.get("target_peer_id", ""))):
            transport = ready_transports.get(peer_id) if isinstance(ready_transports.get(peer_id), Mapping) else {}
            ice = transport.get("ice") if isinstance(transport.get("ice"), Mapping) else {}
            if ice.get("supported") is True:
                ice_peers[peer_id] = dict(ice)
        if ice_peers:
            message["ice"] = {"peers": ice_peers}
        self._sign_message(message)
        return message

    def _session_for_peer(self, session_id: str, requester_node_id: str) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]]]:
        self._prune_expired_sessions()
        safe_session_id = str(session_id).strip()
        requester_id = safe_id(requester_node_id)
        with self._lock:
            session = dict(self._sessions.get(safe_session_id, {}))
        if not session:
            return None, (404, {"ok": False, "error": "session_not_found"})
        if int(session.get("expires_unix", 0) or 0) <= int(time.time()):
            self._expire_session(safe_session_id, session)
            return None, (410, {"ok": False, "error": "session_expired"})
        if str(session.get("status", "")) == "closed":
            return None, (409, {"ok": False, "error": "session_closed"})
        if requester_id not in {str(session.get("initiator_peer_id", "")), str(session.get("target_peer_id", "")), self.node_id}:
            return None, (403, {"ok": False, "error": "session_peer_unauthorized"})
        return session, (200, {"ok": True})

    def _prune_expired_sessions(self) -> None:
        now = int(time.time())
        expired: list[dict[str, Any]] = []
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                if int(session.get("expires_unix", 0) or 0) <= now and str(session.get("status", "")) not in {"closed", "direct", "relay"}:
                    expired_session = dict(session)
                    expired_session["status"] = "expired"
                    expired.append(expired_session)
                    self._sessions.pop(session_id, None)
        for session in expired:
            self._emit_signaling_event("session_expired", session)
        if expired:
            self._write_sessions_snapshot()

    def _expire_session(self, session_id: str, session: Mapping[str, Any]) -> None:
        expired = dict(session)
        expired["status"] = "expired"
        with self._lock:
            self._sessions.pop(session_id, None)
        self._write_sessions_snapshot()
        self._emit_signaling_event("session_expired", expired)
