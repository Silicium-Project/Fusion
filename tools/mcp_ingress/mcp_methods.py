"""Implementations of the MCP JSON-RPC methods (mixin).

Supported methods: ``ping``, ``initialize``, ``resources/list``,
``resources/read``, ``tools/list`` and ``tools/call``. Errors are signalled
with exceptions that the transport (handler_mcp.py) maps to JSON-RPC codes:
``PermissionError`` -> Forbidden, ``FileNotFoundError`` -> Not Found,
``ValueError`` -> Invalid params / Method not found.
"""

from __future__ import annotations

import time
from typing import Any

from .constants import MCP_DEFAULT_PROTOCOL_VERSION
from .persistence import compact_json
from .tool_catalog import RESOURCE_TEMPLATES, tool_descriptors

_SERVER_INFO = {"name": "silicium-mcp", "version": "1.0"}

# Placeholders that mark a URI of SUPPORTED_RESOURCES as a template.
_TEMPLATE_MARKERS = ("{task_id}", "{request_id}", "{node_id}")


def _require_params_object(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("bad_params")
    return params


class McpMethodsMixin:
    """Provides ``_handle_mcp_call``. Expects ``self._app`` and ``_observe_tool_call``."""

    _MCP_METHODS = {
        "ping": "_mcp_ping",
        "initialize": "_mcp_initialize",
        "resources/list": "_mcp_resources_list",
        "resources/read": "_mcp_resources_read",
        "tools/list": "_mcp_tools_list",
        "tools/call": "_mcp_tools_call",
    }

    def _handle_mcp_call(self, method: str, params: Any) -> Any:
        """Dispatch one JSON-RPC method and return its ``result``."""
        handler_name = self._MCP_METHODS.get(method)
        if handler_name is None:
            raise ValueError("unknown_method")
        return getattr(self, handler_name)(params)

    def _mcp_ping(self, params: Any) -> Any:
        return {}

    def _mcp_initialize(self, params: Any) -> Any:
        params = _require_params_object(params)
        client_proto = params.get("protocolVersion")
        # Echo the client's protocol version when given (no negotiation).
        protocol_version = client_proto if isinstance(client_proto, str) and client_proto else MCP_DEFAULT_PROTOCOL_VERSION
        return {
            "protocolVersion": protocol_version,
            "serverInfo": dict(_SERVER_INFO),
            "capabilities": {
                "resources": {"listChanged": False},
                "tools": {"listChanged": False},
            },
        }

    def _mcp_resources_list(self, params: Any) -> Any:
        resources: list[dict[str, Any]] = []
        for uri in self._app.list_resources():
            if any(marker in uri for marker in _TEMPLATE_MARKERS):
                continue
            resources.append({"uri": uri, "name": uri.rsplit("/", 1)[-1], "mimeType": "application/json"})
        # Include template URIs as discoverable patterns.
        for uri, name in RESOURCE_TEMPLATES:
            if self._app.access_policy.resource_allowed(uri):
                resources.append({"uri": uri, "name": name, "mimeType": "application/json"})
        return {"resources": resources}

    def _mcp_resources_read(self, params: Any) -> Any:
        params = _require_params_object(params)
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise ValueError("missing_uri")
        body = self._app.read_resource(uri)
        return {"contents": [{"uri": uri, "mimeType": "application/json", "text": body}]}

    def _mcp_tools_list(self, params: Any) -> Any:
        allowed = set(self._app.list_tools())
        return {"tools": [tool for tool in tool_descriptors() if str(tool.get("name", "")) in allowed]}

    def _mcp_tools_call(self, params: Any) -> Any:
        params = _require_params_object(params)
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise ValueError("missing_tool_name")
        if not self._app.access_policy.tool_allowed(name):
            raise PermissionError("tool_denied")
        started = time.monotonic()
        try:
            result = self._app.execute_tool(name, arguments)
        except Exception as exc:
            self._observe_tool_call(
                name=name,
                ok=False,
                duration_s=time.monotonic() - started,
                transport="jsonrpc",
                error=exc.__class__.__name__,
            )
            raise
        self._observe_tool_call(name=name, ok=True, duration_s=time.monotonic() - started, transport="jsonrpc")
        text = result if isinstance(result, str) else compact_json(result)
        return {"content": [{"type": "text", "text": text}], "isError": False}
