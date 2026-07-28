from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import socket
import struct
import threading
import time
import uuid
from typing import Any, Callable, Mapping


class DirectTransportBackend:
    name = "abstract"

    def features(self) -> list[str]:
        return []

    def build_session_ready_payload(self, session: Mapping[str, Any]) -> dict[str, Any]:
        return {"direct_transport_backend": self.name}

    def direct_sessions_snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    def close(self) -> None:
        return None

    def request_content(self, session_id: str, content_id: str) -> tuple[bytes, dict[str, Any]] | None:
        return None

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

    def features(self) -> list[str]:
        return ["udp_punch_v1", "direct_transport:native-light"]

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
        self._attest_session(session_id)
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
            if not isinstance(session, dict):
                signaling = self.node._sessions.get(session_id)
                signaling_peers = (
                    {
                        str(signaling.get("initiator_peer_id", "")),
                        str(signaling.get("target_peer_id", "")),
                    }
                    if isinstance(signaling, Mapping)
                    else set()
                )
                if {self.node.node_id, peer_id} != signaling_peers:
                    return
                session = {
                    "schema_version": 1,
                    "session_id": session_id,
                    "status": "punching",
                    "local_peer_id": self.node.node_id,
                    "remote_peer_id": peer_id,
                    "transport_backend": self.name,
                    "created_unix": int(time.time()),
                    "updated_utc": self.utc_now(),
                }
                self.node._direct_sessions[session_id] = session
            elif str(session.get("remote_peer_id", "")) != peer_id:
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
            if not isinstance(session, dict):
                session = {
                    "schema_version": 1,
                    "session_id": session_id,
                    "status": "direct",
                    "local_peer_id": self.node.node_id,
                    "remote_peer_id": peer_id,
                    "transport_backend": self.name,
                    "created_unix": int(time.time()),
                    "updated_utc": self.utc_now(),
                }
                self.node._direct_sessions[session_id] = session
            elif str(session.get("remote_peer_id", "")) != peer_id:
                return
            if replay_key in self.node._seen_punch_nonces:
                return
            if str(session.get("status", "")) == "direct":
                return
            self.node._seen_punch_nonces.add(replay_key)
            sent = session.get("sent_probes", {}) if isinstance(session.get("sent_probes"), dict) else {}
            sent_probe = sent.get(probe_nonce, {}) if isinstance(sent.get(probe_nonce, {}), dict) else {}
            rtt_ms = int(max(0.0, time.monotonic() - float(sent_probe.get("sent_monotonic", time.monotonic()))) * 1000) if sent_probe else 10
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
        self._attest_session(session_id)

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

    def _attest_session(self, session_id: str) -> None:
        session = self._direct_session_result(session_id)
        status = str(session.get("status", ""))
        if status not in {"direct", "failed"}:
            return
        self.node.record_transport_attestation_background(
            route="direct" if status == "direct" else "failed",
            transport_backend=self.name,
            remote_peer_id=str(session.get("remote_peer_id", "")),
            session_id=session_id,
            proof_scope="connectivity_check",
            selected_candidate_pair=session.get("selected_candidate_pair", {}),
            success=status == "direct",
            failure_reason=str(session.get("failure_reason", "")),
        )

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


