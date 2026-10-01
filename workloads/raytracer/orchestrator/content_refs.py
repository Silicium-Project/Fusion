"""Content references for task inputs and outputs.

In `network` node mode, content is stored in / fetched from the mesh content
store of the emitter node; in the local modes it is a plain file reference
(`protocol: file`) inside the export directory.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from networked.networked_runtime import fetch_network_content, store_network_content, store_network_file
from workloads.common import p2p_file_path, sha256_bytes, sha256_file


def task_input_ref(args: argparse.Namespace, export_dir: Path, path: Path) -> dict[str, Any]:
    """Reference to an existing file (the scene) usable as a task input."""
    if args.node_mode == "network":
        return store_network_file(export_dir, path, args.network_node_id)
    return {"protocol": "file", "content_id": str(path), "hash": "sha256:" + sha256_file(path)}


def bytes_input_ref(args: argparse.Namespace, export_dir: Path, data: bytes) -> dict[str, Any]:
    """Reference to in-memory bytes (a task spec, a challenge), stored by content hash."""
    if args.node_mode == "network":
        return store_network_content(export_dir, data, args.network_node_id)
    digest = sha256_bytes(data)
    path = export_dir / "p2p" / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return {"protocol": "file", "content_id": str(path), "hash": "sha256:" + digest}


def read_ref_bytes(args: argparse.Namespace, export_dir: Path, ref: dict[str, Any]) -> bytes:
    """Read the bytes behind a reference (a worker's fragment output)."""
    if args.node_mode == "network":
        return fetch_network_content(export_dir, args.network_node_id, ref, args.network_mesh_key)
    return p2p_file_path(ref).read_bytes()
