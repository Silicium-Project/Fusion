"""POST routes of the HTTP handler (mixin), except the ``/mcp`` transport.

Routes (all require the bearer token):

- ``/tasks``                submit a task (needs ``--enable-tools``);
- ``/tasks/<id>/cancel``    cancel a queued task (needs ``--enable-tools``);
- ``/auth/rotate_token``    replace the bearer token (needs ``--enable-tools``);
- ``/requests``             submit a post-job request (needs ``--enable-tools``);
- ``/snapshots/import``     import a snapshot bundle (needs ``--snapshot-dir``);
- ``/mcp``                  MCP JSON-RPC transport (handler_mcp.py);
- ``/tools``                legacy ``{"name", "args"}`` tool call.
"""

from __future__ import annotations

import time
import uuid
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import urlparse

from .constants import SUPPORTED_TOOLS, TOOL_SUBMIT_REQUEST, TOOL_SUBMIT_TASK
from .http_io import json_response, read_json_request
from .persistence import utc_now

# Sentinel returned by _read_body_or_reply when an error was already sent.
_NO_BODY = object()

# Exact paths -> handler method name; /tasks/<id>/cancel is matched afterwards
# (no exact path matches that pattern, so the order is equivalent to the
# historical if-chain).
_POST_ROUTES = {
    "/tasks": "_post_tasks",
    "/auth/rotate_token": "_post_rotate_token",
    "/requests": "_post_requests",
    "/snapshots/import": "_post_snapshot_import",
    "/mcp": "_post_mcp",
    "/tools": "_post_tools",
}

# Exceptions of execute_tool on POST /tools: (type, status, body, logged error).
# The logged error name is the literal class listed here, even for subclasses.
_TOOL_ERRORS: tuple[tuple[type[Exception], int, dict[str, str] | None, str], ...] = (
    (PermissionError, HTTPStatus.FORBIDDEN, {"error": "tool_disabled"}, "PermissionError"),
    (FileNotFoundError, HTTPStatus.NOT_FOUND, {"error": "not_found"}, "FileNotFoundError"),
    # None: body built from the exception (bad_request + detail).
    (ValueError, HTTPStatus.BAD_REQUEST, None, "ValueError"),
)


class PostRoutesMixin:
    """Implements ``do_POST``. Expects ``self._app``, auth, observability and MCP mixins."""

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        self._obs_begin(parsed.path or "/")
        try:
            self._dispatch_post(parsed.path)
        finally:
            self._obs_end()

    def _dispatch_post(self, path: str) -> None:
        if not self._require_auth():
            return
        route = _POST_ROUTES.get(path)
        if route is not None:
            getattr(self, route)()
            return
        if path.startswith("/tasks/") and path.endswith("/cancel"):
            self._post_cancel_task(path[len("/tasks/") : -len("/cancel")].strip("/"))
            return
        json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _read_body_or_reply(self) -> Any:
        """Return the decoded JSON body, or ``_NO_BODY`` after replying 400."""
        try:
            return read_json_request(self)
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return _NO_BODY

    def _tools_enabled_or_reply(self) -> bool:
        if not self._app.enable_tools:
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "tools_disabled"})
            return False
        return True

    def _post_tasks(self) -> None:
        self._submit_through_store(TOOL_SUBMIT_TASK, "http_tasks", self._app.task_store.submit)

    def _post_requests(self) -> None:
        self._submit_through_store(TOOL_SUBMIT_REQUEST, "http_requests", self._app.request_store.submit)

    def _submit_through_store(self, tool_name: str, transport: str, submit: Callable[[Any], dict[str, Any]]) -> None:
        """Shared body of POST /tasks and POST /requests (counted as tool calls)."""
        if not self._tools_enabled_or_reply():
            return
        if not self._app.access_policy.tool_allowed(tool_name):
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "forbidden_tool"})
            return
        req = self._read_body_or_reply()
        if req is _NO_BODY:
            return
        started = time.monotonic()
        try:
            result = submit(req)
        except ValueError as exc:
            self._observe_tool_call(
                name=tool_name,
                ok=False,
                duration_s=time.monotonic() - started,
                transport=transport,
                error="ValueError",
            )
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "bad_request", "detail": str(exc)})
            return
        self._observe_tool_call(name=tool_name, ok=True, duration_s=time.monotonic() - started, transport=transport)
        json_response(self, HTTPStatus.ACCEPTED, {"ok": True, **result})

    def _post_cancel_task(self, task_id: str) -> None:
        if not self._tools_enabled_or_reply():
            return
        try:
            result = self._app.task_store.cancel(task_id)
        except FileNotFoundError:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        except ValueError as exc:
            json_response(self, HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        json_response(self, HTTPStatus.OK, {"ok": True, "task": result})

    def _post_rotate_token(self) -> None:
        if not self._tools_enabled_or_reply():
            return
        # The body is optional; {"new_token": "..."} picks the new token.
        body: Any = {}
        if self.headers.get("Content-Length"):
            try:
                body = read_json_request(self)
            except ValueError as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "bad_request", "detail": str(exc)})
                return
        new_token = str(body.get("new_token", "") if isinstance(body, dict) else "").strip() or uuid.uuid4().hex
        rotated = self._app.rotate_token(new_token)
        json_response(self, HTTPStatus.OK, {"ok": True, "new_token": rotated, "time_utc": utc_now()})

    def _post_snapshot_import(self) -> None:
        if self._app.snapshot_store is None:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "snapshots_disabled"})
            return
        req = self._read_body_or_reply()
        if req is _NO_BODY:
            return
        try:
            imported = self._app.snapshot_store.import_bundle(req)
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        json_response(self, HTTPStatus.OK, {"ok": True, "imported": imported})

    def _post_tools(self) -> None:
        req = self._read_body_or_reply()
        if req is _NO_BODY:
            return
        if not isinstance(req, dict):
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        name = req.get("name")
        args = req.get("args", {})
        if not isinstance(name, str) or not name:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing_tool_name"})
            return
        if name not in SUPPORTED_TOOLS:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "unsupported_tool"})
            return
        if not self._app.access_policy.tool_allowed(name):
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "forbidden_tool"})
            return
        self._run_http_tool(name, args)

    def _run_http_tool(self, name: str, args: Any) -> None:
        started = time.monotonic()
        try:
            result = self._app.execute_tool(name, args)
        except Exception as exc:
            self._reply_tool_error(name, started, exc)
            return
        self._observe_tool_call(name=name, ok=True, duration_s=time.monotonic() - started, transport="http_tools")
        # result may already be a JSON payload string (resources), so wrap it.
        if isinstance(result, str):
            json_response(self, HTTPStatus.OK, {"ok": True, "result_json": result})
        else:
            json_response(self, HTTPStatus.OK, {"ok": True, "result": result})

    def _reply_tool_error(self, name: str, started: float, exc: Exception) -> None:
        """Log the failed tool call and map the exception to an HTTP error."""
        status: int = HTTPStatus.INTERNAL_SERVER_ERROR
        body: dict[str, str] = {"error": "internal_error", "detail": str(exc)}
        error_name = exc.__class__.__name__
        for exc_type, exc_status, exc_body, logged_name in _TOOL_ERRORS:
            if isinstance(exc, exc_type):
                status = exc_status
                body = exc_body if exc_body is not None else {"error": "bad_request", "detail": str(exc)}
                error_name = logged_name
                break
        self._observe_tool_call(
            name=name,
            ok=False,
            duration_s=time.monotonic() - started,
            transport="http_tools",
            error=error_name,
        )
        json_response(self, status, body)
