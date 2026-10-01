"""Mesh routes: inbound signed messages (/mesh) and local gossip publication."""

from __future__ import annotations

import json
from typing import Any

from tools.node.peer.http.common import OK_BODY, read_json_object, send_json


def post_mesh(handler: Any, peer: Any, raw: bytes) -> None:
    """Hand a signed mesh message (announce, gossip event...) to the peer layer."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    peer._handle_network_message(payload, handler.client_address[0])
    handler.send_body(200, OK_BODY)


def post_gossip_publish(handler: Any, peer: Any, raw: bytes) -> None:
    """Publish an allowed topic (software_update, task_control, node_probe)."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        handler.send_error(400)
        return
    topic = str(payload.get("topic", "")).strip() if isinstance(payload, dict) else ""
    event_payload = payload.get("payload") if isinstance(payload, dict) else None
    valid_software_update = (
        topic == "software_update"
        and peer._normalize_update_announcement(event_payload) is not None
    )
    valid_task_control = (
        topic == "task_control"
        and peer.node is not None
        and peer.node.validate_task_control(event_payload, signed_by=peer.node_id)
    )
    valid_node_probe = (
        topic == "node_probe"
        and isinstance(event_payload, dict)
        and bool(str(event_payload.get("probe_id", "")).strip())
    )
    if not valid_software_update and not valid_task_control and not valid_node_probe:
        handler.send_error(400)
        return
    if valid_software_update:
        peer._record_update_announcement(event_payload, peer.node_id)
    elif valid_task_control:
        peer.node.apply_task_control(event_payload, signed_by=peer.node_id)
    # The announcement is durable locally before this call. Fan-out may
    # encounter slow/offline peers and must not hold the HTTP response.
    peer.publish(topic, event_payload, background=True)
    send_json(handler, 202, {"ok": True, "topic": topic})
