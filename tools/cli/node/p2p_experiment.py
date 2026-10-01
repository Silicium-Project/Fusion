"""Experimental Rust `p2p_node` launcher (`node start --experimental-p2p-node`).

The Rust p2p_node is retained as an explicitly opt-in experiment. It is not
the production node because it does not publish the integrated heartbeat and
peer registry consumed by the site (see `network_args.py` for the default
Python daemon).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from typing import Any, Mapping

from tools.cli.constants import REPO_ROOT


def _p2p_node_command() -> list[str]:
    """Return the `p2p_node` command: `SILICIUM_P2P_NODE_BIN` or the release build.

    Raises RuntimeError when neither exists.
    """
    override = os.environ.get("SILICIUM_P2P_NODE_BIN", "").strip()
    if override:
        return [override]

    binary_name = "p2p_node.exe" if os.name == "nt" else "p2p_node"
    release_binary = REPO_ROOT / "crates" / "p2p-node" / "target" / "release" / binary_name
    if release_binary.exists():
        return [str(release_binary)]

    # Never turn a node startup into an implicit production build. End-user
    # runtimes must execute a packaged binary, while developers can opt in by
    # setting SILICIUM_P2P_NODE_BIN explicitly.
    raise RuntimeError("p2p_node_binary_not_found:set_SILICIUM_P2P_NODE_BIN")  # i18n:ignore -- stable machine error code


def _build_p2p_node_env(args: argparse.Namespace, settings: Mapping[str, Any], node_id: str) -> dict[str, str]:
    """Return the process environment of `p2p_node` (inherits `os.environ`)."""
    env = os.environ.copy()
    export_dir = str(args.export_dir or settings["export_dir"])
    env["SILICIUM_APP_VERSION"] = str(args.app_version)
    env["SILICIUM_RELEASE_CHANNEL"] = str(args.release_channel)
    env["SILICIUM_RELEASE_BUILD"] = str(args.release_build)
    env["SILICIUM_NODE_ID"] = node_id
    env["SILICIUM_DATA_DIR"] = export_dir
    env["SILICIUM_DISPATCH_SEED"] = str(
        int.from_bytes(hashlib.sha256(node_id.encode("utf-8")).digest()[:8], "little")
    )
    if getattr(args, "seed_peers", ""):
        env["SILICIUM_BOOTSTRAP_PEERS"] = str(args.seed_peers)
    if getattr(args, "peer_http_port", 0):
        env["API_PORT"] = str(args.peer_http_port)
    return env


def _run_p2p_node(command: list[str], env: Mapping[str, str]) -> int:
    """Run `p2p_node` from the repository root and return its exit code."""
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=dict(env),
        check=False,
    )
    return int(completed.returncode)


def _p2p_node_args(args: argparse.Namespace, settings: Mapping[str, Any], node_id: str) -> list[str]:
    """Translate the `node start` options understood by `p2p_node`."""
    dispatch_seed = int.from_bytes(hashlib.sha256(node_id.encode("utf-8")).digest()[:8], "little")
    p2p_args = [
        "--data-dir",
        str(args.export_dir or settings["export_dir"]),
        "--dispatcher-seed",
        str(dispatch_seed),
    ]
    if getattr(args, "peer_http_port", 0):
        p2p_args.extend(["--api-port", str(args.peer_http_port)])
    if getattr(args, "seed_peers", ""):
        p2p_args.extend(["--bootstrap-peers", str(args.seed_peers)])
    if getattr(args, "gossip_enable", False):
        p2p_args.append("--enable-quic")
    return p2p_args
