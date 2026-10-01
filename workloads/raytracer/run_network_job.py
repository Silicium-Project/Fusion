"""Orchestration of a full raytracer job on the network (compatibility entry point).

Called by the BackEnd (internal/silicium/runner.go): splits the scene, dispatches
fragments, challenges milestones, reassembles the image and writes the progress,
fragment previews and receipts that the BackEnd reads (docs/contracts/backend-files.md).

The implementation lives in the `workloads.raytracer.orchestrator` package (see
its `__init__.py` for the module layout). This file stays because:
- the workload manifest and `workloads/index.json` run it as a script, so it
  keeps the `sys.path` bootstrap below;
- the Windows installer byte-compiles it;
- tests and tools import names from it, so every former public name is
  re-exported here.
"""
from __future__ import annotations

import sys
from pathlib import Path

NETWORK_ROOT = Path(__file__).resolve().parents[2]
# Run as a script, only this file's folder is on sys.path: add the repository
# root so that `networked`, `tools` and `workloads` resolve.
sys.path.insert(0, str(NETWORK_ROOT))

from workloads.raytracer import native  # noqa: E402
from workloads.raytracer.native import pipeline_binary  # noqa: E402
from workloads.raytracer.orchestrator.cli import build_parser  # noqa: E402
from workloads.raytracer.orchestrator.constants import (  # noqa: E402
    DEFAULT_SOLANA_PROGRAM_ID,
    RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD,
    RAYTRACER_FRAGMENT_VERIFY_WORKLOAD,
    RAYTRACER_PERFORMANCE_SCHEMA,
)
from workloads.raytracer.orchestrator.content_refs import (  # noqa: E402
    bytes_input_ref,
    read_ref_bytes,
    task_input_ref,
)
from workloads.raytracer.orchestrator.devnet import run_devnet_trace  # noqa: E402
from workloads.raytracer.orchestrator.dispatch import (  # noqa: E402
    ensure_submission_success,
    submit_network_task,
)
from workloads.raytracer.orchestrator.failures import (  # noqa: E402
    ensure_raytracer_compute_contract,
    ensure_task_success,
    is_transient_task_failure,
    task_failure_details,
)
from workloads.raytracer.orchestrator.job import main  # noqa: E402
from workloads.raytracer.orchestrator.native_steps import make_split, reassemble_fragments  # noqa: E402
from workloads.raytracer.orchestrator.peers import (  # noqa: E402
    discovered_role_capacity,
    resolve_in_flight_limit,
    wait_for_network_role,
)
from workloads.raytracer.orchestrator.performance import (  # noqa: E402
    build_performance_summary,
    merge_compute_intervals,
)
from workloads.raytracer.orchestrator.pipeline import (  # noqa: E402
    RetryFragmentStage,
    run_bounded_fragment_pipeline,
)
from workloads.raytracer.orchestrator.polling import (  # noqa: E402
    poll_task_result_attempts,
    refresh_attempt_deadline,
)
from workloads.raytracer.orchestrator.receipts import (  # noqa: E402
    validate_compute_receipt,
    validate_receipt_attestation,
)
from workloads.raytracer.orchestrator.retries import retry_excluded_peer_ids  # noqa: E402

__all__ = [
    "DEFAULT_SOLANA_PROGRAM_ID",
    "NETWORK_ROOT",
    "RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD",
    "RAYTRACER_FRAGMENT_VERIFY_WORKLOAD",
    "RAYTRACER_PERFORMANCE_SCHEMA",
    "RetryFragmentStage",
    "build_parser",
    "build_performance_summary",
    "bytes_input_ref",
    "discovered_role_capacity",
    "ensure_raytracer_compute_contract",
    "ensure_submission_success",
    "ensure_task_success",
    "is_transient_task_failure",
    "main",
    "make_split",
    "merge_compute_intervals",
    "native",
    "pipeline_binary",
    "poll_task_result_attempts",
    "read_ref_bytes",
    "reassemble_fragments",
    "refresh_attempt_deadline",
    "resolve_in_flight_limit",
    "retry_excluded_peer_ids",
    "run_bounded_fragment_pipeline",
    "run_devnet_trace",
    "submit_network_task",
    "task_failure_details",
    "task_input_ref",
    "validate_compute_receipt",
    "validate_receipt_attestation",
    "wait_for_network_role",
]


if __name__ == "__main__":
    raise SystemExit(main())
