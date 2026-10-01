"""Persistent queue cursors and the bounded processed-envelope idempotency set."""

from __future__ import annotations

from pathlib import Path

from tools.node.util import atomic_write_json, read_json, utc_now


class QueueState:
    """Per-queue read offsets and recently processed envelope keys."""

    def __init__(self, state_dir: Path) -> None:
        self._state_path = state_dir / "queue_state.json"
        self._processed_path = state_dir / "processed.json"
        self._offsets: dict[str, int] = read_json(self._state_path, {})
        self._processed: dict[str, str] = read_json(self._processed_path, {})

    def offset_for(self, path: Path) -> int:
        """Saved byte offset of a queue file."""
        return int(self._offsets.get(str(path), 0) or 0)

    def set_offset(self, path: Path, offset: int) -> None:
        """Remember the byte offset reached in a queue file."""
        self._offsets[str(path)] = max(0, int(offset))

    def seen(self, key: str) -> bool:
        """Whether an envelope key was already processed."""
        return key in self._processed

    def mark_seen(self, key: str) -> None:
        """Record an envelope key as processed."""
        self._processed[key] = utc_now()

    def save(self) -> None:
        """Persist offsets and the last 5000 processed keys."""
        atomic_write_json(self._state_path, self._offsets)
        # Keep the state bounded while preserving recent idempotency.
        items = list(self._processed.items())[-5000:]
        atomic_write_json(self._processed_path, dict(items))
