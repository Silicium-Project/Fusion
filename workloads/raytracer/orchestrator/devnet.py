"""Optional Solana devnet trace of a finished job (`--devnet-trace`).

Runs `solana-layer/scripts/devnet_trace_fragments.ts` through `npx ts-node`
on the written summary and reports whether the on-chain artifact hash matches.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from workloads.common import default_solana_wallet_path, resolve_solana_wallet
from workloads.raytracer.orchestrator.constants import NETWORK_ROOT


def run_devnet_trace(args: argparse.Namespace, summary_path: Path) -> dict[str, Any]:
    """Submit the summary to devnet and return the `devnet_trace` summary block."""
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx_not_found")
    wallet_path = resolve_solana_wallet(args.solana_wallet)
    if not wallet_path.exists():
        raise RuntimeError(
            "solana_wallet_not_found:"
            + str(wallet_path)
            + " | Create one with: solana-keygen new -o "
            + str(default_solana_wallet_path())
            + " | Default path: "
            + str(default_solana_wallet_path())
        )
    trace_path = summary_path.with_name("devnet-trace.json")
    completed = subprocess.run(
        [npx, "ts-node", "scripts/devnet_trace_fragments.ts", str(summary_path)],
        cwd=str(NETWORK_ROOT / "solana-layer"),
        env=_trace_environment(args, trace_path, wallet_path),
        text=True,
        capture_output=True,
        timeout=args.devnet_trace_timeout_s,
        check=False,
    )
    trace = _read_trace(trace_path)
    reconciliation = trace.get("reconciliation") if isinstance(trace.get("reconciliation"), dict) else {}
    trace_ok = completed.returncode == 0 and reconciliation.get("hash_match") is True
    return {
        "enabled": True,
        "ok": trace_ok,
        "trace_path": str(trace_path),
        "returncode": completed.returncode,
        "artifact_hash_reconciled": reconciliation.get("hash_match") is True,
        "stdout_tail": completed.stdout[-4096:],
        "stderr_tail": completed.stderr[-4096:],
        "trace": trace,
    }


def _trace_environment(args: argparse.Namespace, trace_path: Path, wallet_path: Path) -> dict[str, str]:
    """Environment of the trace script: inherited plus wallet, RPC and program id."""
    env = os.environ.copy()
    env["SILICIUM_TRACE_RESULT_PATH"] = str(trace_path)
    env["ANCHOR_WALLET"] = str(wallet_path)
    env["SOLANA_RPC_URL"] = args.solana_rpc
    env["SOLANA_LAYER_PROGRAM_ID"] = args.solana_program_id
    env["SILICIUM_DEVNET_TX_DELAY_MS"] = str(args.devnet_tx_delay_ms)
    return env


def _read_trace(trace_path: Path) -> dict[str, Any]:
    """JSON object written by the trace script, or {} when absent."""
    trace: dict[str, Any] = {}
    if trace_path.exists():
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            trace = payload
    return trace
