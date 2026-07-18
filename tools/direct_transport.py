from __future__ import annotations

import socket
import time
import uuid
from typing import Any, Callable, Mapping


class DirectTransportBackend:
    name = "abstract"

    def direct_sessions_snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    def establish_session(self, punch_start: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def handle_punch_probe(self, message: Mapping[str, Any], sender: str) -> None:
        raise NotImplementedError

    def handle_punch_ack(self, message: Mapping[str, Any]) -> None:
        raise NotImplementedError


class NativeLightDirectTransport(DirectTransportBackend):
    name = "native-light"

    def __init__(
        self,
        node: Any,
        *,
        safe_id: Callable[[str], str],
        utc_now: Callable[[], str],
        atomic_write_json: Callable[[Any, Any], None],
    ) -> None:
        self.node = node
        self.safe_id = safe_id
        self.utc_now = utc_now
        self.atomic_write_json = atomic_write_json

    def direct_sessions_snapshot(self) -> dict[str, Any]:
        with self.node._lock:
            sessions = sorted(self.node._direct_sessions.values(), key=lambda item: str(item.get("session_id", "")))
        payload = {"schema_version": 1, "node_id": self.node.node_id, "count": len(sessions), "sessions": sessions, "updated_utc": self.utc_now()}
        self.atomic_write_json(self.node.direct_sessions_path, payload)
        return payload

    def establish_session(self, punch_start: Mapping[str, Any]) -> dict[str, Any]:
        if not self.node.config.nat_punch_enable:
            return self._direct_failure("", "nat_punch_disabled")
        if not isinstance(punch_start, Mapping) or str(punch_start.get("message_type", "")) != "punch_start":
            return self._direct_failure("", "punch_start_invalid")
        if punch_start.get("signature") and not self.node._verify_message(dict(punch_start)):
            return self._direct_failure(str(punch_start.get("session_id", "")), "punch_start_signature_invalid")
        session_id = str(punch_start.get("session_id", "")).strip()
        initiator_peer_id = self.safe_id(str(punch_start.get("initiator_peer_id", "")))
        target_peer_id = self.safe_id(str(punch_start.get("target_peer_id", "")))
        if not session_id or self.node.node_id not in {initiator_peer_id, target_peer_id}:
            return self._direct_failure(session_id, "wrong_peer_id")
        remote_peer_id = target_peer_id if self.node.node_id == initiator_peer_id else initiator_peer_id
        pairs = self._candidate_pairs_for_local(punch_start)
        if not pairs:
            return self._direct_failure(session_id, "no_candidate_pair", remote_peer_id=remote_peer_id)
        started = time.monotonic()
        timeout_s = max(1, int(self.node.config.p2p_session_timeout_ms)) / 1000.0
        retry_count = max(1, int(self.node.config.p2p_punch_retry_count))
        interval_s = max(1, int(self.node.config.p2p_punch_interval_ms)) / 1000.0
        with self.node._lock:
            self.node._direct_sessions[session_id] = {
                "schema_version": 1,
                "session_id": session_id,
                "status": "punching",
                "local_peer_id": self.node.node_id,
                "remote_peer_id": remote_peer_id,
                "transport_backend": self.name,
                "candidate_pairs": pairs,
                "sent_probes": {},
                "seen_ack_nonces": [],
                "created_unix": int(time.time()),
                "updated_utc": self.utc_now(),
            }
        self._write_direct_sessions_snapshot()
        for _attempt in range(retry_count):
            if time.monotonic() - started >= timeout_s:
                break
            for pair in pairs:
                self._send_punch_probe(session_id, remote_peer_id, pair)
            if self._direct_session_status(session_id) == "direct":
                return self._direct_session_result(session_id)
            time.sleep(min(interval_s, max(0.0, timeout_s - (time.monotonic() - started))))
            if self._direct_session_status(session_id) == "direct":
                return self._direct_session_result(session_id)
        with self.node._lock:
            session = self.node._direct_sessions.get(session_id, {})
            if session.get("status") != "direct":
                session["status"] = "failed"
                session["failure_reason"] = "timeout"
                session["updated_utc"] = self.utc_now()
                self.node._direct_sessions[session_id] = session
        self._write_direct_sessions_snapshot()
        return self._direct_session_result(session_id)

    def _candidate_pairs_for_local(self, punch_start: Mapping[str, Any]) -> list[dict[str, Any]]:
        initiator_peer_id = self.safe_id(str(punch_start.get("initiator_peer_id", "")))
        target_peer_id = self.safe_id(str(punch_start.get("target_peer_id", "")))
        raw_pairs = punch_start.get("candidate_pairs", [])
        if not isinstance(raw_pairs, list):
            return []
        pairs: list[dict[str, Any]] = []
        for raw_pair in raw_pairs:
            if not isinstance(raw_pair, Mapping):
                continue
            local_candidate = raw_pair.get("local_candidate")
            remote_candidate = raw_pair.get("remote_candidate")
            if self.node.node_id == target_peer_id:
                local_candidate, remote_candidate = remote_candidate, local_candidate
            elif self.node.node_id != initiator_peer_id:
                continue
            now = int(time.time())
            local = self.node._normalize_candidate(local_candidate, self.node.node_id, now)
            remote_id = target_peer_id if self.node.node_id == initiator_peer_id else initiator_peer_id
            remote = self.node._normalize_candidate(remote_candidate, remote_id, now)
            if local is None or remote is None:
                continue
            if str(local.get("transport", "")) != "udp" or str(remote.get("transport", "")) != "udp":
                continue
            if str(local.get("address_family", "")) != str(remote.get("address_family", "")):
                continue
            if not self._udp_candidate_family_supported(str(local.get("address_family", ""))):
                continue
            pairs.append(
                {
                    "local_candidate_id": str(local.get("candidate_id", "")),
                    "remote_candidate_id": str(remote.get("candidate_id", "")),
                    "transport": "udp",
                    "address_family": str(local.get("address_family", "")),
                    "priority": int(raw_pair.get("priority", 0) or 0),
                    "local_candidate": local,
                    "remote_candidate": remote,
                }
            )
        pairs.sort(key=lambda pair: int(pair.get("priority", 0) or 0), reverse=True)
        return pairs

    def _udp_candidate_family_supported(self, address_family: str) -> bool:
        if self.node._udp_socket is None:
            return address_family == "ipv4"
        if address_family == "ipv6":
            return self.node._udp_socket.family == socket.AF_INET6
        return self.node._udp_socket.family == socket.AF_INET

    def _send_punch_probe(self, session_id: str, remote_peer_id: str, pair: Mapping[str, Any]) -> None:
        remote = pair.get("remote_candidate") if isinstance(pair.get("remote_candidate"), Mapping) else {}
        host = str(remote.get("ip", "")).strip()
        port = int(remote.get("port", 0) or 0)
        if not host or port <= 0:
            return
        nonce = uuid.uuid4().hex
        message = {
            "message_type": "punch_probe",
            "session_id": session_id,
            "peer_id": self.node.node_id,
            "target_peer_id": remote_peer_id,
            "candidate_id": str(pair.get("local_candidate_id", "")),
            "remote_candidate_id": str(pair.get("remote_candidate_id", "")),
            "nonce": nonce,
            "timestamp_unix": int(time.time()),
        }
        self.node._sign_message(message)
        with self.node._lock:
            session = self.node._direct_sessions.get(session_id, {})
            sent = session.get("sent_probes", {}) if isinstance(session.get("sent_probes"), dict) else {}
            sent[nonce] = {
                "sent_monotonic": time.monotonic(),
                "local_candidate_id": str(pair.get("local_candidate_id", "")),
                "remote_candidate_id": str(pair.get("remote_candidate_id", "")),
            }
            session["sent_probes"] = sent
            self.node._direct_sessions[session_id] = session
        self.node._send_udp(f"{host}:{port}", host, port, message)

    def handle_punch_probe(self, message: Mapping[str, Any], sender: str) -> None:
        session_id = str(message.get("session_id", "")).strip()
        peer_id = self.safe_id(str(message.get("peer_id", "")))
        target_peer_id = self.safe_id(str(message.get("target_peer_id", "")))
        nonce = str(message.get("nonce", "")).strip()
        if not session_id or not nonce or target_peer_id != self.node.node_id or peer_id == self.node.node_id:
            return
        replay_key = f"probe:{session_id}:{peer_id}:{nonce}"
        with self.node._lock:
            session = self.node._direct_sessions.get(session_id)
            if not isinstance(session, dict) or str(session.get("remote_peer_id", "")) != peer_id:
                return
            if replay_key in self.node._seen_punch_nonces:
                return
            self.node._seen_punch_nonces.add(replay_key)
        host, port = self.node._parse_udp_target(sender)
        if not host or port <= 0:
            return
        ack = {
            "message_type": "punch_ack",
            "session_id": session_id,
            "peer_id": self.node.node_id,
            "target_peer_id": peer_id,
            "probe_nonce": nonce,
            "selected_remote_candidate_id": str(message.get("candidate_id", "")),
            "selected_local_candidate_id": self._best_local_candidate_id(session),
            "nonce": uuid.uuid4().hex,
            "timestamp_unix": int(time.time()),
        }
        self.node._sign_message(ack)
        self.node._send_udp(sender, host, port, ack)

    def handle_punch_ack(self, message: Mapping[str, Any]) -> None:
        session_id = str(message.get("session_id", "")).strip()
        peer_id = self.safe_id(str(message.get("peer_id", "")))
        target_peer_id = self.safe_id(str(message.get("target_peer_id", "")))
        ack_nonce = str(message.get("nonce", "")).strip()
        probe_nonce = str(message.get("probe_nonce", "")).strip()
        if not session_id or not ack_nonce or target_peer_id != self.node.node_id:
            return
        replay_key = f"ack:{session_id}:{peer_id}:{ack_nonce}"
        with self.node._lock:
            session = self.node._direct_sessions.get(session_id)
            if not isinstance(session, dict) or str(session.get("remote_peer_id", "")) != peer_id:
                return
            if replay_key in self.node._seen_punch_nonces:
                return
            self.node._seen_punch_nonces.add(replay_key)
            sent = session.get("sent_probes", {}) if isinstance(session.get("sent_probes"), dict) else {}
            sent_probe = sent.get(probe_nonce, {}) if isinstance(sent.get(probe_nonce, {}), dict) else {}
            if not sent_probe:
                return
            rtt_ms = int(max(0.0, time.monotonic() - float(sent_probe.get("sent_monotonic", time.monotonic()))) * 1000)
            current_rtt = int(session.get("rtt_ms", 2**31 - 1) or 2**31 - 1)
            if str(session.get("status", "")) == "direct" and current_rtt <= rtt_ms:
                self._remember_ack_nonce(session, ack_nonce)
                self.node._direct_sessions[session_id] = session
                return
            session["status"] = "direct"
            session["transport_backend"] = self.name
            session["rtt_ms"] = rtt_ms
            session["selected_candidate_pair"] = {
                "local_candidate_id": str(sent_probe.get("local_candidate_id", "")),
                "remote_candidate_id": str(sent_probe.get("remote_candidate_id", "")),
                "ack_local_candidate_id": str(message.get("selected_remote_candidate_id", "")),
                "ack_remote_candidate_id": str(message.get("selected_local_candidate_id", "")),
            }
            session["updated_utc"] = self.utc_now()
            self._remember_ack_nonce(session, ack_nonce)
            self.node._direct_sessions[session_id] = session
        self._write_direct_sessions_snapshot()

    def _remember_ack_nonce(self, session: dict[str, Any], ack_nonce: str) -> None:
        seen = session.get("seen_ack_nonces", []) if isinstance(session.get("seen_ack_nonces"), list) else []
        if ack_nonce not in seen:
            seen.append(ack_nonce)
        session["seen_ack_nonces"] = seen[-32:]

    def _best_local_candidate_id(self, session: Mapping[str, Any]) -> str:
        pairs = session.get("candidate_pairs", []) if isinstance(session.get("candidate_pairs"), list) else []
        if not pairs:
            return ""
        first = pairs[0] if isinstance(pairs[0], Mapping) else {}
        return str(first.get("local_candidate_id", ""))

    def _direct_session_status(self, session_id: str) -> str:
        with self.node._lock:
            return str(self.node._direct_sessions.get(session_id, {}).get("status", ""))

    def _direct_session_result(self, session_id: str) -> dict[str, Any]:
        with self.node._lock:
            session = dict(self.node._direct_sessions.get(session_id, {}))
        if not session:
            return self._direct_failure(session_id, "session_missing")
        return dict(session)

    def _direct_failure(self, session_id: str, reason: str, *, remote_peer_id: str = "") -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": str(session_id),
            "status": "failed",
            "local_peer_id": self.node.node_id,
            "remote_peer_id": self.safe_id(remote_peer_id) if remote_peer_id else "",
            "transport_backend": self.name,
            "failure_reason": reason,
            "updated_utc": self.utc_now(),
        }

    def _write_direct_sessions_snapshot(self) -> None:
        with self.node._lock:
            sessions = sorted(self.node._direct_sessions.values(), key=lambda item: str(item.get("session_id", "")))
        self.atomic_write_json(
            self.node.direct_sessions_path,
            {"schema_version": 1, "node_id": self.node.node_id, "count": len(sessions), "sessions": sessions, "updated_utc": self.utc_now()},
        )
