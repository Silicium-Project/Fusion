"""Compatibility shim for Fusion/networked_runtime.py.

The authoritative implementation was refactored and relocated to
``Network/networked/networked_runtime.py`` as part of issue #67.
This module re-exports everything from that canonical location so that
legacy scripts that still import from here continue to work without
modification.

DO NOT add new code here.  All changes should go to:
    Network/networked/networked_runtime.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the Network package is on the path regardless of how this file is
# invoked (the Fusion root may or may not be on sys.path already).
_NETWORK_ROOT = Path(__file__).resolve().parent / "Network"
if str(_NETWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_NETWORK_ROOT))

from networked.networked_runtime import (  # noqa: E402, F401
    NETWORK_ROOT,
    MAX_INLINE_CONTENT_BLOB_TOTAL_BYTES,
    RpcTaskEventListener,
    LocalNetworkEmitter,
    attach_network_content_blobs,
    best_shared_ref,
    dispatch_task_to_scheduler,
    fetch_network_content,
    find_openssl,
    node_environment,
    peer_url,
    read_json,
    sha256_bytes,
    store_network_content,
    store_network_file,
    wait_for_result,
    write_json,
)

__all__ = [
    "NETWORK_ROOT",
    "MAX_INLINE_CONTENT_BLOB_TOTAL_BYTES",
    "RpcTaskEventListener",
    "LocalNetworkEmitter",
    "attach_network_content_blobs",
    "best_shared_ref",
    "dispatch_task_to_scheduler",
    "fetch_network_content",
    "find_openssl",
    "node_environment",
    "peer_url",
    "read_json",
    "sha256_bytes",
    "store_network_content",
    "store_network_file",
    "wait_for_result",
    "write_json",
]
