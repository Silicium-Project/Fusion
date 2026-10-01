"""P2P routes: signaling sessions, transport diagnostics and content blobs."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from tools.node.peer.http.common import read_json_object, send_json
from tools.node.util import safe_id, sha256_bytes

# Session states that no longer need the peer's attention.
_SETTLED_SESSION_STATUSES = {"closed", "failed", "expired", "direct", "relay", "completed"}


def get_sessions(handler: Any, peer: Any) -> None:
    """Signed read of every live signaling session."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    send_json(handler, 200, peer.sessions_snapshot())


def get_pending_sessions(handler: Any, peer: Any) -> None:
    """Signed read of the unsettled sessions involving the calling peer."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    requester_node_id = safe_id(str(handler.headers.get("X-Silicium-Node-Id", "")))
    now = int(time.time())
    with peer._lock:
        sessions = [
            peer._session_response(session)
            for session in peer._sessions.values()
            if requester_node_id
            in {
                safe_id(str(session.get("initiator_peer_id", ""))),
                safe_id(str(session.get("target_peer_id", ""))),
            }
            and int(session.get("expires_unix", 0) or 0) > now
            and str(session.get("status", "")) not in _SETTLED_SESSION_STATUSES
        ]
    send_json(handler, 200, {"ok": True, "sessions": sessions})


def get_transport(handler: Any, peer: Any) -> None:
    """Signed read of the direct transport backend diagnostics."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    send_json(handler, 200, peer.direct_transport_snapshot())


def get_attestations(handler: Any, peer: Any) -> None:
    """Signed read of this node's transport attestations."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    send_json(handler, 200, peer.transport_attestations_snapshot(), cache_control="no-store")


def get_content(handler: Any, peer: Any) -> None:
    """Signed download of a content blob from the local ``p2p/`` store."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    # Kept as-is: the id is not validated, so an encoded "../" can escape
    # the p2p/ store (path traversal risk, to fix separately).
    content_id = unquote(handler.path[len("/p2p/") :]).strip()
    target = peer.export_dir / "p2p" / content_id
    if not target.exists():
        handler.send_error(404)
        return
    handler.send_body(200, target.read_bytes(), content_type="application/octet-stream")


def post_session_request(handler: Any, peer: Any, raw: bytes) -> None:
    """Create a signaling session; auto-ready it when this node is the target."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    status, body_payload = peer.create_signaling_session(payload, str(handler.headers.get("X-Silicium-Node-Id", "")))
    session = body_payload.get("session") if isinstance(body_payload.get("session"), dict) else {}
    if status == 201 and str(session.get("target_peer_id", "")) == peer.node_id:
        local_ready = peer.build_session_ready_payload(session)
        ready_status, ready_body = peer.mark_session_ready(str(session.get("session_id", "")), peer.node_id, local_ready)
        if ready_status == 200:
            body_payload = ready_body
            punch_start = ready_body.get("punch_start") if isinstance(ready_body.get("punch_start"), dict) else {}
            peer._start_direct_session_background(punch_start)
    send_json(handler, status, body_payload)


def post_session_action(handler: Any, peer: Any, raw: bytes) -> None:
    """``/p2p/sessions/<id>/<ready|result|close>`` for a session participant."""
    parts = [part for part in urlparse(handler.path).path.split("/") if part]
    if len(parts) != 4 or parts[0] != "p2p" or parts[1] != "sessions":
        handler.send_error(404)
        return
    session_id = parts[2]
    action = parts[3]
    payload = read_json_object(handler, raw, allow_empty=True)
    if payload is None:
        return
    requester_node_id = str(handler.headers.get("X-Silicium-Node-Id", ""))
    if action == "ready":
        status, body_payload = peer.mark_session_ready(session_id, requester_node_id, payload)
        ready_session = body_payload.get("session") if isinstance(body_payload.get("session"), dict) else {}
        if status == 200 and str(ready_session.get("status", "")) == "punching" and str(ready_session.get("target_peer_id", "")) == peer.node_id:
            peer._start_direct_session_background(body_payload.get("punch_start", {}))
    elif action == "result":
        status, body_payload = peer.record_session_result(session_id, payload, requester_node_id)
    elif action == "close":
        status, body_payload = peer.close_session(session_id, payload, requester_node_id)
    else:
        handler.send_error(404)
        return
    send_json(handler, status, body_payload)


def post_ingest(handler: Any, peer: Any, raw: bytes) -> None:
    """Store a replica pushed by a peer and announce its availability."""
    query = parse_qs(urlparse(handler.path).query)
    # Kept as-is: the id from the query is neither validated nor checked
    # against the body hash (path traversal / poisoning risk, to fix separately).
    content_id = str((query.get("content_id") or [""])[0]).strip() or sha256_bytes(raw)
    target = peer.export_dir / "p2p" / content_id
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(raw)
    peer.publish("content_available", {"content_id": content_id, "hash": "sha256:" + sha256_bytes(raw), "size_bytes": len(raw)})
    send_json(handler, 200, {"ok": True, "content_id": content_id})
