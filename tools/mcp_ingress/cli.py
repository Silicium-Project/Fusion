"""Command line and process entry point of the MCP/HTTP server.

``main(argv)`` parses the flags (each has an environment fallback), builds the
application, optionally starts the ZeroMQ RPC server in a daemon thread, logs
a ``listen`` event and serves until interrupted. Returns the process exit
code (2 when no export directory is configured).
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from .access_policy import McpAccessPolicy
from .app import McpHttpApp
from .handler import McpHttpHandler
from .observability import McpObservability
from .snapshot_store import McpSnapshotStore
from .validation import csv_values


def build_arg_parser() -> argparse.ArgumentParser:
    """Return the argparse parser of ``tools/mcp_server.py``."""
    p = argparse.ArgumentParser(prog="mcp_server", add_help=True)
    p.add_argument("--bind", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=9765, help="HTTP port (default: 9765)")
    p.add_argument("--export-dir", default="", help="Worker MCP export directory")
    p.add_argument("--snapshot-dir", default="", help="Enable persistent snapshots in this directory.")
    p.add_argument("--snapshot-max-files", type=int, default=200, help="Max number of snapshots kept (0 disables cap).")
    p.add_argument("--snapshot-max-bytes", type=int, default=10 * 1024 * 1024, help="Max total snapshot bytes (0 disables cap).")
    p.add_argument("--enable-tools", action="store_true", help="Enable guarded control tools")
    p.add_argument("--tool-allowlist", default="", help="Comma-separated allowed tool names/patterns")
    p.add_argument("--tool-denylist", default="", help="Comma-separated denied tool names/patterns")
    p.add_argument("--resource-allowlist", default="", help="Comma-separated allowed resource URI patterns")
    p.add_argument("--resource-denylist", default="", help="Comma-separated denied resource URI patterns")
    p.add_argument("--token", default="", help="Optional bearer token (or env SILICIUM_MCP_TOKEN)")
    p.add_argument("--no-auth", action="store_true", help="Disable bearer auth even if token env/flag is set")
    p.add_argument("--rpc-bind", default=os.environ.get("SILICIUM_RPC_BIND", ""), help="Optional ZeroMQ RPC control endpoint, e.g. tcp://127.0.0.1:9770")
    p.add_argument("--rpc-events-bind", default=os.environ.get("SILICIUM_RPC_EVENTS_BIND", "tcp://127.0.0.1:9771"), help="ZeroMQ PUB endpoint for task state events")
    p.add_argument("--log-format", choices=["text", "json"], default="text", help="Structured logs format (default: text)")
    return p


def _build_snapshot_store(args: argparse.Namespace) -> McpSnapshotStore | None:
    snapshot_dir_arg = str(args.snapshot_dir or os.environ.get("SILICIUM_MCP_SNAPSHOT_DIR", "")).strip()
    if not snapshot_dir_arg:
        return None
    snapshot_dir = Path(snapshot_dir_arg)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return McpSnapshotStore(
        snapshot_dir=snapshot_dir,
        max_files=int(args.snapshot_max_files),
        max_total_bytes=int(args.snapshot_max_bytes),
    )


def _policy_lists(args: argparse.Namespace) -> dict[str, list[str]]:
    """Allow/deny lists from flags, falling back to SILICIUM_MCP_* variables."""
    return {
        "tool_allowlist": csv_values(str(args.tool_allowlist or os.environ.get("SILICIUM_MCP_TOOL_ALLOWLIST", ""))),
        "tool_denylist": csv_values(str(args.tool_denylist or os.environ.get("SILICIUM_MCP_TOOL_DENYLIST", ""))),
        "resource_allowlist": csv_values(
            str(args.resource_allowlist or os.environ.get("SILICIUM_MCP_RESOURCE_ALLOWLIST", ""))
        ),
        "resource_denylist": csv_values(
            str(args.resource_denylist or os.environ.get("SILICIUM_MCP_RESOURCE_DENYLIST", ""))
        ),
    }


def _resolve_token(args: argparse.Namespace) -> str:
    if args.no_auth:
        return ""
    return args.token or os.environ.get("SILICIUM_MCP_TOKEN", "")


def _start_rpc_thread(args: argparse.Namespace, export_path: Path, token: str) -> None:
    # Keep RPC in the same process/export directory so task submission and
    # feedback observe identical durable state. The thread is daemonized and
    # therefore cannot change the historical MCP shutdown semantics.
    # rpc_server is imported as a top-level module: this only works when
    # tools/ is on sys.path (i.e. when started as `python3 tools/mcp_server.py`).
    from rpc_server import serve as serve_rpc

    threading.Thread(
        target=serve_rpc,
        args=(str(args.rpc_bind), export_path, token or "", str(args.rpc_events_bind)),
        name="silicium-rpc",
        daemon=True,
    ).start()


def _log_listen(
    app: McpHttpApp,
    args: argparse.Namespace,
    export_path: Path,
    snapshot_store: McpSnapshotStore | None,
    policy_lists: dict[str, list[str]],
    token: str,
) -> None:
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
        tool_allowlist=policy_lists["tool_allowlist"],
        tool_denylist=policy_lists["tool_denylist"],
        resource_allowlist=policy_lists["resource_allowlist"],
        resource_denylist=policy_lists["resource_denylist"],
        token_enabled=bool(token),
        metrics_endpoint="/metrics",
        mcp_endpoint="/mcp",
        rpc_endpoint=str(args.rpc_bind or ""),
        rpc_events_endpoint=str(args.rpc_events_bind or "") if args.rpc_bind else "",
    )


def main(argv: list[str] | None = None) -> int:
    """Run the server; returns the process exit code."""
    args = build_arg_parser().parse_args(argv)
    export_dir = args.export_dir or os.environ.get("SILICIUM_MCP_EXPORT_DIR", "")
    if not export_dir:
        sys.stderr.write("error: missing --export-dir (or SILICIUM_MCP_EXPORT_DIR)\n")
        return 2
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)

    snapshot_store = _build_snapshot_store(args)
    policy_lists = _policy_lists(args)
    token = _resolve_token(args)
    app = McpHttpApp(
        export_path,
        enable_tools=bool(args.enable_tools),
        token=token or None,
        obs=McpObservability(str(args.log_format)),
        snapshot_store=snapshot_store,
        access_policy=McpAccessPolicy(**policy_lists),
    )

    if args.rpc_bind:
        _start_rpc_thread(args, export_path, token)

    server = ThreadingHTTPServer((args.bind, args.port), McpHttpHandler)
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]

    _log_listen(app, args, export_path, snapshot_store, policy_lists, token)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
