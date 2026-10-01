"""Command-line interface of the raytracer job orchestrator.

The BackEnd (internal/silicium/runner.go) and the workload manifest call the
orchestrator with these flags; their names and defaults are part of the
contract and must not change. Several defaults come from environment
variables read when the parser is built.
"""
from __future__ import annotations

import argparse
import os

from workloads.raytracer.orchestrator.constants import DEFAULT_SOLANA_PROGRAM_ID, NETWORK_ROOT


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of `run_network_job.py`."""
    parser = argparse.ArgumentParser(description="Run raytracer as a Silicium network workload.")
    _add_job_arguments(parser)
    _add_split_arguments(parser)
    _add_pipeline_arguments(parser)
    _add_network_arguments(parser)
    _add_solana_arguments(parser)
    return parser


def _add_job_arguments(parser: argparse.ArgumentParser) -> None:
    """Scene, job identity, directories and node timeouts."""
    parser.add_argument("scene")
    parser.add_argument("--job-id", "--task-id", dest="job_id", default="")
    parser.add_argument("--output-root", default=str(NETWORK_ROOT / ".silicium" / "jobs" / "raytracer"))
    parser.add_argument("--export-dir", default="")
    parser.add_argument("--reuse-job-dir", action="store_true")
    parser.add_argument("--priority", default="high", choices=["low", "normal", "high", "urgent"])
    parser.add_argument("--p2p-gateway", default="http://127.0.0.1:5001")
    parser.add_argument("--node-mode", default="auto", choices=["auto", "cli", "inline", "network"])
    parser.add_argument("--node-sweeps", type=int, default=30)
    parser.add_argument("--result-timeout-s", type=float, default=300.0)
    parser.add_argument("--node-timeout-s", type=float, default=300.0)


def _add_split_arguments(parser: argparse.ArgumentParser) -> None:
    """Options forwarded to `silicium-raytracer split`."""
    parser.add_argument("--target-pixels", type=int, default=120_000)
    parser.add_argument("--max-fragments", type=int, default=32)
    parser.add_argument("--fragments", type=int, default=0, help="Optional manual override; 0 keeps automatic split.")


def _add_pipeline_arguments(parser: argparse.ArgumentParser) -> None:
    """Concurrency, retry and verification-batch limits of the fragment pipeline."""
    parser.add_argument(
        "--max-compute-in-flight",
        type=int,
        default=int(os.environ.get("SILICIUM_RAYTRACER_MAX_COMPUTE_IN_FLIGHT", "0")),
        help="Maximum concurrent fragment computes; 0 follows discovered compute capacity.",
    )
    parser.add_argument(
        "--max-verify-in-flight",
        type=int,
        default=int(os.environ.get("SILICIUM_RAYTRACER_MAX_VERIFY_IN_FLIGHT", "0")),
        help="Maximum concurrent fragment verifications; 0 follows discovered verify capacity.",
    )
    parser.add_argument(
        "--max-compute-attempts",
        type=int,
        default=int(os.environ.get("SILICIUM_RAYTRACER_MAX_COMPUTE_ATTEMPTS", "3")),
        help="Maximum dispatch attempts for transient compute failures.",
    )
    parser.add_argument(
        "--max-verify-attempts",
        type=int,
        default=int(os.environ.get("SILICIUM_RAYTRACER_MAX_VERIFY_ATTEMPTS", "3")),
        help="Maximum dispatch attempts for transient verification failures.",
    )
    parser.add_argument(
        "--verification-batch-rows",
        type=int,
        default=int(os.environ.get("SILICIUM_RAYTRACER_VERIFY_BATCH_ROWS", "20")),
        help="Rows committed by each verification milestone; one milestone is challenged after compute.",
    )


def _add_network_arguments(parser: argparse.ArgumentParser) -> None:
    """Local emitter node, mesh membership and worker reputation thresholds."""
    parser.add_argument("--network-node-id", default="raytracer-emitter")
    parser.add_argument("--network-bind", default="0.0.0.0")
    parser.add_argument("--network-port", type=int, default=0, help="Emitter HTTP port; 0 selects a free local port.")
    parser.add_argument("--network-advertise-host", default="127.0.0.1")
    parser.add_argument("--network-advertise-port", type=int, default=0, help="Advertised emitter port; 0 uses the bound port.")
    parser.add_argument("--network-seed-peers", default="")
    parser.add_argument("--network-mesh-key", default=os.environ.get("SILICIUM_MESH_KEY", "demo-mesh"))
    parser.add_argument("--network-start-emitter", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-compute-reputation", type=float, default=float(os.environ.get("SILICIUM_MIN_COMPUTE_REPUTATION", "0")))
    parser.add_argument("--min-verify-reputation", type=float, default=float(os.environ.get("SILICIUM_MIN_VERIFY_REPUTATION", "0")))


def _add_solana_arguments(parser: argparse.ArgumentParser) -> None:
    """Optional devnet trace of the verified fragments."""
    parser.add_argument("--solana-enable", action="store_true")
    parser.add_argument("--devnet-trace", action="store_true")
    parser.add_argument("--devnet-trace-timeout-s", type=float, default=420.0)
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.environ.get("ANCHOR_WALLET", "")))
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument("--solana-program-id", default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", DEFAULT_SOLANA_PROGRAM_ID))
    parser.add_argument("--devnet-tx-delay-ms", type=int, default=int(os.environ.get("SILICIUM_DEVNET_TX_DELAY_MS", "1200")))
