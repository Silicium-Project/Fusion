"""MCP server authentication: bearer token, OAuth discovery documents,
``silicium mcp serve --no-auth`` and token rotation (with the OpenAPI spec).
"""

import json
import subprocess
import sys
from pathlib import Path

from tests.mcp_server_support import (
    DEFAULT_EXPORTS,
    _base_url,
    _find_free_port,
    _http_get,
    _http_post,
    _mcp_server_cmd,
    _running_server,
    _server_env,
    _start_server,
    _wait_ready,
    _write_exports,
)


def test_mcp_server_token_auth(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    with _running_server(_mcp_server_cmd(port), _server_env(export_dir, token="secret")):
        base = _base_url(port)
        headers = {"Authorization": "Bearer secret"}
        _wait_ready(base, headers=headers)

        # Without token -> unauthorized.
        code, _ = _http_get(base + "/healthz")
        assert code in (401, 403)

        code, body = _http_get(base + "/.well-known/oauth-authorization-server")
        assert code == 200
        payload = json.loads(body)
        assert payload["oauth_supported"] is False

        _wait_ready(base, headers=headers)
        code, body = _http_get(base + "/healthz", headers=headers)
        assert code == 200
        assert json.loads(body)["ok"] is True


def test_mcp_server_oauth_discovery_paths(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    with _running_server(_mcp_server_cmd(port), _server_env(export_dir)):
        base = _base_url(port)
        _wait_ready(base)

        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-authorization-server/mcp",
            "/mcp/.well-known/oauth-authorization-server",
        ):
            code, body = _http_get(base + path)
            assert code == 200
            payload = json.loads(body)
            assert payload["oauth_supported"] is False
            assert payload["path"] == path
            assert payload["mcp_endpoint"] == "/mcp"


def test_silicium_mcp_serve_no_auth_overrides_token_env(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    _write_exports(export_dir, DEFAULT_EXPORTS)

    port = _find_free_port()
    cmd = [sys.executable, "silicium", "mcp", "serve", "--port", str(port), "--no-auth"]
    with _running_server(cmd, _server_env(export_dir, token="secret")):
        base = _base_url(port)
        _wait_ready(base)
        code, body = _http_get(base + "/healthz")
        assert code == 200
        assert json.loads(body)["ok"] is True


def _stop_and_print_output(proc: subprocess.Popen) -> None:
    # Unlike `_running_server`, dump the server output to help debug failures.
    proc.terminate()
    out, err = proc.communicate(timeout=3)
    print("SERVER STDOUT:\n", out)
    print("SERVER STDERR:\n", err)


def test_mcp_server_openapi_spec_and_token_rotation(tmp_path: Path) -> None:
    export_dir = tmp_path / "mcp"
    export_dir.mkdir(parents=True, exist_ok=True)
    port = _find_free_port()
    proc = _start_server(_mcp_server_cmd(port, "--enable-tools"), _server_env(export_dir, token="secret-token-1"))
    try:
        base = _base_url(port)
        auth_header = {"Authorization": "Bearer secret-token-1"}
        _wait_ready(base, headers=auth_header)

        # 1. OpenAPI spec
        code, body = _http_get(base + "/openapi.json", headers=auth_header)
        assert code == 200
        spec = json.loads(body)
        assert spec["openapi"] == "3.0.3"
        assert "/auth/rotate_token" in spec["paths"]

        # 2. Rotate token
        code, body = _http_post(base + "/auth/rotate_token", {"new_token": "secret-token-2"}, headers=auth_header)
        assert code == 200
        assert json.loads(body)["new_token"] == "secret-token-2"

        # 3. Old token should now be forbidden
        code, _ = _http_get(base + "/healthz", headers=auth_header)
        assert code == 403

        # 4. New token should be accepted
        new_auth_header = {"Authorization": "Bearer secret-token-2"}
        code, body = _http_get(base + "/healthz", headers=new_auth_header)
        assert code == 200
        assert json.loads(body)["ok"] is True
    finally:
        _stop_and_print_output(proc)
