"""GET routes for liveness and mesh history: /health, /peers, /events/*."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from tools.node.peer.http.common import send_json
from tools.node.util import utc_now


def get_health(handler: Any, peer: Any) -> None:
    """Unauthenticated liveness probe (``service`` is read by other repos)."""
    send_json(
        handler,
        200,
        {
            "ok": True,
            "status": "ok",
            "service": "network_node",
            "node_id": peer.node_id,
            "release_channel": peer.config.release_channel,
            "release_build": peer.config.release_build,
            "updated_utc": utc_now(),
        },
    )


def get_peers(handler: Any, peer: Any) -> None:
    """Signed peer-table read used by anti-entropy sync."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    send_json(handler, 200, peer.peers_snapshot(persist=False))


def get_recent_events(handler: Any, peer: Any) -> None:
    """Signed read of the latest gossip events (``?limit=``)."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    query = parse_qs(urlparse(handler.path).query)
    try:
        limit = int((query.get("limit") or [str(peer.config.peer_event_limit)])[0])
    except ValueError:
        limit = peer.config.peer_event_limit
    send_json(handler, 200, {"schema_version": 1, "node_id": peer.node_id, "events": peer.recent_events(limit)})


def get_task_controls(handler: Any, peer: Any) -> None:
    """Signed read of durable task-control events (limit clamped to 1..4096)."""
    if not handler.signed_by_peer():
        handler.send_error(403)
        return
    query = parse_qs(urlparse(handler.path).query)
    try:
        limit = int((query.get("limit") or ["2048"])[0])
    except ValueError:
        limit = 2048
    send_json(
        handler,
        200,
        {
            "schema_version": 1,
            "node_id": peer.node_id,
            "events": peer.recent_task_control_events(min(max(1, limit), 4096)),
        },
    )
