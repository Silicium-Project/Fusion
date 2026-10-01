#!/usr/bin/env python3
"""
Minimal MCP HTTP server for external clients (compatibility entry point).

The implementation lives in the ``tools/mcp/`` package (see its __init__.py
for the module layout). This file is kept because it is:

- run as a script: ``python3 tools/mcp_server.py --port ...`` (tests,
  ci/docker-compose.e2e.yml, systemd service, load test);
- run as a module: ``python -m tools.mcp_server``;
- imported: ``from tools.mcp_server import McpTaskStore`` (workloads, CLI,
  tests) and ``from mcp_server import McpTaskStore`` (tools/rpc_server.py,
  with tools/ on sys.path);
- byte-compiled by the Windows installer (``py -m py_compile``).

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

import sys
from pathlib import Path

# When run as a script (or imported as top-level ``mcp_server``), sys.path[0]
# is tools/ and the ``tools`` package is not importable. Add the repository
# root right after it: inserting at index 0 would let root-level directories
# (e.g. i18n/) shadow modules of tools/ such as i18n.py.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(1, _REPO_ROOT)

from tools.mcp.access_policy import McpAccessPolicy  # noqa: E402
from tools.mcp.app import McpHttpApp  # noqa: E402
from tools.mcp.cli import build_arg_parser, main  # noqa: E402
from tools.mcp.constants import (  # noqa: E402
    MCP_DEFAULT_PROTOCOL_VERSION,
    MCP_JSONRPC_VERSION,
    METRICS_CONTENT_TYPE,
    OAUTH_DISCOVERY_PATHS,
    RESOURCE_LOGS_PREFIX,
    RESOURCE_NODE_HEARTBEAT_PREFIX,
    RESOURCE_NODE_METRICS_PREFIX,
    RESOURCE_NODE_PEERS_PREFIX,
    RESOURCE_REPORTS_RECENT,
    RESOURCE_REQUEST_PREFIX,
    RESOURCE_RESULT_PREFIX,
    RESOURCE_STATUS_CURRENT,
    RESOURCE_TASK_PREFIX,
    SUPPORTED_RESOURCES,
    SUPPORTED_TOOLS,
    TOOL_GET_HEALTH,
    TOOL_GET_REQUEST,
    TOOL_GET_TASK,
    TOOL_INTERRUPT_ACTION,
    TOOL_RUN_ACTION,
    TOOL_SELECT_RUNNER_MODE,
    TOOL_SUBMIT_REQUEST,
    TOOL_SUBMIT_TASK,
)
from tools.mcp.control_plane import McpControlPlane  # noqa: E402
from tools.mcp.export_store import McpExportStore  # noqa: E402
from tools.mcp.handler import McpHttpHandler  # noqa: E402
from tools.mcp.metrics import McpMetrics  # noqa: E402
from tools.mcp.observability import McpLogger, McpObservability  # noqa: E402
from tools.mcp.request_store import McpRequestStore  # noqa: E402
from tools.mcp.snapshot_store import McpSnapshotStore  # noqa: E402
from tools.mcp.task_store import McpTaskStore  # noqa: E402

__all__ = [
    "MCP_DEFAULT_PROTOCOL_VERSION",
    "MCP_JSONRPC_VERSION",
    "METRICS_CONTENT_TYPE",
    "OAUTH_DISCOVERY_PATHS",
    "RESOURCE_LOGS_PREFIX",
    "RESOURCE_NODE_HEARTBEAT_PREFIX",
    "RESOURCE_NODE_METRICS_PREFIX",
    "RESOURCE_NODE_PEERS_PREFIX",
    "RESOURCE_REPORTS_RECENT",
    "RESOURCE_REQUEST_PREFIX",
    "RESOURCE_RESULT_PREFIX",
    "RESOURCE_STATUS_CURRENT",
    "RESOURCE_TASK_PREFIX",
    "SUPPORTED_RESOURCES",
    "SUPPORTED_TOOLS",
    "TOOL_GET_HEALTH",
    "TOOL_GET_REQUEST",
    "TOOL_GET_TASK",
    "TOOL_INTERRUPT_ACTION",
    "TOOL_RUN_ACTION",
    "TOOL_SELECT_RUNNER_MODE",
    "TOOL_SUBMIT_REQUEST",
    "TOOL_SUBMIT_TASK",
    "McpAccessPolicy",
    "McpControlPlane",
    "McpExportStore",
    "McpHttpApp",
    "McpHttpHandler",
    "McpLogger",
    "McpMetrics",
    "McpObservability",
    "McpRequestStore",
    "McpSnapshotStore",
    "McpTaskStore",
    "build_arg_parser",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
