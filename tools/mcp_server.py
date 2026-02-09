#!/usr/bin/env python3
"""
Minimal MCP HTTP server for external clients.

V1 design:
- Local-only HTTP by default (127.0.0.1).
- Reads resources from a worker export directory produced by:
  worker --mcp-readonly --mcp-export-dir <dir>
- Exposes a small surface:
  - GET  /healthz
  - GET  /resources/list
  - GET  /resources?uri=<resource_uri>
  - GET  /tools/list
  - POST /tools  {"name": "...", "args": {...}}  (guarded allowlist)
- Optional bearer token auth via SILICIUM_MCP_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse


RESOURCE_STATUS_CURRENT = "resources://silicium/status/current"
RESOURCE_REPORTS_RECENT = "resources://silicium/reports/recent"
RESOURCE_RESULT_PREFIX = "resources://silicium/results/by-task/"
RESOURCE_LOGS_PREFIX = "resources://silicium/logs/by-task/"

TOOL_RUN_ACTION = "tools.silicium.run_action"
TOOL_INTERRUPT_ACTION = "tools.silicium.interrupt_action"
TOOL_SELECT_RUNNER_MODE = "tools.silicium.select_runner_mode"
TOOL_GET_HEALTH = "tools.silicium.get_health"

SUPPORTED_RESOURCES = (
    RESOURCE_STATUS_CURRENT,
    RESOURCE_REPORTS_RECENT,
    "resources://silicium/results/by-task/{task_id}",
    "resources://silicium/logs/by-task/{task_id}",
)

SUPPORTED_TOOLS = (
    TOOL_RUN_ACTION,
    TOOL_INTERRUPT_ACTION,
    TOOL_SELECT_RUNNER_MODE,
    TOOL_GET_HEALTH,
)

_SAFE_TASK_ID_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_request(handler: BaseHTTPRequestHandler, max_bytes: int = 256 * 1024) -> Any:
    length = handler.headers.get("Content-Length")
    if not length:
        raise ValueError("missing_content_length")
    try:
        size = int(length)
    except ValueError as exc:
        raise ValueError("bad_content_length") from exc
    if size < 0 or size > max_bytes:
        raise ValueError("payload_too_large")
    raw = handler.rfile.read(size)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid_json") from exc


def _sanitize_task_id(task_id: str) -> str:
    task_id = task_id.strip()
    if not task_id:
        return ""
    return _SAFE_TASK_ID_RE.sub("_", task_id)


class McpExportStore:
    def __init__(self, export_dir: Path) -> None:
        self._export_dir = export_dir

    @property
    def export_dir(self) -> Path:
        return self._export_dir

    def read_resource(self, uri: str) -> str:
        if uri == RESOURCE_STATUS_CURRENT:
            return self._read_text(self._export_dir / "status.current.json")
        if uri == RESOURCE_REPORTS_RECENT:
            return self._read_text(self._export_dir / "reports.recent.json")
        if uri.startswith(RESOURCE_RESULT_PREFIX):
            task_id = _sanitize_task_id(uri[len(RESOURCE_RESULT_PREFIX) :])
            if not task_id:
                raise FileNotFoundError("missing_task_id")
            return self._read_text(self._export_dir / f"result.{task_id}.json")
        if uri.startswith(RESOURCE_LOGS_PREFIX):
            task_id = _sanitize_task_id(uri[len(RESOURCE_LOGS_PREFIX) :])
            if not task_id:
                raise FileNotFoundError("missing_task_id")
            return self._read_text(self._export_dir / f"logs.{task_id}.json")
        raise ValueError("unsupported_resource")

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")


class McpControlPlane:
    """
    Writes control requests into the export directory so a worker can
    consume them out-of-process.
    """

    def __init__(self, export_dir: Path) -> None:
        self._path = export_dir / "control.request.json"
        self._lock = threading.Lock()

    def request_interrupt(self) -> None:
        self._write({"kind": "interrupt", "timestamp_utc": _utc_now()})

    def request_mode(self, mode: str) -> None:
        self._write({"kind": "select_runner_mode", "mode": mode, "timestamp_utc": _utc_now()})

    def _write(self, payload: Mapping[str, Any]) -> None:
        with self._lock:
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
            tmp.replace(self._path)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class McpHttpHandler(BaseHTTPRequestHandler):
    server_version = "SiliciumMcpHttp/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep logs structured-ish and single-line.
        sys.stdout.write("[mcp-http] " + (fmt % args) + "\n")

    @property
    def _app(self) -> "McpHttpApp":
        return self.server.app  # type: ignore[attr-defined]

    def _require_auth(self) -> bool:
        token = self._app.token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return False
        provided = header[len("Bearer ") :].strip()
        if provided != token:
            _json_response(self, HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "schema_version": 1,
                    "export_dir": str(self._app.store.export_dir),
                    "time_utc": _utc_now(),
                },
            )
            return
        if parsed.path == "/resources/list":
            _json_response(self, HTTPStatus.OK, {"resources": list(SUPPORTED_RESOURCES)})
            return
        if parsed.path == "/tools/list":
            _json_response(self, HTTPStatus.OK, {"tools": list(SUPPORTED_TOOLS)})
            return
        if parsed.path == "/resources":
            qs = parse_qs(parsed.query)
            uri = (qs.get("uri") or [""])[0]
            if not uri:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing_uri"})
                return
            try:
                body = self._app.store.read_resource(uri)
            except FileNotFoundError:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            except ValueError:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "unsupported_resource"})
                return
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "io_error", "detail": str(exc)})
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            raw = body.encode("utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        if parsed.path != "/tools":
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            req = _read_json_request(self)
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if not isinstance(req, dict):
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        name = req.get("name")
        args = req.get("args", {})
        if not isinstance(name, str) or not name:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing_tool_name"})
            return
        if name not in SUPPORTED_TOOLS:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "unsupported_tool"})
            return

        try:
            result = self._app.execute_tool(name, args)
        except PermissionError:
            _json_response(self, HTTPStatus.FORBIDDEN, {"error": "tool_disabled"})
            return
        except FileNotFoundError:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "bad_request", "detail": str(exc)})
            return
        except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error", "detail": str(exc)})
            return

        # result may already be a JSON payload string (resources), so wrap it.
        if isinstance(result, str):
            _json_response(self, HTTPStatus.OK, {"ok": True, "result_json": result})
        else:
            _json_response(self, HTTPStatus.OK, {"ok": True, "result": result})


class McpHttpApp:
    def __init__(self, export_dir: Path, enable_tools: bool, token: str | None) -> None:
        self.store = McpExportStore(export_dir)
        self.control = McpControlPlane(export_dir)
        self.enable_tools = enable_tools
        self.token = token or ""

    def execute_tool(self, name: str, args: Any) -> Any:
        if name == TOOL_GET_HEALTH:
            return self.store.read_resource(RESOURCE_STATUS_CURRENT)

        if not self.enable_tools:
            raise PermissionError("tools_disabled")

        if name == TOOL_RUN_ACTION:
            if not isinstance(args, dict):
                raise ValueError("args_not_object")
            action = args.get("action")
            if not isinstance(action, str) or not action:
                raise ValueError("missing_action")
            if action == "get_health_snapshot":
                return self.store.read_resource(RESOURCE_STATUS_CURRENT)
            if action == "read_recent_reports":
                return self.store.read_resource(RESOURCE_REPORTS_RECENT)
            if action == "read_task_result":
                task_id = args.get("task_id")
                if not isinstance(task_id, str) or not task_id:
                    raise ValueError("missing_task_id")
                return self.store.read_resource(RESOURCE_RESULT_PREFIX + task_id)
            raise ValueError("action_not_allowed")

        if name == TOOL_INTERRUPT_ACTION:
            self.control.request_interrupt()
            return {"status": "accepted", "message": "interrupt request registered"}

        if name == TOOL_SELECT_RUNNER_MODE:
            if not isinstance(args, dict):
                raise ValueError("args_not_object")
            mode = args.get("mode")
            if not isinstance(mode, str) or not mode:
                raise ValueError("missing_mode")
            if mode not in ("auto", "emu", "native", "dynamo"):
                raise ValueError("unsupported_mode")
            self.control.request_mode(mode)
            return {"status": "accepted", "message": "runner mode request registered"}

        raise ValueError("unsupported_tool")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mcp_server", add_help=True)
    p.add_argument("--bind", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=9765, help="HTTP port (default: 9765)")
    p.add_argument("--export-dir", default="", help="Worker MCP export directory")
    p.add_argument("--enable-tools", action="store_true", help="Enable guarded control tools")
    p.add_argument("--token", default="", help="Optional bearer token (or env SILICIUM_MCP_TOKEN)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    export_dir = args.export_dir or os.environ.get("SILICIUM_MCP_EXPORT_DIR", "")
    if not export_dir:
        sys.stderr.write("error: missing --export-dir (or SILICIUM_MCP_EXPORT_DIR)\n")
        return 2
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)

    token = args.token or os.environ.get("SILICIUM_MCP_TOKEN", "")
    app = McpHttpApp(export_path, enable_tools=bool(args.enable_tools), token=token or None)

    server = ThreadingHTTPServer((args.bind, args.port), McpHttpHandler)
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]

    sys.stdout.write(f"[mcp-http] listening on http://{args.bind}:{args.port}\n")
    sys.stdout.flush()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

