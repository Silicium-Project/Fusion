"""Descriptors advertised to MCP clients (``tools/list`` and ``resources/list``).

``tool_descriptors`` returns the MCP tool definitions with their JSON input
schemas; ``RESOURCE_TEMPLATES`` lists the parameterised resource URIs that
``resources/list`` exposes as discoverable patterns.
"""

from __future__ import annotations

from typing import Any

from .constants import (
    NETWORK_ROLES,
    PRIORITIES,
    REQUEST_KINDS,
    RUNNER_MODES,
    TOOL_GET_HEALTH,
    TOOL_GET_REQUEST,
    TOOL_GET_TASK,
    TOOL_INTERRUPT_ACTION,
    TOOL_RUN_ACTION,
    TOOL_SELECT_RUNNER_MODE,
    TOOL_SUBMIT_REQUEST,
    TOOL_SUBMIT_TASK,
)

# (template URI, display name), in the order they are advertised.
RESOURCE_TEMPLATES = (
    ("resources://silicium/results/by-task/{task_id}", "result_by_task"),
    ("resources://silicium/logs/by-task/{task_id}", "logs_by_task"),
    ("resources://silicium/tasks/by-id/{task_id}", "task_by_id"),
    ("resources://silicium/requests/by-id/{request_id}", "request_by_id"),
    ("resources://silicium/nodes/heartbeat/{node_id}", "node_heartbeat"),
    ("resources://silicium/nodes/metrics/{node_id}", "node_metrics"),
    ("resources://silicium/nodes/peers/{node_id}", "node_peers"),
)

_NO_ARGS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _object_schema(
    properties: dict[str, Any], *, required: list[str] | None = None, additional: bool
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    schema["additionalProperties"] = additional
    return schema


def tool_descriptors() -> list[dict[str, Any]]:
    """Return every MCP tool descriptor, in advertising order (fresh copies)."""
    return [
        {
            "name": TOOL_GET_HEALTH,
            "description": "Return status.current.json from the worker export directory.",
            "inputSchema": dict(_NO_ARGS_SCHEMA, properties={}),
        },
        {
            "name": TOOL_RUN_ACTION,
            "description": "Run a guarded read-only action (exported snapshots).",
            "inputSchema": _object_schema(
                {"action": {"type": "string"}, "task_id": {"type": "string"}},
                additional=True,
            ),
        },
        {
            "name": TOOL_INTERRUPT_ACTION,
            "description": "Request an interrupt via control.request.json (if enabled).",
            "inputSchema": dict(_NO_ARGS_SCHEMA, properties={}),
        },
        {
            "name": TOOL_SELECT_RUNNER_MODE,
            "description": "Request a runner mode selection via control.request.json (if enabled).",
            "inputSchema": _object_schema(
                {"mode": {"type": "string", "enum": list(RUNNER_MODES)}},
                required=["mode"],
                additional=False,
            ),
        },
        {
            "name": TOOL_SUBMIT_TASK,
            "description": "Submit a task into the Silicium network ingress queue.",
            "inputSchema": _object_schema(
                {"task_id": {"type": "string"}, "task": {"type": "object"}},
                required=["task"],
                additional=True,
            ),
        },
        {
            "name": TOOL_GET_TASK,
            "description": "Read a submitted task envelope by task_id.",
            "inputSchema": _object_schema(
                {"task_id": {"type": "string"}}, required=["task_id"], additional=False
            ),
        },
        {
            "name": TOOL_SUBMIT_REQUEST,
            "description": "Submit a high-priority post-job request such as audit, resource retrieval, or challenge.",
            "inputSchema": _object_schema(
                {
                    "request_id": {"type": "string"},
                    "kind": {"type": "string", "enum": sorted(REQUEST_KINDS)},
                    "target_roles": {"type": "array", "items": {"type": "string", "enum": sorted(NETWORK_ROLES)}},
                    "priority": {"type": "string", "enum": sorted(PRIORITIES)},
                    "p2p_ref": {"type": "object"},
                    "request": {"type": "object"},
                },
                required=["kind"],
                additional=True,
            ),
        },
        {
            "name": TOOL_GET_REQUEST,
            "description": "Read a submitted network request envelope by request_id.",
            "inputSchema": _object_schema(
                {"request_id": {"type": "string"}}, required=["request_id"], additional=False
            ),
        },
    ]
