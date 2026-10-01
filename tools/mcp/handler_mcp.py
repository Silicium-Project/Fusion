"""MCP Streamable-HTTP transport: JSON-RPC 2.0 over ``POST /mcp`` (mixin).

Accepts a single message or a batch. Notifications (no ``id``, method
``notifications/...``) get no response; a request that yields no response at
all is answered with ``204 No Content``. When the client accepts
``text/event-stream`` the response is sent as one SSE ``message`` event,
otherwise as plain JSON. Method implementations live in mcp_methods.py.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Mapping

from .constants import MCP_JSONRPC_VERSION
from .http_io import json_response, read_json_request
from .persistence import compact_json

# JSON-RPC error codes used by the server (-32003/-32004 are server-defined).
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_FORBIDDEN = -32003
_NOT_FOUND = -32004


def jsonrpc_ok(req_id: Any, result: Any) -> Mapping[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": MCP_JSONRPC_VERSION, "id": req_id, "result": result}


def jsonrpc_err(req_id: Any, code: int, message: str, data: Any | None = None) -> Mapping[str, Any]:
    """Build a JSON-RPC error response (``data`` omitted when None)."""
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": MCP_JSONRPC_VERSION, "id": req_id, "error": err}


def _value_error_response(req_id: Any, msg: str) -> Mapping[str, Any]:
    # Every ValueError other than unknown_method is reported as invalid params.
    if msg in {"missing_uri", "missing_tool_name", "bad_params"}:
        return jsonrpc_err(req_id, _INVALID_PARAMS, "Invalid params", {"detail": msg})
    if msg == "unknown_method":
        return jsonrpc_err(req_id, _METHOD_NOT_FOUND, "Method not found")
    return jsonrpc_err(req_id, _INVALID_PARAMS, "Invalid params", {"detail": msg})


class McpTransportMixin:
    """Implements ``POST /mcp``. Expects ``_handle_mcp_call`` (McpMethodsMixin)."""

    def _post_mcp(self) -> None:
        try:
            req = read_json_request(self)
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if isinstance(req, list):
            responses = [r for r in (self._handle_jsonrpc_message(o) for o in req) if r is not None]
            if not responses:
                self._send_no_content()
                return
            self._send_mcp_response(responses)
            return

        resp = self._handle_jsonrpc_message(req)
        if resp is None:
            self._send_no_content()
            return
        self._send_mcp_response(resp)

    def _send_no_content(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _handle_jsonrpc_message(self, obj: Any) -> Mapping[str, Any] | None:
        """Process one JSON-RPC message; None for notifications."""
        if not isinstance(obj, dict):
            return jsonrpc_err(None, _INVALID_REQUEST, "Invalid Request")
        if obj.get("jsonrpc") not in (MCP_JSONRPC_VERSION, None):
            return jsonrpc_err(obj.get("id"), _INVALID_REQUEST, "Invalid Request")
        req_id = obj.get("id")
        method = obj.get("method")
        params = obj.get("params", {})
        if not isinstance(method, str) or not method:
            return jsonrpc_err(req_id, _INVALID_REQUEST, "Invalid Request")
        if isinstance(getattr(self, "_mcp_methods", None), list):
            self._mcp_methods.append(method)
        if req_id is None and method.startswith("notifications/"):
            return None
        metrics = self._app.obs.metrics
        try:
            result = self._handle_mcp_call(method, params)
            metrics.inc_jsonrpc(method, ok=True)
        except PermissionError:
            metrics.inc_jsonrpc(method, ok=False)
            return jsonrpc_err(req_id, _FORBIDDEN, "Forbidden")
        except FileNotFoundError:
            metrics.inc_jsonrpc(method, ok=False)
            return jsonrpc_err(req_id, _NOT_FOUND, "Not Found")
        except ValueError as exc:
            metrics.inc_jsonrpc(method, ok=False)
            return _value_error_response(req_id, str(exc))
        except Exception as exc:
            metrics.inc_jsonrpc(method, ok=False)
            return jsonrpc_err(req_id, _INTERNAL_ERROR, "Internal error", {"detail": str(exc)})
        return jsonrpc_ok(req_id, result)

    def _send_mcp_response(self, payload: Any) -> None:
        accept = (self.headers.get("Accept") or "").lower()
        if "text/event-stream" not in accept:
            json_response(self, HTTPStatus.OK, payload)
            return
        raw = ("event: message\ndata: " + compact_json(payload) + "\n\n").encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

