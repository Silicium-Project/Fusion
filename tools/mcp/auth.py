"""Bearer-token authentication for the HTTP handler (mixin).

The token comes from ``--token`` / ``SILICIUM_MCP_TOKEN`` (empty or
``--no-auth`` disables auth) and can be replaced at runtime through
``POST /auth/rotate_token`` (see ``McpHttpApp.rotate_token``).
"""

from __future__ import annotations

from http import HTTPStatus

from .http_io import json_response

_BEARER_PREFIX = "Bearer "


class AuthMixin:
    """Provides ``_require_auth`` to the handler. Expects ``self._app``."""

    def _require_auth(self) -> bool:
        """Return True when the request may proceed; otherwise send 401/403.

        A missing or non-Bearer ``Authorization`` header gets 401, a wrong
        token gets 403.
        """
        token = self._app.token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith(_BEARER_PREFIX):
            json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return False
        provided = header[len(_BEARER_PREFIX) :].strip()
        if provided != token:
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return False
        return True
