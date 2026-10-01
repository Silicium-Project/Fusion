"""Relay routes (only with --relay-enable): content fetch, mesh forward, UDP punch."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from tools.node.peer.http.common import OK_BODY, read_json_object, send_json
from tools.node.util import utc_now


def get_fetch(handler: Any, peer: Any) -> None:
    """Fetch ``content_id`` from ``peer_id`` on behalf of a peer that cannot reach it."""
    if not peer.config.relay_enable or not handler.signed_by_peer():
        handler.send_error(403)
        return
    query = parse_qs(urlparse(handler.path).query)
    peer_id = str((query.get("peer_id") or [""])[0]).strip()
    content_id = str((query.get("content_id") or [""])[0]).strip()
    if not peer_id or not content_id:
        handler.send_error(400)
        return
    data = _fetch_from_target(peer, peer_id, content_id)
    if data is None:
        handler.send_error(404)
        return
    handler.send_body(200, data, content_type="application/octet-stream")


def _fetch_from_target(peer: Any, peer_id: str, content_id: str) -> bytes | None:
    """Try the target three times, re-syncing the peer table between attempts."""
    target_peer = peer._peers.get(peer_id)
    if not isinstance(target_peer, dict):
        target_peer = {}
    data = None
    for attempt in range(3):
        data = peer._fetch_direct_from_peer(target_peer, content_id)
        if data is not None:
            break
        try:
            peer.sync_once()
        except Exception:
            pass
        target_peer = peer._peers.get(peer_id, {})
        if attempt < 2:
            time.sleep(0.05)
    return data


def post_mesh(handler: Any, peer: Any, raw: bytes) -> None:
    """Forward a mesh message to a known peer's HTTP endpoint."""
    if not peer.config.relay_enable:
        handler.send_error(403)
        return
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    target_peer_id = str(payload.get("peer_id", "")).strip()
    message = payload.get("message")
    target_peer = peer._peers.get(target_peer_id)
    if not target_peer_id or not isinstance(message, dict) or not isinstance(target_peer, dict):
        handler.send_error(400)
        return
    peer._send_http(str(target_peer.get("http_base_url", "")).rstrip("/"), message)
    handler.send_body(200, OK_BODY)


def _punch_probe(peer: Any, session_id: str, requester_handshake: Any, target_host: str, target_port: int) -> dict[str, Any]:
    """Signed ``punch_probe`` telling the receiver which address to punch."""
    probe = {
        "message_type": "punch_probe",
        "session_id": session_id,
        "node_id": peer.node_id,
        "identity_id": peer.identity.identity_id,
        "public_key": peer.identity.public_key_b64,
        "requester_handshake": requester_handshake,
        "target_host": target_host,
        "target_port": target_port,
        "timestamp_utc": utc_now(),
    }
    peer._sign_message(probe)
    return probe


def post_punch(handler: Any, peer: Any, raw: bytes) -> None:
    """Coordinate a UDP hole punch between the signed requester and a target."""
    if not peer.config.relay_enable:
        handler.send_error(403)
        return
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    target_peer_id = str(payload.get("target_peer_id", "")).strip()
    session_id = str(payload.get("session_id", "")).strip()
    requester_handshake = payload.get("handshake")
    requester_node_id = str(handler.headers.get("X-Silicium-Node-Id", "")).strip()
    ok, reason = peer.verify_session_handshake(
        requester_handshake if isinstance(requester_handshake, dict) else None,
        expected_peer_id=requester_node_id,
        expected_target_peer_id=target_peer_id,
    )
    if not ok:
        send_json(handler, 403, {"ok": False, "error": reason})
        return
    requester_peer = peer._peers.get(str(handler.headers.get("X-Silicium-Node-Id", "")).strip(), {})
    target_peer = peer._peers.get(target_peer_id, {})
    if not isinstance(requester_peer, dict) or not isinstance(target_peer, dict):
        handler.send_error(404)
        return
    requester_host = str(requester_peer.get("gossip_bind", "")).strip()
    requester_port = int(requester_peer.get("gossip_port", 0) or 0)
    target_host = str(target_peer.get("gossip_bind", "")).strip()
    target_port = int(target_peer.get("gossip_port", 0) or 0)
    if requester_host and requester_port > 0 and target_host and target_port > 0:
        probe_to_target = _punch_probe(peer, session_id, requester_handshake, requester_host, requester_port)
        peer._send_udp(f"{target_host}:{target_port}", target_host, target_port, probe_to_target)
        probe_to_requester = _punch_probe(peer, session_id, requester_handshake, target_host, target_port)
        peer._send_udp(f"{requester_host}:{requester_port}", requester_host, requester_port, probe_to_requester)
    handler.send_body(200, OK_BODY)
