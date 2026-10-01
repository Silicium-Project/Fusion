"""The HTTP request handler, assembled from per-feature mixins.

``ThreadingHTTPServer`` instantiates ``McpHttpHandler`` once per request; the
shared application state is attached to the server as ``server.app`` (see
cli.py). Each mixin lives in its own module:

- handler_observe.py  access log, metrics, ``send_response`` hook;
- auth.py             bearer-token check;
- handler_get.py      GET routes;
- handler_post.py     POST routes;
- handler_mcp.py      ``POST /mcp`` JSON-RPC transport;
- mcp_methods.py      MCP method implementations.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from .app import McpHttpApp
from .auth import AuthMixin
from .handler_get import GetRoutesMixin
from .handler_mcp import McpTransportMixin
from .handler_observe import ObservabilityMixin
from .handler_post import PostRoutesMixin
from .mcp_methods import McpMethodsMixin


class McpHttpHandler(
    ObservabilityMixin,
    AuthMixin,
    GetRoutesMixin,
    PostRoutesMixin,
    McpTransportMixin,
    McpMethodsMixin,
    BaseHTTPRequestHandler,
):
    """HTTP/MCP request handler of the Silicium ingress server."""

    server_version = "SiliciumMcpHttp/1.0"

    @property
    def _app(self) -> McpHttpApp:
        return self.server.app  # type: ignore[attr-defined]
