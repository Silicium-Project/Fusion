"""Task routes: pull-based claims and push dispatch of tasks, requests, results."""

from __future__ import annotations

from typing import Any

from tools.node.envelopes import enqueue_request_envelope, enqueue_task_envelope, ingest_content_blobs
from tools.node.peer.http.common import OK_BODY, read_json_object, send_json
from tools.node.util import append_jsonl, normalize_release_channel, safe_id, utc_now
from tools.node_defaults import split_csv


def _claim_channel_mismatch(handler: Any, peer: Any, payload: dict[str, Any]) -> bool:
    """Answer 409 when a worker of another release channel asks for work."""
    raw_channel = str(payload.get("release_channel", "") or "").strip()
    requested_channel = normalize_release_channel(raw_channel)
    if not raw_channel or requested_channel == peer.config.release_channel:
        return False
    send_json(
        handler,
        409,
        {
            "ok": False,
            "error": "release_channel_mismatch",
            "expected_release_channel": peer.config.release_channel,
        },
    )
    return True


def _claim_roles(payload: dict[str, Any]) -> set[str]:
    roles = payload.get("roles", [])
    if isinstance(roles, str):
        roles = split_csv(roles)
    return {str(r).lower() for r in roles if str(r).strip()}


def _record_claiming_worker(handler: Any, peer: Any, requester_node_id: str, roles_set: set[str], payload: dict[str, Any]) -> None:
    """Refresh the worker's liveness/profile from its claim request."""
    peer._record_peer(
        {
            "node_id": requester_node_id,
            "identity_id": str(handler.headers.get("X-Silicium-Identity-Id", "")),
            "public_key": str(handler.headers.get("X-Silicium-Public-Key", "")),
            "roles": sorted(roles_set),
            "features": payload.get("features", []),
            "transport_attestations": payload.get("transport_attestations", []),
            "http_base_url": payload.get("http_base_url", ""),
            "mesh_post_url": payload.get("mesh_post_url", ""),
            "gossip_bind": payload.get("gossip_bind", ""),
            "gossip_port": payload.get("gossip_port", 0),
            "candidates": payload.get("candidates", []),
            "relay_capable": payload.get("relay_capable", False),
            "capacity": payload.get("capacity", {}),
            "reputation_score": payload.get("reputation_score", 0.0),
            "resource_reputation": payload.get("resource_reputation", {}),
            "app_version": payload.get("app_version", ""),
            "release_channel": payload.get("release_channel", ""),
            "release_build": payload.get("release_build", ""),
            "timestamp_utc": utc_now(),
        },
        # Claims are a hot path. Keep liveness in memory
        # immediately and let heartbeat/anti-entropy write
        # the durable peer snapshot at a bounded cadence.
        persist_snapshot=False,
    )


def _requested_batch(payload: dict[str, Any]) -> int:
    requested_batch = payload.get("max_tasks", 1)
    try:
        requested_batch = int(requested_batch)
    except (TypeError, ValueError):
        requested_batch = 1
    return max(1, min(32, requested_batch))


def _log_claim_request(
    peer: Any,
    requester_node_id: str,
    roles_set: set[str],
    payload: dict[str, Any],
    claimed_envelopes: list[dict[str, Any]],
) -> None:
    claimed_envelope = claimed_envelopes[0] if claimed_envelopes else None
    append_jsonl(
        peer.node.events_path,
        {
            "schema_version": 1,
            "timestamp_utc": utc_now(),
            "node_id": peer.node.config.node_id,
            "kind": "claim_request",
            "worker_id": requester_node_id,
            "roles": sorted(roles_set),
            "app_version": str(payload.get("app_version", "")),
            "release_channel": str(payload.get("release_channel", "")),
            "release_build": str(payload.get("release_build", "")),
            "claimed": bool(claimed_envelopes),
            "claimed_count": len(claimed_envelopes),
            "item_id": safe_id(str((claimed_envelope or {}).get("request_id") or (claimed_envelope or {}).get("task_id") or "")),
            "item_ids": [
                safe_id(str(item.get("request_id") or item.get("task_id") or ""))
                for item in claimed_envelopes
            ],
        },
    )


def post_claim(handler: Any, peer: Any, raw: bytes) -> None:
    """Reserve up to ``max_tasks`` (1..32) compatible tasks for the calling worker."""
    payload = read_json_object(handler, raw, allow_empty=True)
    if payload is None:
        return
    if _claim_channel_mismatch(handler, peer, payload):
        return
    requester_node_id = safe_id(str(payload.get("node_id", "") or handler.headers.get("X-Silicium-Node-Id", "")))
    roles_set = _claim_roles(payload)
    if requester_node_id:
        _record_claiming_worker(handler, peer, requester_node_id, roles_set, payload)
    requested_batch = _requested_batch(payload)
    claimed_envelopes = (
        peer.node.claim_tasks_for_worker(
            requester_node_id,
            roles_set,
            limit=requested_batch,
        )
        if peer.node
        else []
    )
    claimed_envelope = claimed_envelopes[0] if claimed_envelopes else None
    if peer.node:
        _log_claim_request(peer, requester_node_id, roles_set, payload, claimed_envelopes)
    send_json(
        handler,
        200,
        {
            "ok": True,
            # Keep `task` for older workers; new workers use
            # `tasks` to amortise authenticated HTTP claims.
            "task": claimed_envelope,
            "tasks": claimed_envelopes,
            "claimed_count": len(claimed_envelopes),
        },
    )


def post_task_dispatch(handler: Any, peer: Any, raw: bytes) -> None:
    """Accept a task pushed by a scheduler into the local queues (202)."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    # Keep the immutable source emitter alongside the
    # hop-by-hop dispatched_by field. The signed peer header
    # is available at ingress; downstream schedulers preserve
    # this value while they update their routing metadata.
    emitter_node_id = safe_id(str(handler.headers.get("X-Silicium-Node-Id", "")).strip())
    if emitter_node_id:
        payload.setdefault("emitter_node_id", emitter_node_id)
        payload.setdefault("origin_node_id", emitter_node_id)
    ingest_content_blobs(peer.export_dir, payload)
    enqueue_task_envelope(peer.export_dir, payload)
    handler.send_body(202, OK_BODY)


def post_request_dispatch(handler: Any, peer: Any, raw: bytes) -> None:
    """Accept a request pushed by a scheduler into the local queues (202)."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    ingest_content_blobs(peer.export_dir, payload)
    enqueue_request_envelope(peer.export_dir, payload)
    handler.send_body(202, OK_BODY)


def post_result_dispatch(handler: Any, peer: Any, raw: bytes) -> None:
    """Ingest a result returned by the worker a task was dispatched to (202)."""
    payload = read_json_object(handler, raw)
    if payload is None:
        return
    try:
        peer.node.ingest_dispatched_result(payload)
    except Exception:
        handler.send_error(400)
        return
    handler.send_body(202, OK_BODY)
