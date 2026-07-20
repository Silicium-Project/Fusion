from __future__ import annotations

import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any


NETWORK_ROOT = Path(__file__).resolve().parents[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def ppm_to_png_bytes(ppm: bytes) -> bytes:
    offset = 0

    def read_token() -> bytes:
        nonlocal offset
        while offset < len(ppm) and ppm[offset] in b" \t\r\n":
            offset += 1
        if offset < len(ppm) and ppm[offset] == ord("#"):
            while offset < len(ppm) and ppm[offset] not in b"\r\n":
                offset += 1
            return read_token()
        start = offset
        while offset < len(ppm) and ppm[offset] not in b" \t\r\n":
            offset += 1
        return ppm[start:offset]

    magic = read_token()
    if magic != b"P6":
        raise ValueError("only binary P6 PPM files are supported")
    width = int(read_token())
    height = int(read_token())
    max_value = int(read_token())
    if max_value != 255:
        raise ValueError("only 8-bit PPM files are supported")
    while offset < len(ppm) and ppm[offset] in b" \t\r\n":
        offset += 1
    rgb = ppm[offset:]
    expected = width * height * 3
    if len(rgb) != expected:
        raise ValueError(f"invalid PPM payload size: expected {expected}, got {len(rgb)}")

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(rgb[y * stride : (y + 1) * stride])

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")
