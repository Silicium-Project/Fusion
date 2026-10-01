"""Shared helpers for the ``tests/test_mcp_server_*.py`` suites.

Not a test module. The suites start the real MCP/HTTP server
(``tools/mcp_server.py``, implemented in ``tools/mcp_ingress/``) as a
subprocess on a free loopback port and talk to it over HTTP:

- ``_write_exports``: create the export directory and write JSON fixture files
  (``DEFAULT_EXPORTS`` is the minimal ``status.current`` + ``reports.recent`` pair).
- ``_server_env``: a copy of ``os.environ`` pointing the server at an export
  directory, optionally with a bearer token (``SILICIUM_MCP_TOKEN``).
- ``_mcp_server_cmd``: the ``tools/mcp_server.py --port ...`` command line.
- ``_running_server``: context manager that starts a server process and always
  stops it (terminate, then kill after 3 s).
- ``_find_free_port``, ``_base_url``, ``_http_get``, ``_http_post``, ``_wait_ready``:
  HTTP plumbing; ``_http_*`` return ``(status, body)`` even for HTTP errors.

Commands use paths relative to the repository root, like pytest is run from.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_EXPORTS = {
    "status.current.json": '{"ok":true}',
    "reports.recent.json": '{"tasks":[]}',
}


def _find_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _http_get(url: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _http_post(url: str, payload: dict, headers: dict[str, str] | None = None) -> tuple[int, str]:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _wait_ready(base_url: str, headers: dict[str, str] | None = None) -> None:
    deadline = time.time() + 5.0
    last: Any = None
    while time.time() < deadline:
        try:
            code, body = _http_get(base_url + "/healthz", headers=headers)
            last = (code, body)
            if code == 200:
                return
        except urllib.error.URLError as exc:
            last = f"url_error: {exc}"
        time.sleep(0.05)
    raise AssertionError(f"server not ready: {last}")


def _write_exports(export_dir: Path, files: dict[str, str]) -> None:
    """Create ``export_dir`` and write each ``name -> JSON text`` fixture in it."""
    export_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (export_dir / name).write_text(content, encoding="utf-8")


def _server_env(export_dir: Path, token: str | None = None) -> dict[str, str]:
    """Environment of a server reading ``export_dir`` (and requiring ``token``)."""
    env = os.environ.copy()
    env["SILICIUM_MCP_EXPORT_DIR"] = str(export_dir)
    if token is not None:
        env["SILICIUM_MCP_TOKEN"] = token
    return env


def _mcp_server_cmd(port: int, *extra: str) -> list[str]:
    """Command line starting ``tools/mcp_server.py`` on ``port``."""
    return [sys.executable, "tools/mcp_server.py", "--port", str(port), *extra]


def _start_server(cmd: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


@contextmanager
def _running_server(cmd: list[str], env: dict[str, str]) -> Iterator[subprocess.Popen]:
    """Start the server process for the ``with`` block, then stop it."""
    proc = _start_server(cmd, env)
    try:
        yield proc
    finally:
        _stop_server(proc)
