"""GET routes of the HTTP handler (mixin).

Routes (all but the OAuth discovery paths require the bearer token):

- ``/.well-known/oauth-authorization-server[...]``  OAuth discovery stub;
- ``/healthz``, ``/openapi.json``, ``/metrics``;
- ``/mcp``                       405 (the MCP transport is POST only);
- ``/resources/list``, ``/resources?uri=...``, ``/tools/list``;
- ``/tasks[?limit=N]``, ``/tasks/<id>``, ``/requests/<id>``;
- ``/snapshots/list``, ``/snapshots/export``.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Callable
from urllib.parse import ParseResult, parse_qs, urlparse

from .constants import METRICS_CONTENT_TYPE, OAUTH_DISCOVERY_PATHS, RESOURCE_REQUEST_PREFIX, RESOURCE_TASK_PREFIX
from .discovery import oauth_discovery_payload, openapi_spec
from .http_io import json_response, json_text_response, send_body
from .persistence import utc_now

# Exact paths -> handler method name. Prefix routes (/tasks/, /requests/) are
# checked afterwards; no exact path below starts with those prefixes, so the
# lookup order is equivalent to the historical if-chain.
_GET_ROUTES = {
    "/healthz": "_get_healthz",
    "/openapi.json": "_get_openapi",
    "/metrics": "_get_metrics",
    "/mcp": "_get_mcp",
    "/resources/list": "_get_resources_list",
    "/tools/list": "_get_tools_list",
    "/tasks": "_get_tasks",
    "/snapshots/list": "_get_snapshots_list",
    "/snapshots/export": "_get_snapshots_export",
    "/resources": "_get_resource",
}


class GetRoutesMixin:
    """Implements ``do_GET``. Expects ``self._app``, auth and observability mixins."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        self._obs_begin(path)
        try:
            self._dispatch_get(path, parsed)
        finally:
            self._obs_end()

    def _dispatch_get(self, path: str, parsed: ParseResult) -> None:
        if path in OAUTH_DISCOVERY_PATHS:
            # Served before auth: clients probe these before having a token.
            json_response(self, HTTPStatus.OK, oauth_discovery_payload(path))
            return
        if not self._require_auth():
            return
        route = _GET_ROUTES.get(path)
        if route is not None:
            getattr(self, route)(parsed)
            return
        if path.startswith("/tasks/"):
            task_id = path[len("/tasks/") :]
            self._get_stored_envelope(RESOURCE_TASK_PREFIX + task_id, task_id, self._app.task_store.read)
            return
        if path.startswith("/requests/"):
            request_id = path[len("/requests/") :]
            self._get_stored_envelope(RESOURCE_REQUEST_PREFIX + request_id, request_id, self._app.request_store.read)
            return
        json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _get_healthz(self, parsed: ParseResult) -> None:
        json_response(
            self,
            HTTPStatus.OK,
            {
                "ok": True,
                "schema_version": 1,
                "export_dir": str(self._app.store.export_dir),
                "time_utc": utc_now(),
            },
        )

    def _get_openapi(self, parsed: ParseResult) -> None:
        json_response(self, HTTPStatus.OK, openapi_spec())

    def _get_metrics(self, parsed: ParseResult) -> None:
        raw = self._app.obs.metrics.render().encode("utf-8")
        send_body(self, HTTPStatus.OK, METRICS_CONTENT_TYPE, raw)

    def _get_mcp(self, parsed: ParseResult) -> None:
        # Streamable HTTP MCP transport is primarily POST-based.
        json_response(self, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def _get_resources_list(self, parsed: ParseResult) -> None:
        json_response(self, HTTPStatus.OK, {"resources": self._app.list_resources()})

    def _get_tools_list(self, parsed: ParseResult) -> None:
        json_response(self, HTTPStatus.OK, {"tools": self._app.list_tools()})

    def _get_tasks(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        try:
            limit = int((query.get("limit") or ["100"])[0])
        except ValueError:
            limit = 100
        json_response(self, HTTPStatus.OK, {"ok": True, "tasks": self._app.task_store.list(limit)})

    def _get_stored_envelope(self, resource_uri: str, item_id: str, reader: Callable[[str], str]) -> None:
        """Serve ``tasks/<id>.json`` or ``requests/<id>.json`` after the policy check."""
        if not self._app.access_policy.resource_allowed(resource_uri):
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "forbidden_resource"})
            return
        try:
            body = reader(item_id)
        except FileNotFoundError:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        json_text_response(self, body)

    def _get_snapshots_list(self, parsed: ParseResult) -> None:
        snapshot_store = self._app.snapshot_store
        if snapshot_store is None:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "snapshots_disabled"})
            return
        json_response(
            self,
            HTTPStatus.OK,
            {
                "ok": True,
                "snapshot_dir": str(snapshot_store.snapshot_dir),
                "entries": snapshot_store.list_entries(),
            },
        )

    def _get_snapshots_export(self, parsed: ParseResult) -> None:
        if self._app.snapshot_store is None:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "snapshots_disabled"})
            return
        json_response(self, HTTPStatus.OK, self._app.snapshot_store.export_bundle())

    def _get_resource(self, parsed: ParseResult) -> None:
        qs = parse_qs(parsed.query)
        uri = (qs.get("uri") or [""])[0]
        if not uri:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing_uri"})
            return
        try:
            body = self._app.read_resource(uri)
        except PermissionError:
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "forbidden_resource"})
            return
        except FileNotFoundError:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        except ValueError:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "unsupported_resource"})
            return
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "io_error", "detail": str(exc)})
            return
        json_text_response(self, body)
