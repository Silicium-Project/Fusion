"""Mutable state of one running job and the progress file built from it.

`JobState` replaces the variables that the former monolithic `main()` shared
with its nested stage closures. The stage modules receive it explicitly. The
progress file (`raytracer-progress.json`) is rewritten after every state
change; the BackEnd polls it (docs/contracts/backend-files.md), so its field
names are a contract.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from networked.networked_runtime import LocalNetworkEmitter
from workloads.common import write_json
from workloads.raytracer.orchestrator.performance import build_performance_summary


@dataclass
class JobState:
    """Everything the fragment stages read or update while a job runs."""

    args: argparse.Namespace
    job_id: str
    job_dir: Path
    export_dir: Path
    # Scene as given on the command line (reported in progress/summary);
    # the tasks use the copy in `<job_dir>/input/scene.cfg`.
    scene_path: Path
    width: int
    height: int
    # time.perf_counter() at job start, for the job-level performance summary.
    job_started: float
    fragments_dir: Path
    progress_path: Path
    split: dict[str, Any]
    fragments: list[dict[str, Any]]
    compute_in_flight_limit: int
    verify_in_flight_limit: int
    # Per-fragment progress entries keyed by fragment_index; they become the
    # `fragments` list of the progress and summary files.
    progress_fragments: dict[int, dict[str, Any]]
    submissions: list[dict[str, Any]] = field(default_factory=list)
    node_runs: list[dict[str, Any]] = field(default_factory=list)
    performance_records: list[dict[str, Any]] = field(default_factory=list)
    emitter_result: dict[str, Any] = field(default_factory=lambda: {"enabled": False})
    emitter_node: LocalNetworkEmitter | None = None
    scene_ref: dict[str, Any] = field(default_factory=dict)
    # (x_start, y_start, ppm path) of each computed fragment, in completion order.
    fragment_files: list[tuple[int, int, Path]] = field(default_factory=list)

    def performance_summary(self) -> dict[str, Any]:
        """Job-level performance so far (wall time measured from job start)."""
        return build_performance_summary(
            self.performance_records,
            (time.perf_counter() - self.job_started) * 1000.0,
        )

    def sorted_progress_fragments(self) -> list[dict[str, Any]]:
        """Progress entries ordered by fragment index."""
        return [self.progress_fragments[index] for index in sorted(self.progress_fragments)]

    def write_progress(self, stage: str, success: bool = False) -> None:
        """Rewrite the progress file for `stage`."""
        write_json(
            self.progress_path,
            {
                "schema_version": 1,
                "mode": "raytracer_network_job",
                "progress": True,
                "stage": stage,
                "success": success,
                "job_id": self.job_id,
                "job_dir": str(self.job_dir),
                "export_dir": str(self.export_dir),
                "scene": str(self.scene_path),
                "image": {"width": self.width, "height": self.height},
                "split_policy": self.split.get("split_policy", {}),
                "fragment_count": len(self.fragments),
                "pipeline_limits": {
                    "compute": self.compute_in_flight_limit,
                    "verify": self.verify_in_flight_limit,
                },
                "fragments": self.sorted_progress_fragments(),
                "submissions": self.submissions,
                "node_runs": self.node_runs,
                "performance": self.performance_summary(),
                "network": self.emitter_result,
                "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    def fail_fragment(self, index: int, status: str, error: BaseException) -> None:
        """Mark a fragment failed with `status` and publish it as the progress stage."""
        self.progress_fragments[index].update({"status": status, "error": str(error)})
        self.write_progress(status)

    def record_node_run(self, role: str, task_id: str, result: dict[str, Any]) -> None:
        """Append the `node_runs` entry for a task whose result arrived."""
        self.node_runs.append(
            {
                "role": role,
                "mode": "network",
                "target_task_id": task_id,
                "target_result_ready": True,
                "handled_by": result.get("node_id", ""),
            }
        )

    def record_performance(self, record: dict[str, Any]) -> None:
        """Keep a task performance record and attach it to the latest node run."""
        self.performance_records.append(record)
        if self.node_runs:
            self.node_runs[-1]["performance"] = record
