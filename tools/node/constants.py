"""Node-wide constants: roles, task statuses, release channels and defaults."""

from __future__ import annotations

from pathlib import Path

# Directory of the legacy tools/ scripts (this package lives in tools/node/).
# Kept unresolved, like the former Path(__file__).with_name(...) default.
TOOLS_DIR = Path(__file__).parent.parent

DEFAULT_EXPORT_DIR = Path(".silicium/mcp/export")
NETWORK_ROLES = frozenset({"compute", "verify", "storage", "audit", "resource"})
REQUEST_ROLES = frozenset({"audit", "resource", "verify", "storage", "compute"})
DEFAULT_PEER_HTTP_MAX_WORKERS = 16
DEFAULT_PEER_SYNC_FANOUT = 8
TERMINAL_TASK_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "dead_lettered",
        "cancelled",
        "canceled",
        "expired",
        "finalized",
        "resolved",
    }
)
RELEASE_CHANNELS = frozenset({"dev", "prod"})
