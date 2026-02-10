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
- Optional bearer token auth via SILICIUM_MCP_TOKEN (disable with --no-auth).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse


RESOURCE_STATUS_CURRENT = "resources://silicium/status/current"
RESOURCE_REPORTS_RECENT = "resources://silicium/reports/recent"
RESOURCE_RESULT_PREFIX = "resources://silicium/results/by-task/"
RESOURCE_LOGS_PREFIX = "resources://silicium/logs/by-task/"

MCP_JSONRPC_VERSION = "2.0"
MCP_DEFAULT_PROTOCOL_VERSION = "2024-11-05"

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

METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
OAUTH_DISCOVERY_PATHS = (
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-authorization-server/mcp",
    "/mcp/.well-known/oauth-authorization-server",
)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _oauth_discovery_payload(path: str) -> Mapping[str, Any]:
    return {
        "oauth_supported": False,
        "error": "oauth_not_supported",
        "path": path,
        "mcp_endpoint": "/mcp",
    }


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


def _jsonrpc_ok(req_id: Any, result: Any) -> Mapping[str, Any]:
    return {"jsonrpc": MCP_JSONRPC_VERSION, "id": req_id, "result": result}


def _jsonrpc_err(req_id: Any, code: int, message: str, data: Any | None = None) -> Mapping[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": MCP_JSONRPC_VERSION, "id": req_id, "error": err}


def _sanitize_task_id(task_id: str) -> str:
    task_id = task_id.strip()
    if not task_id:
        return ""
    return _SAFE_TASK_ID_RE.sub("_", task_id)


class McpExportStore:
    def __init__(self, export_dir: Path, snapshot_store: "McpSnapshotStore | None" = None) -> None:
        self._export_dir = export_dir
        self._snapshot_store = snapshot_store

    @property
    def export_dir(self) -> Path:
        return self._export_dir

    def read_resource(self, uri: str) -> str:
        try:
            body = self._read_live_resource(uri)
            if self._snapshot_store is not None:
                self._snapshot_store.capture(uri, body)
            return body
        except FileNotFoundError:
            if self._snapshot_store is not None:
                return self._snapshot_store.read_latest(uri)
            raise

    def _read_live_resource(self, uri: str) -> str:
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


class McpSnapshotStore:
    def __init__(self, snapshot_dir: Path, max_files: int, max_total_bytes: int) -> None:
        self._snapshot_dir = snapshot_dir
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._snapshot_dir / "snapshot.index.json"
        self._max_files = max(0, int(max_files))
        self._max_total_bytes = max(0, int(max_total_bytes))
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._load_index()

    @property
    def snapshot_dir(self) -> Path:
        return self._snapshot_dir

    def capture(self, uri: str, text: str) -> None:
        created_ms = int(time.time() * 1000)
        entry_id = f"{created_ms}-{uuid.uuid4().hex[:8]}"
        filename = f"{entry_id}.json"
        payload = text.encode("utf-8")
        final_path = self._snapshot_dir / filename
        tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        tmp_path.write_bytes(payload)
        tmp_path.replace(final_path)
        entry = {
            "id": entry_id,
            "uri": uri,
            "created_utc": _utc_now(),
            "created_ms": created_ms,
            "size": len(payload),
            "file": filename,
        }
        with self._lock:
            self._entries.append(entry)
            self._apply_retention_locked()
            self._save_index_locked()

    def read_latest(self, uri: str) -> str:
        with self._lock:
            for entry in reversed(self._entries):
                if str(entry.get("uri", "")) != uri:
                    continue
                p = self._snapshot_dir / str(entry.get("file", ""))
                if p.exists():
                    return p.read_text(encoding="utf-8")
            raise FileNotFoundError("snapshot_not_found")

    def list_entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "id": str(entry.get("id", "")),
                    "uri": str(entry.get("uri", "")),
                    "created_utc": str(entry.get("created_utc", "")),
                    "size": int(entry.get("size", 0)),
                    "file": str(entry.get("file", "")),
                }
                for entry in self._entries
            ]

    def export_bundle(self) -> dict[str, Any]:
        entries = self.list_entries()
        exported: list[dict[str, Any]] = []
        for entry in entries:
            p = self._snapshot_dir / entry["file"]
            if not p.exists():
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            exported.append(
                {
                    "id": entry["id"],
                    "uri": entry["uri"],
                    "created_utc": entry["created_utc"],
                    "size": entry["size"],
                    "text": text,
                }
            )
        return {"schema_version": 1, "exported_utc": _utc_now(), "entries": exported}

    def import_bundle(self, payload: Any) -> int:
        if not isinstance(payload, dict):
            raise ValueError("bad_bundle")
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("bad_bundle")
        imported = 0
        for item in entries:
            if not isinstance(item, dict):
                continue
            uri = item.get("uri")
            text = item.get("text")
            if not isinstance(uri, str) or not uri or not isinstance(text, str):
                continue
            self.capture(uri, text)
            imported += 1
        return imported

    def _load_index(self) -> None:
        with self._lock:
            entries: list[dict[str, Any]] = []
            if self._index_path.exists():
                try:
                    data = json.loads(self._index_path.read_text(encoding="utf-8"))
                    raw_entries = data.get("entries", []) if isinstance(data, dict) else []
                    if isinstance(raw_entries, list):
                        for item in raw_entries:
                            if not isinstance(item, dict):
                                continue
                            file_name = str(item.get("file", ""))
                            uri = str(item.get("uri", ""))
                            if not file_name or not uri:
                                continue
                            size = int(item.get("size", 0) or 0)
                            created_ms = int(item.get("created_ms", 0) or 0)
                            created_utc = str(item.get("created_utc", ""))
                            entry_id = str(item.get("id", ""))
                            entries.append(
                                {
                                    "id": entry_id or f"{created_ms}-{file_name}",
                                    "uri": uri,
                                    "created_utc": created_utc or _utc_now(),
                                    "created_ms": created_ms,
                                    "size": size,
                                    "file": file_name,
                                }
                            )
                except Exception:
                    entries = []
            self._entries = [e for e in entries if (self._snapshot_dir / str(e.get("file", ""))).exists()]
            self._entries.sort(key=lambda e: int(e.get("created_ms", 0)))
            self._apply_retention_locked()
            self._save_index_locked()

    def _apply_retention_locked(self) -> None:
        self._entries.sort(key=lambda e: int(e.get("created_ms", 0)))
        if self._max_files > 0:
            while len(self._entries) > self._max_files:
                removed = self._entries.pop(0)
                self._remove_entry_file(removed)
        if self._max_total_bytes > 0:
            total = sum(int(e.get("size", 0)) for e in self._entries)
            while self._entries and total > self._max_total_bytes:
                removed = self._entries.pop(0)
                total -= int(removed.get("size", 0))
                self._remove_entry_file(removed)

    def _remove_entry_file(self, entry: dict[str, Any]) -> None:
        file_name = str(entry.get("file", ""))
        if not file_name:
            return
        p = self._snapshot_dir / file_name
        try:
            p.unlink(missing_ok=True)
        except Exception:
            return

    def _save_index_locked(self) -> None:
        data = {"schema_version": 1, "entries": self._entries}
        tmp = self._index_path.with_suffix(self._index_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
        tmp.replace(self._index_path)


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


def _prom_escape(value: str) -> str:
    # Prometheus label escaping.
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class McpMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._http_requests: dict[tuple[str, str, str], int] = {}
        self._http_duration_sum_s: dict[tuple[str, str], float] = {}
        self._http_duration_count: dict[tuple[str, str], int] = {}
        self._jsonrpc_calls: dict[tuple[str, str], int] = {}
        self._tool_calls: dict[str, int] = {}

    def inc_http(self, method: str, path: str, status: int, duration_s: float) -> None:
        m = method.upper()
        p = path
        s = str(status)
        with self._lock:
            self._http_requests[(m, p, s)] = self._http_requests.get((m, p, s), 0) + 1
            self._http_duration_sum_s[(m, p)] = self._http_duration_sum_s.get((m, p), 0.0) + float(duration_s)
            self._http_duration_count[(m, p)] = self._http_duration_count.get((m, p), 0) + 1

    def inc_jsonrpc(self, method: str, ok: bool) -> None:
        key = (method, "false" if ok else "true")
        with self._lock:
            self._jsonrpc_calls[key] = self._jsonrpc_calls.get(key, 0) + 1

    def inc_tool_call(self, tool: str) -> None:
        with self._lock:
            self._tool_calls[tool] = self._tool_calls.get(tool, 0) + 1

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            lines.extend(
                [
                    "# HELP mcp_http_requests_total Total HTTP requests served by the MCP server.",
                    "# TYPE mcp_http_requests_total counter",
                ]
            )
            for (method, path, status), value in sorted(self._http_requests.items()):
                lines.append(
                    'mcp_http_requests_total{method="%s",path="%s",status="%s"} %d'
                    % (_prom_escape(method), _prom_escape(path), _prom_escape(status), value)
                )

            lines.extend(
                [
                    "# HELP mcp_http_request_duration_seconds HTTP request durations (sum/count).",
                    "# TYPE mcp_http_request_duration_seconds summary",
                ]
            )
            for (method, path), value in sorted(self._http_duration_sum_s.items()):
                lines.append(
                    'mcp_http_request_duration_seconds_sum{method="%s",path="%s"} %.6f'
                    % (_prom_escape(method), _prom_escape(path), float(value))
                )
            for (method, path), value in sorted(self._http_duration_count.items()):
                lines.append(
                    'mcp_http_request_duration_seconds_count{method="%s",path="%s"} %d'
                    % (_prom_escape(method), _prom_escape(path), value)
                )

            lines.extend(
                [
                    "# HELP mcp_jsonrpc_calls_total Total JSON-RPC calls received on /mcp.",
                    "# TYPE mcp_jsonrpc_calls_total counter",
                ]
            )
            for (method, is_error), value in sorted(self._jsonrpc_calls.items()):
                lines.append(
                    'mcp_jsonrpc_calls_total{method="%s",is_error="%s"} %d'
                    % (_prom_escape(method), _prom_escape(is_error), value)
                )

            lines.extend(
                [
                    "# HELP mcp_tool_calls_total Total tool invocations (HTTP /tools and MCP tools/call).",
                    "# TYPE mcp_tool_calls_total counter",
                ]
            )
            for tool, value in sorted(self._tool_calls.items()):
                lines.append('mcp_tool_calls_total{tool="%s"} %d' % (_prom_escape(tool), value))

        return "\n".join(lines) + "\n"


class McpLogger:
    def __init__(self, fmt: str) -> None:
        self._fmt = fmt

    def log(self, event: str, **fields: Any) -> None:
        if self._fmt == "json":
            payload = {"ts": _utc_now(), "event": event, **fields}
            sys.stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n")
            sys.stdout.flush()
            return
        # text
        parts = [f"{k}={fields[k]!r}" for k in sorted(fields.keys())]
        sys.stdout.write("[mcp-http] " + event + (" " + " ".join(parts) if parts else "") + "\n")
        sys.stdout.flush()


class McpObservability:
    def __init__(self, log_format: str) -> None:
        self.metrics = McpMetrics()
        self.logger = McpLogger(log_format)


class McpHttpHandler(BaseHTTPRequestHandler):
    server_version = "SiliciumMcpHttp/1.0"

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:  # noqa: N802
        # Disable BaseHTTPRequestHandler access logging; we emit structured logs ourselves.
        return

    def log_message(self, fmt: str, *args: Any) -> None:
        # Disable BaseHTTPRequestHandler logging; see log_request override above.
        return

    def send_response(self, code: int, message: str | None = None) -> None:  # noqa: N802
        self._resp_status = int(code)
        super().send_response(code, message)

    @property
    def _app(self) -> "McpHttpApp":
        return self.server.app  # type: ignore[attr-defined]

    def _obs_begin(self, path: str) -> None:
        self._req_id = uuid.uuid4().hex
        self._req_start = time.monotonic()
        self._req_path = path
        self._resp_status = 0
        self._mcp_methods: list[str] = []

    def _obs_end(self) -> None:
        try:
            start = getattr(self, "_req_start", None)
            path = getattr(self, "_req_path", "")
            if start is None:
                return
            duration_s = max(0.0, time.monotonic() - float(start))
            status = int(getattr(self, "_resp_status", 0) or 0)
            method = (self.command or "").upper()
            self._app.obs.metrics.inc_http(method, path, status, duration_s)

            fields: dict[str, Any] = {
                "request_id": getattr(self, "_req_id", ""),
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": round(duration_s * 1000.0, 3),
                "client_ip": (self.client_address[0] if self.client_address else ""),
            }
            ua = (self.headers.get("User-Agent") or "").strip()
            if ua:
                fields["user_agent"] = ua[:200]
            mcp_methods = getattr(self, "_mcp_methods", None)
            if mcp_methods:
                fields["mcp_methods"] = mcp_methods[:20]
            self._app.obs.logger.log("http_request", **fields)
        except Exception:
            return

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
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        self._obs_begin(path)
        try:
            if path in OAUTH_DISCOVERY_PATHS:
                _json_response(self, HTTPStatus.OK, _oauth_discovery_payload(path))
                return
            if not self._require_auth():
                return
            if path == "/healthz":
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
            if path == "/metrics":
                raw = self._app.obs.metrics.render().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", METRICS_CONTENT_TYPE)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if path == "/mcp":
                # Streamable HTTP MCP transport is primarily POST-based.
                _json_response(self, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})
                return
            if path == "/resources/list":
                _json_response(self, HTTPStatus.OK, {"resources": list(SUPPORTED_RESOURCES)})
                return
            if path == "/tools/list":
                _json_response(self, HTTPStatus.OK, {"tools": list(SUPPORTED_TOOLS)})
                return
            if path == "/snapshots/list":
                if self._app.snapshot_store is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "snapshots_disabled"})
                    return
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "snapshot_dir": str(self._app.snapshot_store.snapshot_dir),
                        "entries": self._app.snapshot_store.list_entries(),
                    },
                )
                return
            if path == "/snapshots/export":
                if self._app.snapshot_store is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "snapshots_disabled"})
                    return
                _json_response(self, HTTPStatus.OK, self._app.snapshot_store.export_bundle())
                return
            if path == "/resources":
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
        finally:
            self._obs_end()

    def _send_mcp_response(self, payload: Any) -> None:
        accept = (self.headers.get("Accept") or "").lower()
        if "text/event-stream" in accept:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
            raw = ("event: message\ndata: " + body + "\n\n").encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        _json_response(self, HTTPStatus.OK, payload)

    def _handle_mcp_call(self, method: str, params: Any) -> Any:
        if method == "ping":
            return {}

        if method == "initialize":
            if not isinstance(params, dict):
                raise ValueError("bad_params")
            client_proto = params.get("protocolVersion")
            protocol_version = client_proto if isinstance(client_proto, str) and client_proto else MCP_DEFAULT_PROTOCOL_VERSION
            return {
                "protocolVersion": protocol_version,
                "serverInfo": {"name": "silicium-mcp", "version": "1.0"},
                "capabilities": {
                    "resources": {"listChanged": False},
                    "tools": {"listChanged": False},
                },
            }

        if method == "resources/list":
            resources: list[dict[str, Any]] = []
            for uri in SUPPORTED_RESOURCES:
                if "{task_id}" in uri:
                    continue
                resources.append({"uri": uri, "name": uri.rsplit("/", 1)[-1], "mimeType": "application/json"})
            # Include template URIs as discoverable patterns.
            resources.append({"uri": "resources://silicium/results/by-task/{task_id}", "name": "result_by_task", "mimeType": "application/json"})
            resources.append({"uri": "resources://silicium/logs/by-task/{task_id}", "name": "logs_by_task", "mimeType": "application/json"})
            return {"resources": resources}

        if method == "resources/read":
            if not isinstance(params, dict):
                raise ValueError("bad_params")
            uri = params.get("uri")
            if not isinstance(uri, str) or not uri:
                raise ValueError("missing_uri")
            body = self._app.store.read_resource(uri)
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": body}]}

        if method == "tools/list":
            tools: list[dict[str, Any]] = [
                {
                    "name": TOOL_GET_HEALTH,
                    "description": "Return status.current.json from the worker export directory.",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                {
                    "name": TOOL_RUN_ACTION,
                    "description": "Run a guarded read-only action (exported snapshots).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "task_id": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                {
                    "name": TOOL_INTERRUPT_ACTION,
                    "description": "Request an interrupt via control.request.json (if enabled).",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                {
                    "name": TOOL_SELECT_RUNNER_MODE,
                    "description": "Request a runner mode selection via control.request.json (if enabled).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"mode": {"type": "string", "enum": ["auto", "emu", "native", "dynamo"]}},
                        "required": ["mode"],
                        "additionalProperties": False,
                    },
                },
            ]
            return {"tools": tools}

        if method == "tools/call":
            if not isinstance(params, dict):
                raise ValueError("bad_params")
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not name:
                raise ValueError("missing_tool_name")
            self._app.obs.metrics.inc_tool_call(name)
            result = self._app.execute_tool(name, arguments)
            if isinstance(result, str):
                text = result
            else:
                text = json.dumps(result, separators=(",", ":"), ensure_ascii=True)
            return {"content": [{"type": "text", "text": text}], "isError": False}

        raise ValueError("unknown_method")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        self._obs_begin(parsed.path or "/")
        try:
            if not self._require_auth():
                return
            if parsed.path == "/snapshots/import":
                if self._app.snapshot_store is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "snapshots_disabled"})
                    return
                try:
                    req = _read_json_request(self)
                except ValueError as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                try:
                    imported = self._app.snapshot_store.import_bundle(req)
                except ValueError as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                _json_response(self, HTTPStatus.OK, {"ok": True, "imported": imported})
                return
            if parsed.path == "/mcp":
                try:
                    req = _read_json_request(self)
                except ValueError as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                def handle_one(obj: Any) -> Mapping[str, Any] | None:
                    if not isinstance(obj, dict):
                        return _jsonrpc_err(None, -32600, "Invalid Request")
                    if obj.get("jsonrpc") not in (MCP_JSONRPC_VERSION, None):
                        return _jsonrpc_err(obj.get("id"), -32600, "Invalid Request")
                    req_id = obj.get("id")
                    method = obj.get("method")
                    params = obj.get("params", {})
                    if not isinstance(method, str) or not method:
                        return _jsonrpc_err(req_id, -32600, "Invalid Request")
                    if isinstance(getattr(self, "_mcp_methods", None), list):
                        self._mcp_methods.append(method)
                    if req_id is None and method.startswith("notifications/"):
                        return None
                    try:
                        result = self._handle_mcp_call(method, params)
                        self._app.obs.metrics.inc_jsonrpc(method, ok=True)
                    except PermissionError:
                        self._app.obs.metrics.inc_jsonrpc(method, ok=False)
                        return _jsonrpc_err(req_id, -32003, "Forbidden")
                    except FileNotFoundError:
                        self._app.obs.metrics.inc_jsonrpc(method, ok=False)
                        return _jsonrpc_err(req_id, -32004, "Not Found")
                    except ValueError as exc:
                        self._app.obs.metrics.inc_jsonrpc(method, ok=False)
                        msg = str(exc)
                        if msg in {"missing_uri", "missing_tool_name", "bad_params"}:
                            return _jsonrpc_err(req_id, -32602, "Invalid params", {"detail": msg})
                        if msg == "unknown_method":
                            return _jsonrpc_err(req_id, -32601, "Method not found")
                        return _jsonrpc_err(req_id, -32602, "Invalid params", {"detail": msg})
                    except Exception as exc:
                        self._app.obs.metrics.inc_jsonrpc(method, ok=False)
                        return _jsonrpc_err(req_id, -32603, "Internal error", {"detail": str(exc)})
                    return _jsonrpc_ok(req_id, result)

                if isinstance(req, list):
                    responses = [r for r in (handle_one(o) for o in req) if r is not None]
                    if not responses:
                        self.send_response(HTTPStatus.NO_CONTENT)
                        self.end_headers()
                        return
                    self._send_mcp_response(responses)
                    return

                resp = handle_one(req)
                if resp is None:
                    self.send_response(HTTPStatus.NO_CONTENT)
                    self.end_headers()
                    return
                self._send_mcp_response(resp)
                return

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
                self._app.obs.metrics.inc_tool_call(name)
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
        finally:
            self._obs_end()


