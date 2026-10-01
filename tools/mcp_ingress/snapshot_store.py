"""Persistent snapshots of resources served by the MCP server.

Enabled with ``--snapshot-dir``. Each successful resource read is stored as
``<created_ms>-<rand>.json`` and indexed in ``snapshot.index.json``; when the
live export file disappears (worker restart, cleanup) the latest snapshot of
the URI is served instead. Retention caps the number of files and the total
size, dropping the oldest snapshots first. Bundles allow moving snapshots
between servers (``/snapshots/export`` and ``/snapshots/import``).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .persistence import atomic_write_bytes, atomic_write_text, compact_json, utc_now


class McpSnapshotStore:
    """Captures resource bodies on disk with file-count and byte-size retention."""

    def __init__(self, snapshot_dir: Path, max_files: int, max_total_bytes: int) -> None:
        self._snapshot_dir = snapshot_dir
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._snapshot_dir / "snapshot.index.json"
        # 0 disables the corresponding cap.
        self._max_files = max(0, int(max_files))
        self._max_total_bytes = max(0, int(max_total_bytes))
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._load_index()

    @property
    def snapshot_dir(self) -> Path:
        """Directory holding snapshot files and the index."""
        return self._snapshot_dir

    def capture(self, uri: str, text: str) -> None:
        """Store ``text`` as the newest snapshot of ``uri`` and apply retention."""
        created_ms = int(time.time() * 1000)
        entry_id = f"{created_ms}-{uuid.uuid4().hex[:8]}"
        filename = f"{entry_id}.json"
        payload = text.encode("utf-8")
        atomic_write_bytes(self._snapshot_dir / filename, payload)
        entry = {
            "id": entry_id,
            "uri": uri,
            "created_utc": utc_now(),
            "created_ms": created_ms,
            "size": len(payload),
            "file": filename,
        }
        with self._lock:
            self._entries.append(entry)
            self._apply_retention_locked()
            self._save_index_locked()

    def read_latest(self, uri: str) -> str:
        """Return the newest snapshot of ``uri`` or raise ``FileNotFoundError``."""
        with self._lock:
            for entry in reversed(self._entries):
                if str(entry.get("uri", "")) != uri:
                    continue
                p = self._snapshot_dir / str(entry.get("file", ""))
                if p.exists():
                    return p.read_text(encoding="utf-8")
            raise FileNotFoundError("snapshot_not_found")

    def list_entries(self) -> list[dict[str, Any]]:
        """Return the public view of the index (oldest first)."""
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
        """Return every readable snapshot with its text, for ``/snapshots/export``."""
        exported: list[dict[str, Any]] = []
        for entry in self.list_entries():
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
        return {"schema_version": 1, "exported_utc": utc_now(), "entries": exported}

    def import_bundle(self, payload: Any) -> int:
        """Capture every valid entry of an exported bundle; returns the count."""
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
            # Imported snapshots get fresh ids and timestamps.
            self.capture(uri, text)
            imported += 1
        return imported

    def _load_index(self) -> None:
        with self._lock:
            entries: list[dict[str, Any]] = []
            if self._index_path.exists():
                try:
                    entries = self._read_index_entries()
                except Exception:
                    # A corrupt index is discarded rather than blocking startup.
                    entries = []
            self._entries = [e for e in entries if (self._snapshot_dir / str(e.get("file", ""))).exists()]
            self._entries.sort(key=lambda e: int(e.get("created_ms", 0)))
            self._apply_retention_locked()
            self._save_index_locked()

    def _read_index_entries(self) -> list[dict[str, Any]]:
        data = json.loads(self._index_path.read_text(encoding="utf-8"))
        raw_entries = data.get("entries", []) if isinstance(data, dict) else []
        if not isinstance(raw_entries, list):
            return []
        entries: list[dict[str, Any]] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            entry = _normalize_index_entry(item)
            if entry is not None:
                entries.append(entry)
        return entries

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
        atomic_write_text(self._index_path, compact_json(data))


def _normalize_index_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    """Rebuild one index entry, filling defaults; None when file/uri is missing.

    ``int()`` conversions may raise; the caller then discards the whole index.
    """
    file_name = str(item.get("file", ""))
    uri = str(item.get("uri", ""))
    if not file_name or not uri:
        return None
    size = int(item.get("size", 0) or 0)
    created_ms = int(item.get("created_ms", 0) or 0)
    created_utc = str(item.get("created_utc", ""))
    entry_id = str(item.get("id", ""))
    return {
        "id": entry_id or f"{created_ms}-{file_name}",
        "uri": uri,
        "created_utc": created_utc or utc_now(),
        "created_ms": created_ms,
        "size": size,
        "file": file_name,
    }
