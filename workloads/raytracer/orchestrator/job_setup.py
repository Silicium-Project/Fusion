"""Preparation of a job before any task is dispatched.

Creates the job directory layout, waits for workers to announce their roles
(network mode), resolves the in-flight limits and starts the local emitter
node that serves task inputs to the mesh.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from networked.networked_runtime import LocalNetworkEmitter
from workloads.raytracer.orchestrator.peers import resolve_in_flight_limit, wait_for_network_role


@dataclass(frozen=True)
class JobDirectories:
    """Directory layout of a job under `<output_root>/<job_id>/`."""

    job_dir: Path
    export_dir: Path
    input_dir: Path
    fragments_dir: Path
    reassembled_dir: Path


def resolve_job_dir(args: argparse.Namespace) -> tuple[str, Path]:
    """Return `(job_id, job_dir)`; refuse a non-empty directory unless --reuse-job-dir."""
    job_id = args.job_id or f"raytracer-auto-{int(time.time())}"
    output_root = Path(args.output_root).resolve()
    job_dir = output_root / job_id
    if job_dir.exists() and any(job_dir.iterdir()) and not args.reuse_job_dir:
        raise RuntimeError(
            f"job directory already exists: {job_dir}\n"
            "Use a new --job-id for a fresh run, or pass --reuse-job-dir intentionally."
        )
    return job_id, job_dir


def prepare_job_directories(args: argparse.Namespace, job_dir: Path) -> JobDirectories:
    """Create the job directories; also stores the resolved export dir back in `args`."""
    export_dir = Path(args.export_dir).resolve() if args.export_dir else (job_dir / "export").resolve()
    args.export_dir = str(export_dir)
    dirs = JobDirectories(
        job_dir=job_dir,
        export_dir=export_dir,
        input_dir=job_dir / "input",
        fragments_dir=job_dir / "fragments",
        reassembled_dir=job_dir / "reassembled",
    )
    dirs.input_dir.mkdir(parents=True, exist_ok=True)
    dirs.fragments_dir.mkdir(parents=True, exist_ok=True)
    dirs.reassembled_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    return dirs


def wait_for_worker_roles(args: argparse.Namespace, export_dir: Path) -> None:
    """Give workers a chance to announce the roles whose limit is automatic."""
    # The orchestrator peer snapshot is populated asynchronously.  Resolve
    # the pipeline limits only after workers have had a chance to announce
    # their roles; otherwise a cold start silently freezes the whole job at
    # the fallback capacity of one worker.
    roles_to_discover = []
    if int(args.max_compute_in_flight) <= 0:
        roles_to_discover.append("compute")
    if int(args.max_verify_in_flight) <= 0:
        roles_to_discover.append("verify")
    for role in roles_to_discover:
        try:
            wait_for_network_role(
                export_dir,
                args.network_node_id,
                role,
                timeout_s=max(1.0, min(60.0, float(args.result_timeout_s))),
            )
        except TimeoutError:
            # A single-role or temporarily empty network still gets the
            # safe fallback limit and can proceed locally.
            pass


def resolve_pipeline_limits(args: argparse.Namespace, export_dir: Path) -> tuple[int, int]:
    """Return the `(compute, verify)` in-flight limits."""
    compute_in_flight_limit = resolve_in_flight_limit(
        int(args.max_compute_in_flight),
        export_dir,
        args.network_node_id,
        "compute",
    )
    verify_in_flight_limit = resolve_in_flight_limit(
        int(args.max_verify_in_flight),
        export_dir,
        args.network_node_id,
        "verify",
    )
    return compute_in_flight_limit, verify_in_flight_limit


def start_emitter(
    args: argparse.Namespace,
    export_dir: Path,
    job_dir: Path,
) -> tuple[LocalNetworkEmitter | None, dict[str, Any]]:
    """Start the local emitter node in network mode; return it and the `network` progress block."""
    emitter_result: dict[str, Any] = {"enabled": False}
    emitter_node: LocalNetworkEmitter | None = None
    if args.node_mode == "network" and args.network_start_emitter:
        if not args.network_mesh_key:
            raise RuntimeError("--network-mesh-key is required for network mode content fetches")
        emitter_node = LocalNetworkEmitter(
            export_dir=export_dir,
            state_dir=job_dir / "_emitter_state",
            node_id=args.network_node_id,
            bind=args.network_bind,
            port=args.network_port,
            advertise_host=args.network_advertise_host,
            advertise_port=args.network_advertise_port,
            seed_peers=args.network_seed_peers,
            mesh_key=args.network_mesh_key,
        )
        emitter_node.start()
        emitter_result = {
            "enabled": True,
            "node_id": args.network_node_id,
            "public_url": emitter_node.public_url,
            "seed_peers": args.network_seed_peers,
        }
    return emitter_node, emitter_result
