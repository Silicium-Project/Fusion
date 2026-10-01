"""Static discovery documents: OAuth discovery stub and the OpenAPI spec.

MCP clients probe the OAuth authorization-server discovery paths before
connecting; the server answers (without authentication) that OAuth is not
supported so clients fall back to the static bearer token.
"""

from __future__ import annotations

from typing import Any, Mapping


def oauth_discovery_payload(path: str) -> Mapping[str, Any]:
    """Body returned on every path of ``OAUTH_DISCOVERY_PATHS``."""
    return {
        "oauth_supported": False,
        "error": "oauth_not_supported",
        "path": path,
        "mcp_endpoint": "/mcp",
    }


def openapi_spec() -> Mapping[str, Any]:
    """Minimal OpenAPI 3 document served on ``/openapi.json``.

    It only lists a subset of the routes (historical); see
    docs/contracts/mcp-connector-spec.md for the full surface.
    """
    return {
        "openapi": "3.0.3",
        "info": {"title": "Silicium MCP Server API", "version": "1.0.0"},
        "paths": {
            "/healthz": {"get": {"summary": "Health status"}},
            "/tasks": {"get": {"summary": "List tasks"}, "post": {"summary": "Submit task"}},
            "/tasks/{id}/cancel": {"post": {"summary": "Cancel pending task"}},
            "/auth/rotate_token": {"post": {"summary": "Rotate bearer token"}},
            "/openapi.json": {"get": {"summary": "OpenAPI specification"}},
        },
    }
