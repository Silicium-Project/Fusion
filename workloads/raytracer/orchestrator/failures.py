"""Classification of failed worker results.

Turns a worker result into a readable error detail, decides whether a failure
is transient (worth a new attempt) and enforces the raytracer compute result
contract.
"""
from __future__ import annotations

from typing import Any


def task_failure_details(result: dict[str, Any]) -> tuple[str, str]:
    """Return `(detail, node_id)` for a failed result: error, type and worker traceback."""
    error = str(result.get("error") or result.get("last_error") or "unknown_error").strip()
    error_type = str(result.get("error_type") or "").strip()
    traceback_text = str(result.get("traceback") or result.get("error_traceback") or "").strip()
    detail = error or "unknown_error"
    if error_type and error_type not in detail:
        detail = f"{error_type}: {detail}"
    if traceback_text and traceback_text not in detail:
        detail = f"{detail}\n\nTraceback worker:\n{traceback_text}"
    node_id = str(result.get("node_id") or "")
    return detail, node_id


def is_transient_task_failure(error: str) -> bool:
    """True when the error looks like a network/content hiccup rather than a bad result."""
    normalized = str(error).lower()
    return any(
        marker in normalized
        for marker in (
            "peer_content_not_found:",
            "unknown_peer_for_content:",
            "content_not_found",
            "missing network result after deadline:",
            "timed out",
            "timeout",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
        )
    )


def ensure_task_success(result: dict[str, Any], task_id: str) -> None:
    """Raise RuntimeError when the worker reported `success: false`."""
    if result.get("success", True) is not False:
        return
    error, node_id = task_failure_details(result)
    raise RuntimeError(f"task failed: {task_id} on {node_id}\n{error}")


def ensure_raytracer_compute_contract(result: dict[str, Any], task_id: str) -> None:
    """Reject a result that did not actually run the raytracer fragment renderer."""
    compute = result.get("compute")
    mode = str(compute.get("mode", "")) if isinstance(compute, dict) else ""
    executed = bool(compute.get("executed", False)) if isinstance(compute, dict) else False
    milestones = result.get("verification_milestones")
    if mode != "raytracer-fragment" or not executed or not isinstance(milestones, dict):
        node_id = str(result.get("node_id") or "")
        raise RuntimeError(
            "raytracer_compute_contract_invalid:"
            f"task={task_id}:node={node_id}:mode={mode or 'missing'}:executed={str(executed).lower()}"
        )