class McpHttpApp:
    def __init__(
        self,
        export_dir: Path,
        enable_tools: bool,
        token: str | None,
        obs: McpObservability,
        snapshot_store: McpSnapshotStore | None = None,
    ) -> None:
        self.snapshot_store = snapshot_store
        self.store = McpExportStore(export_dir, snapshot_store=snapshot_store)
        self.control = McpControlPlane(export_dir)
        self.enable_tools = enable_tools
        self.token = token or ""
        self.obs = obs

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
    p.add_argument("--snapshot-dir", default="", help="Enable persistent snapshots in this directory.")
    p.add_argument("--snapshot-max-files", type=int, default=200, help="Max number of snapshots kept (0 disables cap).")
    p.add_argument("--snapshot-max-bytes", type=int, default=10 * 1024 * 1024, help="Max total snapshot bytes (0 disables cap).")
    p.add_argument("--enable-tools", action="store_true", help="Enable guarded control tools")
    p.add_argument("--token", default="", help="Optional bearer token (or env SILICIUM_MCP_TOKEN)")
    p.add_argument("--no-auth", action="store_true", help="Disable bearer auth even if token env/flag is set")
    p.add_argument("--log-format", choices=["text", "json"], default="text", help="Structured logs format (default: text)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    export_dir = args.export_dir or os.environ.get("SILICIUM_MCP_EXPORT_DIR", "")
    if not export_dir:
        sys.stderr.write("error: missing --export-dir (or SILICIUM_MCP_EXPORT_DIR)\n")
        return 2
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)

    snapshot_dir_arg = str(args.snapshot_dir or os.environ.get("SILICIUM_MCP_SNAPSHOT_DIR", "")).strip()
    snapshot_store: McpSnapshotStore | None = None
    if snapshot_dir_arg:
        snapshot_dir = Path(snapshot_dir_arg)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_store = McpSnapshotStore(
            snapshot_dir=snapshot_dir,
            max_files=int(args.snapshot_max_files),
            max_total_bytes=int(args.snapshot_max_bytes),
        )

    token = ""
    if not args.no_auth:
        token = args.token or os.environ.get("SILICIUM_MCP_TOKEN", "")
    obs = McpObservability(str(args.log_format))
    app = McpHttpApp(
        export_path,
        enable_tools=bool(args.enable_tools),
        token=token or None,
        obs=obs,
        snapshot_store=snapshot_store,
    )

    server = ThreadingHTTPServer((args.bind, args.port), McpHttpHandler)
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]

    app.obs.logger.log(
        "listen",
        bind=str(args.bind),
        port=int(args.port),
        export_dir=str(export_path),
        snapshot_enabled=bool(snapshot_store is not None),
        snapshot_dir=str(snapshot_store.snapshot_dir) if snapshot_store is not None else "",
        snapshot_max_files=int(args.snapshot_max_files),
        snapshot_max_bytes=int(args.snapshot_max_bytes),
        enable_tools=bool(args.enable_tools),
        token_enabled=bool(token),
        metrics_endpoint="/metrics",
        mcp_endpoint="/mcp",
    )
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
