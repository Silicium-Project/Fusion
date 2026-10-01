"""Small pure helpers shared by every node module: time, ids, JSON, hashing and files."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from tools.node.constants import RELEASE_CHANNELS, TERMINAL_TASK_STATUSES

# Serialises the final rename of atomic JSON writes (Windows needs retries on
# PermissionError when a reader holds the destination open).
ATOMIC_WRITE_LOCK = threading.Lock()


def utc_now() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def task_status(value: Any, default: str = "queued") -> str:
    """Normalised (lower-case) status, ``default`` when empty."""
    return str(value or default).strip().lower()


def task_status_is_terminal(value: Any) -> bool:
    """Whether a status is final (completed, failed, cancelled...)."""
    return task_status(value) in TERMINAL_TASK_STATUSES


def safe_id(value: str) -> str:
    """Restrict to ``[A-Za-z0-9_.:-]``; NOTE: an empty value yields a random id."""
    cleaned = "".join(ch if ch.isalnum() or ch in "_.:-" else "_" for ch in value.strip())
    return cleaned or uuid.uuid4().hex


def optional_peer_id(value: Any) -> str:
    """``safe_id`` of a non-empty value, else "" (never random)."""
    raw = str(value or "").strip()
    return safe_id(raw) if raw else ""


def normalize_release_channel(value: Any, *, default: str = "") -> str:
    """``dev``/``prod``; ``default`` when empty, "" when unknown."""
    channel = str(value or "").strip().lower()
    if not channel:
        return default
    return channel if channel in RELEASE_CHANNELS else ""


def safe_path_id(value: str) -> str:
    """Like ``safe_id`` but also safe as a file name (no ``:``)."""
    cleaned = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in value.strip())
    return cleaned or uuid.uuid4().hex


def stable_json(value: Any) -> str:
    """Canonical JSON (sorted keys, compact, ASCII) used for hashing and signing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    """Hex sha256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    """Hex sha256 of the canonical JSON of ``value``."""
    return sha256_bytes(stable_json(value).encode("utf-8"))


def fragment_status_name(fragment_account: dict[str, Any] | Any) -> str:
    """Status name of an on-chain fragment account (enum dict or plain value)."""
    status = fragment_account.get("status") if isinstance(fragment_account, dict) else getattr(fragment_account, "status", None)
    if isinstance(status, dict) and status:
        return str(next(iter(status.keys())))
    return str(status or "unknown")


def reputation_value(account: dict[str, Any] | Any, field: str) -> float:
    """Float field of an on-chain account (dict, object or BN-like), 0.0 on error."""
    value: Any
    if isinstance(account, dict):
        value = account.get(field)
    else:
        value = getattr(account, field, None)
    if value is None:
        return 0.0
    if hasattr(value, "toString"):
        try:
            value = value.toString()
        except Exception:
            pass
    try:
        return float(value)
    except Exception:
        return 0.0


def read_json(path: Path, default: Any) -> Any:
    """Parsed JSON file, or ``default`` when missing or invalid."""
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON through a temporary file and an atomic rename (with retries)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
    with ATOMIC_WRITE_LOCK:
        for attempt in range(20):
            try:
                tmp.replace(path)
                return
            except PermissionError:
                if attempt >= 19:
                    raise
                time.sleep(0.05 * float(attempt + 1))


def append_jsonl(path: Path, payload: Any) -> None:
    """Append one compact JSON line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n")
