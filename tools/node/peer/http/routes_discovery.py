"""Discovery routes: rendezvous snapshot/observe and peer/candidate registration."""

from __future__ import annotations

import time
from typing import Any

from tools.node.peer.http.common import OK_BODY, read_json_object, send_json
from tools.node.util import read_json, safe_id


def get_snapshot(handler: Any, peer: Any) -> None:
    """Signed read of the persisted discovery registry (live table as fallback)."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    send_json(handler, 200, read_json(peer.discovery_registry_path, peer.peers_snapshot(persist=False)))


def get_observe(handler: Any, peer: Any) -> None:
    """Echo the caller's public address (server-reflexive candidate discovery)."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    send_json(
        handler,
        200,
        {
            "schema_version": 1,
            "node_id": peer.node_id,
            "observed_ip": str(handler.client_address[0]),
            "observed_port": int(handler.client_address[1]),
            "timestamp_unix": int(time.time()),
        },
    )


def post_register(handler: Any, peer: Any, raw: bytes) -> None:
    """Record a peer profile pushed by a node registering with this rendezvous."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    peer._record_peer(payload)
    handler.send_body(200, OK_BODY)


def _requester_mismatch(handler: Any, claimed_peer_id: str) -> bool:
    """Answer 403 when the body's peer id differs from the signed header id."""
    requester_node_id = safe_id(str(handler.headers.get("X-Silicium-Node-Id", "")))
    if claimed_peer_id == requester_node_id:
        return False
    send_json(handler, 403, {"ok": False, "error": "requester_mismatch"})
    return True


def post_peer_register(handler: Any, peer: Any, raw: bytes) -> None:
    """Register the signed caller itself (body ``node_id`` must match)."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    requester_node_id = safe_id(str(handler.headers.get("X-Silicium-Node-Id", "")))
    if _requester_mismatch(handler, safe_id(str(payload.get("node_id", "")))):
        return
    peer._record_peer(payload)
    send_json(handler, 200, {"ok": True, "peer_id": requester_node_id})


def post_candidates(handler: Any, peer: Any, raw: bytes) -> None:
    """Merge the signed caller's own connectivity candidates."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    requester_node_id = safe_id(str(handler.headers.get("X-Silicium-Node-Id", "")))
    if _requester_mismatch(handler, safe_id(str(payload.get("peer_id", payload.get("node_id", ""))))):
        return
    peer._record_candidate_announce(payload)
    candidates = peer._normalize_candidate_list(payload.get("candidates", []), requester_node_id)
    send_json(handler, 200, {"ok": True, "peer_id": requester_node_id, "candidate_count": len(candidates)})
