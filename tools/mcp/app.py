"""Application state of one server instance and the tool executor.

``McpHttpApp`` wires the stores, the access policy, the bearer token and the
observability bundle together; the HTTP handler reaches it through
``server.app``. ``execute_tool`` is shared by ``POST /tools`` and the MCP
``tools/call`` method.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .access_policy import McpAccessPolicy
from .constants import (
    RESOURCE_REPORTS_RECENT,
    RESOURCE_REQUEST_PREFIX,
    RESOURCE_RESULT_PREFIX,
    RESOURCE_STATUS_CURRENT,
    RESOURCE_TASK_PREFIX,
    RUNNER_MODES,
    SUPPORTED_RESOURCES,
    SUPPORTED_TOOLS,
    TOOL_GET_HEALTH,
    TOOL_GET_REQUEST,
    TOOL_GET_TASK,
    TOOL_INTERRUPT_ACTION,
    TOOL_RUN_ACTION,
    TOOL_SELECT_RUNNER_MODE,
    TOOL_SUBMIT_REQUEST,
    TOOL_SUBMIT_TASK,
)
from .control_plane import McpControlPlane
from .export_store import McpExportStore
from .observability import McpObservability
from .request_store import McpRequestStore
from .snapshot_store import McpSnapshotStore
from .task_store import McpTaskStore


def _require_args_object(args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ValueError("args_not_object")
    return args


def _require_text(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing_{key}")
    return value


class McpHttpApp:
    """Shared state of the HTTP server: stores, policy, token, observability."""

    def __init__(
        self,
        export_dir: Path,
        enable_tools: bool,
        token: str | None,
        obs: McpObservability,
        snapshot_store: McpSnapshotStore | None = None,
        access_policy: McpAccessPolicy | None = None,
    ) -> None:
        self.snapshot_store = snapshot_store
        self.store = McpExportStore(export_dir, snapshot_store=snapshot_store)
        self.control = McpControlPlane(export_dir)
        self.task_store = McpTaskStore(export_dir)
        self.request_store = McpRequestStore(export_dir)
        self.enable_tools = enable_tools
        self.token = token or ""
        self.obs = obs
        self.access_policy = access_policy or McpAccessPolicy()

    def rotate_token(self, new_token: str | None = None) -> str:
        """Replace the bearer token (random when empty) and return it."""
        # Historical: reuses the metrics lock as a generic mutex.
        with self.obs.metrics._lock:
            token = (new_token or "").strip() or uuid.uuid4().hex
            self.token = token
            return token

    def list_tools(self) -> list[str]:
        """Tool names allowed by the access policy."""
        return self.access_policy.filter_tools(list(SUPPORTED_TOOLS))

    def list_resources(self) -> list[str]:
        """Resource URIs (and templates) allowed by the access policy."""
        return self.access_policy.filter_resources(list(SUPPORTED_RESOURCES))

    def read_resource(self, uri: str) -> str:
        """Read a resource after the access check (``PermissionError`` if denied)."""
        if not self.access_policy.resource_allowed(uri):
            raise PermissionError("resource_denied")
        return self.store.read_resource(uri)

    def execute_tool(self, name: str, args: Any) -> Any:
        """Run tool ``name``; returns a JSON string (resources) or a dict.

        Read-only tools work without ``--enable-tools``; every other tool name
        (including unknown ones) raises ``PermissionError("tools_disabled")``
        when tools are disabled.
        """
        if not self.access_policy.tool_allowed(name):
            raise PermissionError("tool_denied")
        if name == TOOL_GET_HEALTH:
            return self.read_resource(RESOURCE_STATUS_CURRENT)
        if name == TOOL_GET_TASK:
            return self._read_task_checked(_require_args_object(args))
        if name == TOOL_GET_REQUEST:
            return self._read_request_checked(_require_args_object(args))

        if not self.enable_tools:
            raise PermissionError("tools_disabled")

        if name == TOOL_SUBMIT_TASK:
            return self.task_store.submit(args)
        if name == TOOL_SUBMIT_REQUEST:
            return self.request_store.submit(args)
        if name == TOOL_RUN_ACTION:
            return self._run_action(_require_args_object(args))
        if name == TOOL_INTERRUPT_ACTION:
            self.control.request_interrupt()
            return {"status": "accepted", "message": "interrupt request registered"}
        if name == TOOL_SELECT_RUNNER_MODE:
            return self._select_runner_mode(_require_args_object(args))
        raise ValueError("unsupported_tool")

    def _read_task_checked(self, args: dict[str, Any]) -> str:
        task_id = _require_text(args, "task_id")
        if not self.access_policy.resource_allowed(RESOURCE_TASK_PREFIX + task_id):
            raise PermissionError("resource_denied")
        return self.task_store.read(task_id)

    def _read_request_checked(self, args: dict[str, Any]) -> str:
        request_id = _require_text(args, "request_id")
        if not self.access_policy.resource_allowed(RESOURCE_REQUEST_PREFIX + request_id):
            raise PermissionError("resource_denied")
        return self.request_store.read(request_id)

    def _run_action(self, args: dict[str, Any]) -> str:
        action = _require_text(args, "action")
        if action == "get_health_snapshot":
            return self.read_resource(RESOURCE_STATUS_CURRENT)
        if action == "read_recent_reports":
            return self.read_resource(RESOURCE_REPORTS_RECENT)
        if action == "read_task_result":
            return self.read_resource(RESOURCE_RESULT_PREFIX + _require_text(args, "task_id"))
        if action == "read_submitted_task":
            return self._read_task_checked(args)
        if action == "read_submitted_request":
            return self._read_request_checked(args)
        raise ValueError("action_not_allowed")

    def _select_runner_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        mode = _require_text(args, "mode")
        if mode not in RUNNER_MODES:
            raise ValueError("unsupported_mode")
        self.control.request_mode(mode)
        return {"status": "accepted", "message": "runner mode request registered"}
