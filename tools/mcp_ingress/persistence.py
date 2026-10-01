"""Small file helpers shared by the durable stores.

All JSON written by the server uses the same compact, ASCII-only encoding, and
every single-file record is replaced atomically (write ``<name>.tmp`` then
rename) so a concurrent reader never sees a half-written file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def utc_now() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def compact_json(payload: Any) -> str:
    """Encode ``payload`` as compact ASCII JSON (the on-disk/wire format)."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def tmp_path_for(path: Path) -> Path:
    """Return the sibling temporary path used for atomic replacement."""
    return path.with_suffix(path.suffix + ".tmp")


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` through a temporary file and a rename."""
    tmp_path = tmp_path_for(path)
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temporary file and a rename."""
    tmp_path = tmp_path_for(path)
    tmp_path.write_bytes(data)
    tmp_path.replace(path)


def append_line(path: Path, line: str) -> None:
    """Append ``line`` plus a newline to an NDJSON queue file."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
