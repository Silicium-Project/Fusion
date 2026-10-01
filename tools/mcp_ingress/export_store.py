"""Read-only access to the worker export directory, by resource URI.

A worker started with ``--mcp-readonly --mcp-export-dir <dir>`` (and the
network node) write JSON files into the export directory; this module maps
each ``resources://silicium/...`` URI to its file. When a snapshot store is
configured, every successful read is captured and served back as a fallback
once the live file disappears.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .constants import (
    RESOURCE_LOGS_PREFIX,
    RESOURCE_NODE_HEARTBEAT_PREFIX,
    RESOURCE_NODE_METRICS_PREFIX,
    RESOURCE_NODE_PEERS_PREFIX,
    RESOURCE_REPORTS_RECENT,
    RESOURCE_REQUEST_PREFIX,
    RESOURCE_RESULT_PREFIX,
    RESOURCE_STATUS_CURRENT,
    RESOURCE_TASK_PREFIX,
)
from .validation import sanitize_task_id

if TYPE_CHECKING:
    from .snapshot_store import McpSnapshotStore

# Fixed URIs -> file name inside the export directory.
_FIXED_RESOURCES = {
    RESOURCE_STATUS_CURRENT: "status.current.json",
    RESOURCE_REPORTS_RECENT: "reports.recent.json",
}

# Parameterised URIs: (prefix, error raised when the id is empty, path builder).
# The id after the prefix is sanitised before it is used in a file name.
_PREFIXED_RESOURCES: tuple[tuple[str, str, Callable[[Path, str], Path]], ...] = (
    (RESOURCE_RESULT_PREFIX, "missing_task_id", lambda d, i: d / f"result.{i}.json"),
    (RESOURCE_LOGS_PREFIX, "missing_task_id", lambda d, i: d / f"logs.{i}.json"),
    (RESOURCE_TASK_PREFIX, "missing_task_id", lambda d, i: d / "tasks" / f"{i}.json"),
    (RESOURCE_REQUEST_PREFIX, "missing_request_id", lambda d, i: d / "requests" / f"{i}.json"),
    (RESOURCE_NODE_HEARTBEAT_PREFIX, "missing_node_id", lambda d, i: d / f"node.{i}.heartbeat.json"),
    (RESOURCE_NODE_METRICS_PREFIX, "missing_node_id", lambda d, i: d / f"node.{i}.metrics.json"),
    (RESOURCE_NODE_PEERS_PREFIX, "missing_node_id", lambda d, i: d / f"node.{i}.peers.json"),
)


class McpExportStore:
    """Resolves resource URIs to export files, with optional snapshot fallback."""

    def __init__(self, export_dir: Path, snapshot_store: "McpSnapshotStore | None" = None) -> None:
        self._export_dir = export_dir
        self._snapshot_store = snapshot_store

    @property
    def export_dir(self) -> Path:
        """The worker export directory this store reads from."""
        return self._export_dir

    def read_resource(self, uri: str) -> str:
        """Return the JSON text of ``uri``.

        Raises ``FileNotFoundError`` when neither the live file nor a snapshot
        exists, and ``ValueError("unsupported_resource")`` for unknown URIs.
        """
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
        return self._read_text(self._resource_path(uri))

    def _resource_path(self, uri: str) -> Path:
        fixed = _FIXED_RESOURCES.get(uri)
        if fixed is not None:
            return self._export_dir / fixed
        for prefix, missing_error, build_path in _PREFIXED_RESOURCES:
            if uri.startswith(prefix):
                resource_id = sanitize_task_id(uri[len(prefix) :])
                if not resource_id:
                    raise FileNotFoundError(missing_error)
                return build_path(self._export_dir, resource_id)
        raise ValueError("unsupported_resource")

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")
