"""Helpers shared by workloads: hashing, stable JSON, performance figures,
task submission to an export dir, P2P refs, Solana wallet."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


NETWORK_ROOT = Path(__file__).resolve().parents[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return sha256_bytes(stable_json(value).encode("utf-8"))


RAYTRACER_PERFORMANCE_SCHEMA = "silicium.raytracer-performance.v1"


def performance_duration(value: Any) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(duration, 3) if math.isfinite(duration) and duration >= 0 else 0.0


def performance_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(max(0.0, numerator) / denominator, 4)


def last_json_object(text: str) -> dict[str, Any]:
    """Extract the last JSON object from a renderer's stdout."""
    decoder = json.JSONDecoder()
    best: dict[str, Any] = {}
    best_end = -1
    for index in range(len(text)):
        if text[index] != "{":
            continue
        try:
            candidate, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        absolute_end = index + end
        if isinstance(candidate, dict) and absolute_end > best_end:
            best = candidate
            best_end = absolute_end
    return best


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True), encoding="utf-8")


def submit_task(export_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    sys.path.insert(0, str(NETWORK_ROOT))
    from tools.mcp_server import McpTaskStore

    return McpTaskStore(export_dir).submit(payload)


def clear_previous_result(export_dir: Path, task_id: str) -> None:
    for prefix in ("result", "logs"):
        path = export_dir / f"{prefix}.{task_id}.json"
        if path.exists():
            path.unlink()


def output_ref_from_compute(result: dict[str, Any]) -> dict[str, Any]:
    ref = result.get("output_ref") or result.get("proof_ref")
    if not isinstance(ref, dict):
        raise ValueError("compute result does not contain output_ref")
    return ref


def result_hash_from_compute(result: dict[str, Any]) -> str:
    raw = str(result.get("result_hash") or "")
    if not raw:
        raise ValueError("compute result does not contain result_hash")
    return raw.removeprefix("sha256:")


def p2p_file_path(ref: dict[str, Any]) -> Path:
    if ref.get("protocol") != "file":
        raise ValueError(f"file protocol output_ref expected, got {ref.get('protocol')}")
    content_id = str(ref.get("content_id") or "")
    if not content_id:
        raise ValueError("missing output_ref content_id")
    return Path(content_id)


def default_solana_wallet_path() -> Path:
    return NETWORK_ROOT / ".silicium" / "solana" / "id.json"


def resolve_solana_wallet(raw: str) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return default_solana_wallet_path()
