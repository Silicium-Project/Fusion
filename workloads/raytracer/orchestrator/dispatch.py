"""Submission of compute/verify tasks to the scheduler.

Without a local emitter the task is queued in the shared export directory
(a colocated persistent scheduler picks it up). With an emitter it goes, in
order of preference, through the local protobuf/ZeroMQ RPC sidecar or the
signed HTTP dispatch of the seed peers.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from networked.networked_runtime import (
    LocalNetworkEmitter,
    attach_network_content_blobs,
    dispatch_task_to_scheduler,
)
from workloads.common import submit_task


def submit_network_task(
    args: argparse.Namespace,
    export_dir: Path,
    payload: dict[str, Any],
    emitter_node: LocalNetworkEmitter | None,
) -> dict[str, Any]:
    """Queue locally for a shared scheduler, otherwise dispatch to the seed."""
    payload = attach_network_content_blobs(export_dir, payload)
    emitter_node_id = str(getattr(args, "network_node_id", "") or "").strip()
    if emitter_node_id:
        payload.setdefault("emitter_node_id", emitter_node_id)
        payload.setdefault("origin_node_id", emitter_node_id)
    task_id = str(payload.get("task_id", ""))
    required_roles = payload.get("required_roles", [])
    if emitter_node is None:
        return _queue_locally(export_dir, payload)

    # Optional local protobuf/ZeroMQ control plane. It avoids an HTTP round
    # trip when a scheduler gateway is colocated with the node, while retaining
    # the signed HTTP path as a transparent fallback for older releases.
    rpc_endpoint = str(os.environ.get("SILICIUM_RPC_ENDPOINT", "")).strip()
    rpc_fallback_error = ""
    if rpc_endpoint:
        try:
            return _dispatch_over_rpc(args, rpc_endpoint, payload, task_id, required_roles)
        except Exception as error:
            # A rolling upgrade must not strand work when the sidecar is absent.
            rpc_fallback_error = f"{type(error).__name__}:{error}"

    return _dispatch_over_http(args, export_dir, payload, task_id, required_roles, rpc_fallback_error)


def _queue_locally(export_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Write the task into the export directory for a colocated scheduler."""
    submission = submit_task(export_dir, payload)
    submission["scheduler_dispatch"] = {
        "status": "queued_local",
        "target": str(export_dir),
    }
    submission["queue"] = "scheduler://local-export"
    return submission


def _dispatch_over_rpc(
    args: argparse.Namespace,
    rpc_endpoint: str,
    payload: dict[str, Any],
    task_id: str,
    required_roles: Any,
) -> dict[str, Any]:
    """Dispatch through the RPC sidecar; any exception makes the caller fall back to HTTP."""
    # Imported lazily: the RPC client pulls in ZeroMQ, which is optional.
    from tools.rpc_client import RpcClient
    # The experiment API already uses the MCP bearer for the same
    # authenticated control plane.  Reuse it when a dedicated RPC
    # token is not configured; otherwise an in-container renderer
    # silently falls back to the legacy HTTP dispatcher.
    rpc_token = os.environ.get("SILICIUM_RPC_TOKEN", "") or os.environ.get("SILICIUM_MCP_TOKEN", "")
    rpc_result = RpcClient(rpc_endpoint, rpc_token, timeout_ms=3000).call("task.dispatch", payload)
    return {
        "task_id": task_id,
        "required_roles": required_roles,
        "priority": args.priority,
        "status": str(rpc_result.get("status", "dispatched")),
        "queue": "rpc://task.dispatch",
        "scheduler_dispatch": {"status": "dispatched", "target": rpc_endpoint, "transport": "protobuf+zeromq"},
    }


def _dispatch_over_http(
    args: argparse.Namespace,
    export_dir: Path,
    payload: dict[str, Any],
    task_id: str,
    required_roles: Any,
    rpc_fallback_error: str,
) -> dict[str, Any]:
    """Signed HTTP dispatch to the seed peers' scheduler."""
    scheduler_dispatch = dispatch_task_to_scheduler(
        payload,
        args.network_seed_peers,
        args.network_mesh_key,
        export_dir=export_dir,
        node_id=args.network_node_id,
    )
    if rpc_fallback_error:
        scheduler_dispatch = {**scheduler_dispatch, "rpc_fallback_error": rpc_fallback_error}
    return {
        "task_id": task_id,
        "required_roles": required_roles,
        "priority": args.priority,
        "status": scheduler_dispatch["status"],
        "queue": "scheduler://tasks/dispatch",
        "scheduler_dispatch": scheduler_dispatch,
    }


def ensure_submission_success(submission: dict[str, Any]) -> None:
    """Raise RuntimeError (`scheduler_dispatch_failed:<json>`) unless the task was queued or dispatched."""
    status = str(submission.get("status", ""))
    if status in {"queued", "dispatched"}:
        return
    dispatch = submission.get("scheduler_dispatch", {})
    raise RuntimeError(
        "scheduler_dispatch_failed:"
        + json.dumps(dispatch, sort_keys=True, separators=(",", ":"))
    )
