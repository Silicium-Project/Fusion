#!/usr/bin/env python3
"""
Role-aware Silicium network node daemon (entry point and compatibility facade).

This daemon consumes the MCP/HTTP ingress queues produced by tools/mcp_server.py.
It is intentionally service-shaped: a node has roles, prioritizes urgent
post-job requests, exchanges larger payloads through P2P/content references, and
publishes stable result/log resources back into the export directory.

The implementation lives in the ``tools/node/`` package (see
``tools/node/__init__.py`` and ``tools/node/README.md``). This module only
re-exports the historical public names so that every existing entry point keeps
working unchanged:

- ``python3 -m tools.network_node ...``      (deploy/linux/start-orchestrator.sh)
- ``python3 tools/network_node.py ...``      (load test, installers)
- ``from tools import network_node; network_node.main(argv)``  (tools/cli/node/start.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    # Run as a script: sys.path[0] is tools/. Append the repository root at
    # index 1 (not 0) so that the root-level i18n/ directory never shadows
    # tools/i18n.py for modules imported from tools/.
    _repo_root = str(Path(__file__).resolve().parent.parent)
    if _repo_root not in sys.path:
        sys.path.insert(1, _repo_root)

# Kept as module attributes for callers/tests that monkeypatch e.g.
# ``network_node.socket.socket``; they patch the shared stdlib modules.
import importlib.util  # noqa: E402,F401
import socket  # noqa: E402,F401
import subprocess  # noqa: E402,F401

from tools.node.cli import build_arg_parser, main, parse_roles  # noqa: E402
from tools.node.config import NodeConfig, _peer_constraints, build_capacity_snapshot  # noqa: E402
from tools.node.constants import (  # noqa: E402
    DEFAULT_EXPORT_DIR,
    DEFAULT_PEER_HTTP_MAX_WORKERS,
    DEFAULT_PEER_SYNC_FANOUT,
    NETWORK_ROLES,
    RELEASE_CHANNELS,
    REQUEST_ROLES,
    TERMINAL_TASK_STATUSES,
)
from tools.node.daemon import NetworkNode  # noqa: E402
from tools.node.envelopes import enqueue_request_envelope, enqueue_task_envelope, ingest_content_blobs  # noqa: E402
from tools.node.identity import NodeIdentity  # noqa: E402
from tools.node.p2p_client import P2PClient  # noqa: E402
from tools.node.peer import PeerNetwork  # noqa: E402
from tools.node.queue_state import QueueState  # noqa: E402
from tools.node.reputation import ReputationStore  # noqa: E402
from tools.node.role_runtime import RoleRuntime  # noqa: E402
from tools.node.solana_bridge import SolanaBridge  # noqa: E402
from tools.node.util import (  # noqa: E402
    ATOMIC_WRITE_LOCK,
    append_jsonl,
    atomic_write_json,
    fragment_status_name,
    normalize_release_channel,
    optional_peer_id,
    read_json,
    reputation_value,
    safe_id,
    safe_path_id,
    sha256_bytes,
    sha256_json,
    stable_json,
    task_status,
    task_status_is_terminal,
    utc_now,
)
from tools.node_defaults import (  # noqa: E402
    DEFAULT_PEER_STALE_AFTER_S,
    DEFAULT_PEER_SYNC_INTERVAL_S,
    apply_nat_traversal_defaults,
)

__all__ = [
    # constants
    "ATOMIC_WRITE_LOCK",
    "DEFAULT_EXPORT_DIR",
    "DEFAULT_PEER_HTTP_MAX_WORKERS",
    "DEFAULT_PEER_STALE_AFTER_S",
    "DEFAULT_PEER_SYNC_FANOUT",
    "DEFAULT_PEER_SYNC_INTERVAL_S",
    "NETWORK_ROLES",
    "RELEASE_CHANNELS",
    "REQUEST_ROLES",
    "TERMINAL_TASK_STATUSES",
    # helpers
    "append_jsonl",
    "apply_nat_traversal_defaults",
    "atomic_write_json",
    "build_capacity_snapshot",
    "fragment_status_name",
    "ingest_content_blobs",
    "normalize_release_channel",
    "optional_peer_id",
    "read_json",
    "reputation_value",
    "safe_id",
    "safe_path_id",
    "sha256_bytes",
    "sha256_json",
    "stable_json",
    "task_status",
    "task_status_is_terminal",
    "utc_now",
    "_peer_constraints",
    # classes
    "NetworkNode",
    "NodeConfig",
    "NodeIdentity",
    "P2PClient",
    "PeerNetwork",
    "QueueState",
    "ReputationStore",
    "RoleRuntime",
    "SolanaBridge",
    # envelopes and CLI
    "enqueue_request_envelope",
    "enqueue_task_envelope",
    "build_arg_parser",
    "main",
    "parse_roles",
]


if __name__ == "__main__":
    raise SystemExit(main())