class IceDirectTransport(DirectTransportBackend):
    name = "ice"
    _FRAME_MAGIC = b"SILICIUM-ICE-DATA/1\n"
    _MAX_HEADER_BYTES = 65536
    _MAX_PAYLOAD_BYTES = 67108864
    # Keep ICE application datagrams below the common Internet MTU. Large
    # datagrams worked on loopback but were fragmented and dropped across NAT.
    # Stay below the common Internet MTU while reducing Python/aioice frame
    # overhead for fragment payloads. TURN and ICE already provide loss
    # recovery; smaller chunks only add scheduler-visible latency.
    _CHUNK_SIZE = 1200

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
        self._connections: dict[str, Any] = {}
        self._runtimes: dict[str, dict[str, Any]] = {}

    def features(self) -> list[str]:
        features = ["ice_v1", "direct_transport:ice"]
        if self.node.config.p2p_stun_server:
            features.append("stun_v1")
        if self.node.config.p2p_turn_server:
            features.append("turn_v1")
        return features

    def build_session_ready_payload(self, session: Mapping[str, Any]) -> dict[str, Any]:
        session_id = str(session.get("session_id", "")).strip()
        if not session_id:
            return {"direct_transport_backend": self.name, "ice": {"supported": False, "error": "session_id_missing"}}
        if not self.node.config.nat_punch_enable:
            return {"direct_transport_backend": self.name, "ice": {"supported": False, "error": "nat_punch_disabled"}}
        try:
            self._aioice()
            session_id = str(session.get("session_id", "")).strip()
            runtime = self._ensure_runtime(session_id)
            return self._submit(runtime, self._build_session_ready_payload(session))
        except ModuleNotFoundError:
            return {"direct_transport_backend": self.name, "ice": {"supported": False, "error": "aioice_missing"}}
        except Exception as exc:
            return {"direct_transport_backend": self.name, "ice": {"supported": False, "error": "ice_candidate_gather_failed", "details": str(exc)}}

    async def _build_session_ready_payload(self, session: Mapping[str, Any]) -> dict[str, Any]:
        session_id = str(session.get("session_id", "")).strip()
        connection = await self._prepare_connection(session_id, self._is_controlling(session))
        now = int(time.time())
        candidates = [self._candidate_to_wire(candidate, now) for candidate in list(getattr(connection, "local_candidates", []))]
        candidates = [candidate for candidate in candidates if candidate is not None]
        self._connections[session_id] = connection
        return {
            "direct_transport_backend": self.name,
            "ice": {
                "supported": True,
                "ufrag": str(getattr(connection, "local_username", "")),
                "pwd": str(getattr(connection, "local_password", "")),
                "candidates": candidates,
                "stun_server": self.node.config.p2p_stun_server,
                "turn_server": self._redacted_turn_server(),
            },
        }

    def direct_sessions_snapshot(self) -> dict[str, Any]:
        with self.node._lock:
            sessions = sorted(self.node._direct_sessions.values(), key=lambda item: str(item.get("session_id", "")))
        payload = {"schema_version": 1, "node_id": self.node.node_id, "count": len(sessions), "sessions": sessions, "updated_utc": self.utc_now()}
        self.atomic_write_json(self.node.direct_sessions_path, payload)
        return payload

    def request_content(self, session_id: str, content_id: str) -> tuple[bytes, dict[str, Any]] | None:
        runtime = self._runtimes.get(str(session_id))
        if runtime is None:
            return None
        try:
            return self._submit(runtime, self._request_content(runtime, str(session_id), str(content_id)))
        except (TimeoutError, OSError, RuntimeError, ValueError):
            return None

    async def _request_content(self, runtime: Mapping[str, Any], session_id: str, content_id: str) -> tuple[bytes, dict[str, Any]] | None:
        connection = self._connections.get(session_id)
        if connection is None or not hasattr(connection, "send"):
            return None
        request_id = uuid.uuid4().hex
        response_waiters = runtime.get("response_waiters")
        response_buffers = runtime.get("response_buffers")
        if not isinstance(response_waiters, dict) or not isinstance(response_buffers, dict):
            return None
        for _attempt in range(3):
            request_id = uuid.uuid4().hex
            waiter = asyncio.get_running_loop().create_future()
            response_waiters[request_id] = waiter
            header = self._signed_data_header(
                message_type="content_request",
                session_id=session_id,
                request_id=request_id,
                content_id=content_id,
                target_peer_id=str(runtime.get("remote_peer_id", "")),
            )
            try:
                await connection.send(self._pack_frame(header, b""))
                response_header, payload = await asyncio.wait_for(waiter, timeout=5.0)
            except asyncio.TimeoutError:
                continue
            finally:
                response_waiters.pop(request_id, None)
                response_buffers.pop(request_id, None)
            if not isinstance(response_header, Mapping) or str(response_header.get("status", "")) != "ok":
                return None
            expected_hash = str(response_header.get("content_hash", "")).strip()
            if expected_hash and expected_hash != hashlib.sha256(payload).hexdigest():
                return None
            with self.node._lock:
                session = dict(self.node._direct_sessions.get(session_id, {}))
            attestation = self.node.record_transport_attestation(
                route="direct",
                transport_backend=self.name,
                remote_peer_id=str(runtime.get("remote_peer_id", "")),
                session_id=session_id,
                proof_scope="payload_transfer",
                content_id=content_id,
                content_sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                selected_candidate_pair=session.get("selected_candidate_pair", {}),
                peer_proof=response_header,
                success=True,
            )
            return payload, {
                "source": "silicium-ice",
                "content_id": content_id,
                "session_id": session_id,
                "node_id": str(runtime.get("remote_peer_id", "")),
                "transport_backend": self.name,
                "size_bytes": len(payload),
                "transport_route": "direct",
                "path_attestation": attestation,
            }
        return None

    async def _data_loop(self, session_id: str, remote_peer_id: str, connection: Any, runtime: dict[str, Any]) -> None:
        while True:
            try:
                raw = await connection.recv()
            except Exception:
                return
            frame = self._unpack_frame(raw)
            if frame is None:
                continue
            header, payload = frame
            if str(header.get("session_id", "")) != session_id:
                continue
            if self.safe_id(str(header.get("source_peer_id", ""))) != self.safe_id(remote_peer_id):
                continue
            if self.safe_id(str(header.get("target_peer_id", ""))) != self.node.node_id:
                continue
            try:
                if abs(int(time.time()) - int(header.get("timestamp_unix", 0) or 0)) > 120:
                    continue
            except (TypeError, ValueError):
                continue
            message_type = str(header.get("message_type", ""))
            try:
                chunk_index = int(header.get("chunk_index", 0) or 0)
            except (TypeError, ValueError):
                continue
            compact_response_chunk = message_type == "content_response" and chunk_index > 0 and not header.get("signature")
            if not compact_response_chunk and not self.node._verify_message(dict(header)):
                continue
            if message_type == "content_response":
                waiters = runtime.get("response_waiters")
                buffers = runtime.get("response_buffers")
                request_id = str(header.get("request_id", ""))
                waiter = waiters.get(request_id) if isinstance(waiters, dict) else None
                if waiter is not None and isinstance(buffers, dict):
                    try:
                        chunk_count = int(header.get("chunk_count", 1) or 1)
                        total_size = int(header.get("total_size", len(payload)) or 0)
                    except (TypeError, ValueError):
                        continue
                    if chunk_count < 1 or chunk_count > self._MAX_PAYLOAD_BYTES // self._CHUNK_SIZE + 1 or chunk_index < 0 or chunk_index >= chunk_count:
                        continue
                    buffer = buffers.setdefault(request_id, {"header": dict(header), "chunks": {}, "count": chunk_count, "total_size": total_size})
                    if chunk_index == 0:
                        buffer["header"] = dict(header)
                    chunks = buffer.get("chunks") if isinstance(buffer.get("chunks"), dict) else {}
                    chunks.setdefault(chunk_index, payload)
                    buffer["chunks"] = chunks
                    if len(chunks) == chunk_count:
                        assembled = b"".join(chunks[index] for index in range(chunk_count))
                        if len(assembled) != int(buffer.get("total_size", len(assembled))):
                            continue
                        buffers.pop(request_id, None)
                        if not waiter.done():
                            waiter.set_result((dict(buffer.get("header", header)), assembled))
                continue
            if message_type != "content_request":
                continue
            content_id = str(header.get("content_id", "")).strip()
            ok, response_payload, reason = self.node._serve_direct_content(session_id, remote_peer_id, content_id)
            payload = response_payload if ok else b""
            content_hash = hashlib.sha256(payload).hexdigest() if ok else ""
            chunk_count = max(1, (len(payload) + self._CHUNK_SIZE - 1) // self._CHUNK_SIZE)
            for chunk_index in range(chunk_count):
                start = chunk_index * self._CHUNK_SIZE
                chunk = payload[start : start + self._CHUNK_SIZE]
                if chunk_index == 0:
                    response_header = self._signed_data_header(
                        message_type="content_response",
                        session_id=session_id,
                        request_id=str(header.get("request_id", "")),
                        content_id=content_id,
                        target_peer_id=remote_peer_id,
                        status="ok" if ok else "error",
                        failure_reason="" if ok else reason,
                        content_hash=content_hash,
                        chunk_index=chunk_index,
                        chunk_count=chunk_count,
                        total_size=len(payload),
                    )
                else:
                    response_header = {
                        "message_type": "content_response",
                        "session_id": session_id,
                        "request_id": str(header.get("request_id", "")),
                        "content_id": content_id,
                        "source_peer_id": self.node.node_id,
                        "target_peer_id": self.safe_id(remote_peer_id),
                        "timestamp_unix": int(time.time()),
                        "nonce": uuid.uuid4().hex,
                        "chunk_index": chunk_index,
                        "chunk_count": chunk_count,
                        "total_size": len(payload),
                    }
                try:
                    await connection.send(self._pack_frame(response_header, chunk))
                    # Avoid overflowing the receiver/NAT UDP queues when a
                    # large result expands into hundreds of MTU-safe chunks.
                    await asyncio.sleep(0.001)
                except Exception:
                    return

    def _signed_data_header(
        self,
        *,
        message_type: str,
        session_id: str,
        request_id: str,
        content_id: str,
        target_peer_id: str,
        status: str = "",
        failure_reason: str = "",
        content_hash: str = "",
        chunk_index: int = 0,
        chunk_count: int = 1,
        total_size: int = 0,
    ) -> dict[str, Any]:
        header = {
            "message_type": message_type,
            "session_id": session_id,
            "request_id": request_id,
            "content_id": content_id,
            "source_peer_id": self.node.node_id,
            "target_peer_id": self.safe_id(target_peer_id),
            "timestamp_unix": int(time.time()),
            "nonce": uuid.uuid4().hex,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "total_size": total_size,
        }
        if status:
            header["status"] = status
        if failure_reason:
            header["failure_reason"] = failure_reason
        if content_hash:
            header["content_hash"] = content_hash
        self.node._sign_message(header)
        return header

    def _pack_frame(self, header: Mapping[str, Any], payload: bytes) -> bytes:
        header_bytes = json.dumps(dict(header), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(header_bytes) > self._MAX_HEADER_BYTES or len(payload) > self._MAX_PAYLOAD_BYTES:
            raise ValueError("ice_frame_too_large")
        return self._FRAME_MAGIC + struct.pack("!II", len(header_bytes), len(payload)) + header_bytes + payload

    def _unpack_frame(self, raw: bytes) -> tuple[dict[str, Any], bytes] | None:
        if not isinstance(raw, bytes) or len(raw) < len(self._FRAME_MAGIC) + 8 or not raw.startswith(self._FRAME_MAGIC):
            return None
        offset = len(self._FRAME_MAGIC)
        header_size, payload_size = struct.unpack("!II", raw[offset : offset + 8])
        if header_size > self._MAX_HEADER_BYTES or payload_size > self._MAX_PAYLOAD_BYTES:
            return None
        start = offset + 8
        end_header = start + header_size
        end_payload = end_header + payload_size
        if end_payload != len(raw):
            return None
        try:
            header = json.loads(raw[start:end_header].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return (header, raw[end_header:end_payload]) if isinstance(header, dict) else None

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
        ice = punch_start.get("ice") if isinstance(punch_start.get("ice"), Mapping) else {}
        peers = ice.get("peers") if isinstance(ice.get("peers"), Mapping) else {}
        local_ice = peers.get(self.node.node_id) if isinstance(peers.get(self.node.node_id), Mapping) else {}
        remote_ice = peers.get(remote_peer_id) if isinstance(peers.get(remote_peer_id), Mapping) else {}
        if not local_ice or not remote_ice:
            return self._direct_failure(session_id, "ice_credentials_missing", remote_peer_id=remote_peer_id)
        try:
            self._aioice()
            runtime = self._ensure_runtime(session_id)
            return self._submit(runtime, self._establish_session(session_id, remote_peer_id, local_ice, remote_ice))
        except ModuleNotFoundError:
            return self._direct_failure(session_id, "aioice_missing", remote_peer_id=remote_peer_id)
        except TimeoutError:
            return self._store_failure(session_id, remote_peer_id, "ice_connect_timeout")
        except Exception as exc:
            return self._store_failure(session_id, remote_peer_id, "ice_connect_failed", details=str(exc))

    async def _establish_session(
        self,
        session_id: str,
        remote_peer_id: str,
        local_ice: Mapping[str, Any],
        remote_ice: Mapping[str, Any],
    ) -> dict[str, Any]:
        aioice = self._aioice()
        connection = await self._prepare_connection(
            session_id,
            self._is_controlling({"initiator_peer_id": self.node.node_id}),
            local_ice,
        )
        connection.remote_username = str(remote_ice.get("ufrag", ""))
        connection.remote_password = str(remote_ice.get("pwd", ""))
        if not connection.remote_username or not connection.remote_password:
            return self._store_failure(session_id, remote_peer_id, "ice_credentials_missing")
        remote_candidates = remote_ice.get("candidates", [])
        if not isinstance(remote_candidates, list) or not remote_candidates:
            return self._store_failure(session_id, remote_peer_id, "ice_remote_candidates_missing")
        for candidate in remote_candidates:
            parsed = self._wire_to_candidate(aioice, candidate)
            if parsed is not None:
                await connection.add_remote_candidate(parsed)
        await connection.add_remote_candidate(None)
        started = time.monotonic()
        timeout_s = max(1, int(self.node.config.p2p_session_timeout_ms)) / 1000.0
        try:
            await asyncio.wait_for(connection.connect(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return self._store_failure(session_id, remote_peer_id, "ice_connect_timeout")
        except Exception as exc:
            return self._store_failure(session_id, remote_peer_id, "ice_connect_failed", details=str(exc))
        rtt_ms = int(max(0.0, time.monotonic() - started) * 1000)
        local_default = self._candidate_to_wire(connection.get_default_candidate(1), int(time.time()))
        remote_first = next((candidate for candidate in remote_candidates if isinstance(candidate, Mapping)), {})
        session = {
            "schema_version": 1,
            "session_id": session_id,
            "status": "direct",
            "local_peer_id": self.node.node_id,
            "remote_peer_id": remote_peer_id,
            "transport_backend": self.name,
            "rtt_ms": rtt_ms,
            "selected_candidate_pair": {
                "local_candidate_id": str((local_default or {}).get("candidate_id", "")),
                "remote_candidate_id": str(remote_first.get("candidate_id", "")),
                "local_candidate_type": str((local_default or {}).get("candidate_type", "")),
                "remote_candidate_type": str(remote_first.get("candidate_type", "")),
            },
            "ice": {
                "local_ufrag": str(local_ice.get("ufrag", "")),
                "remote_ufrag": str(remote_ice.get("ufrag", "")),
                "remote_candidate_count": len(remote_candidates),
            },
            "created_unix": int(time.time()),
            "updated_utc": self.utc_now(),
        }
        with self.node._lock:
            self.node._direct_sessions[session_id] = session
        runtime = self._runtimes.get(session_id)
        if runtime is not None and hasattr(connection, "recv") and hasattr(connection, "send"):
            runtime["remote_peer_id"] = remote_peer_id
            listener = runtime.get("listener_task")
            if listener is None or listener.done():
                runtime["listener_task"] = asyncio.create_task(self._data_loop(session_id, remote_peer_id, connection, runtime))
        self._write_direct_sessions_snapshot()
        self.node.record_transport_attestation_background(
            route="direct",
            transport_backend=self.name,
            remote_peer_id=remote_peer_id,
            session_id=session_id,
            proof_scope="connectivity_check",
            selected_candidate_pair=session.get("selected_candidate_pair", {}),
            success=True,
        )
        return dict(session)

    def handle_punch_probe(self, message: Mapping[str, Any], sender: str) -> None:
        return None

    def handle_punch_ack(self, message: Mapping[str, Any]) -> None:
        return None

    async def _prepare_connection(
        self,
        session_id: str,
        ice_controlling: bool,
        local_ice: Mapping[str, Any] | None = None,
    ) -> Any:
        connection = self._connections.get(session_id)
        if connection is not None:
            return connection
        connection = self._make_connection(self._aioice(), ice_controlling, local_ice)
        await connection.gather_candidates()
        self._connections[session_id] = connection
        return connection

    def _make_connection(self, aioice: Any, ice_controlling: bool, local_ice: Mapping[str, Any] | None = None) -> Any:
        local_ice = local_ice if isinstance(local_ice, Mapping) else {}
        return aioice.Connection(
            ice_controlling=ice_controlling,
            components=1,
            stun_server=self._server_tuple(self.node.config.p2p_stun_server),
            turn_server=self._server_tuple(self.node.config.p2p_turn_server),
            turn_username=self.node.config.p2p_turn_username or None,
            turn_password=self.node.config.p2p_turn_password or None,
            turn_transport=self.node.config.p2p_turn_transport or "udp",
            use_ipv4=True,
            use_ipv6=True,
            local_username=str(local_ice.get("ufrag", "")) or None,
            local_password=str(local_ice.get("pwd", "")) or None,
        )

    def _candidate_to_wire(self, candidate: Any, now: int) -> dict[str, Any] | None:
        if candidate is None:
            return None
        host = str(getattr(candidate, "host", "")).strip()
        port = int(getattr(candidate, "port", 0) or 0)
        candidate_type = str(getattr(candidate, "type", "host") or "host").lower()
        base = self.node._make_candidate(candidate_type, host, port, "ice:aioice", int(getattr(candidate, "priority", 0) or 0), now)
        normalized = self.node._normalize_candidate(base, self.node.node_id, now)
        if normalized is None:
            return None
        normalized["ice_sdp"] = str(candidate.to_sdp())
        normalized["ice_foundation"] = str(getattr(candidate, "foundation", ""))
        normalized["ice_component"] = int(getattr(candidate, "component", 1) or 1)
        return normalized

    def _wire_to_candidate(self, aioice: Any, candidate: Any) -> Any:
        if not isinstance(candidate, Mapping):
            return None
        sdp = str(candidate.get("ice_sdp", "")).strip()
        if sdp:
            return aioice.Candidate.from_sdp(sdp)
        foundation = str(candidate.get("ice_foundation") or candidate.get("candidate_id") or "silicium")
        return aioice.Candidate(
            foundation=foundation,
            component=int(candidate.get("ice_component", 1) or 1),
            transport=str(candidate.get("transport", "udp")),
            priority=int(candidate.get("priority", 0) or 0),
            host=str(candidate.get("ip", "")),
            port=int(candidate.get("port", 0) or 0),
            type=str(candidate.get("candidate_type", "host")),
        )

    def _store_failure(self, session_id: str, remote_peer_id: str, reason: str, *, details: str = "") -> dict[str, Any]:
        session = self._direct_failure(session_id, reason, remote_peer_id=remote_peer_id)
        if details:
            session["details"] = details
        with self.node._lock:
            self.node._direct_sessions[session_id] = session
        self._write_direct_sessions_snapshot()
        self.node.record_transport_attestation_background(
            route="failed",
            transport_backend=self.name,
            remote_peer_id=remote_peer_id,
            session_id=session_id,
            proof_scope="connectivity_check",
            success=False,
            failure_reason=reason,
        )
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

    def _is_controlling(self, session: Mapping[str, Any]) -> bool:
        return self.safe_id(str(session.get("initiator_peer_id", ""))) == self.node.node_id

    def _ensure_runtime(self, session_id: str) -> dict[str, Any]:
        runtime = self._runtimes.get(session_id)
        if runtime is not None:
            return runtime
        ready = threading.Event()
        state: dict[str, Any] = {"ready": ready, "response_waiters": {}, "response_buffers": {}}

        def run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            state["loop"] = loop
            ready.set()
            loop.run_forever()
            loop.close()

        thread = threading.Thread(target=run_loop, name=f"ice-{session_id}", daemon=True)
        state["thread"] = thread
        self._runtimes[session_id] = state
        thread.start()
        if not ready.wait(timeout=2):
            self._runtimes.pop(session_id, None)
            raise TimeoutError("ice_event_loop_start_timeout")
        return state

    def _submit(self, runtime: Mapping[str, Any], coroutine: Any) -> Any:
        loop = runtime.get("loop")
        if not isinstance(loop, asyncio.AbstractEventLoop) or loop.is_closed():
            close_coroutine = getattr(coroutine, "close", None)
            if callable(close_coroutine):
                close_coroutine()
            raise RuntimeError("ice_event_loop_unavailable")
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except Exception:
            close_coroutine = getattr(coroutine, "close", None)
            if callable(close_coroutine):
                close_coroutine()
            raise
        timeout_s = max(5.0, float(self.node.config.p2p_session_timeout_ms) / 1000.0 + 5.0)
        try:
            return future.result(timeout=timeout_s)
        except TimeoutError:
            future.cancel()
            raise

    def close(self) -> None:
        for session_id, runtime in list(self._runtimes.items()):
            connection = self._connections.get(session_id)
            if connection is not None:
                try:
                    self._submit(runtime, connection.close())
                except Exception:
                    pass
            loop = runtime.get("loop")
            if isinstance(loop, asyncio.AbstractEventLoop) and not loop.is_closed():
                loop.call_soon_threadsafe(loop.stop)
            thread = runtime.get("thread")
            if isinstance(thread, threading.Thread):
                thread.join(timeout=2)
        self._runtimes.clear()
        self._connections.clear()

    def _server_tuple(self, value: str) -> tuple[str, int] | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        host, sep, port_raw = raw.rpartition(":")
        if not sep:
            return None
        try:
            port = int(port_raw)
        except ValueError:
            return None
        host = host.strip().strip("[]")
        return (host, port) if host and port > 0 else None

    def _redacted_turn_server(self) -> str:
        return self.node.config.p2p_turn_server if self.node.config.p2p_turn_server else ""

    def _aioice(self) -> Any:
        return importlib.import_module("aioice")
