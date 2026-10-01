"""Entry point of a raytracer job: `main()` ties the orchestrator steps together.

Order of operations (unchanged from the former monolithic script):
1. read the scene size, create the job directories, discover worker capacity;
2. split the scene with the native binary, start the emitter node;
3. run every fragment through compute then verify (`pipeline`);
4. reassemble the image and write the summary (`summary`).
The emitter node is always stopped, even when a stage raises.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from networked.networked_runtime import RpcTaskEventListener
from workloads.raytracer import native
from workloads.raytracer.orchestrator.cli import build_parser
from workloads.raytracer.orchestrator.compute_stage import launch_compute, poll_compute
from workloads.raytracer.orchestrator.content_refs import task_input_ref
from workloads.raytracer.orchestrator.job_setup import (
    prepare_job_directories,
    resolve_job_dir,
    resolve_pipeline_limits,
    start_emitter,
    wait_for_worker_roles,
)
from workloads.raytracer.orchestrator.job_state import JobState
from workloads.raytracer.orchestrator.native_steps import make_split
from workloads.raytracer.orchestrator.pipeline import run_bounded_fragment_pipeline
from workloads.raytracer.orchestrator.summary import finalize_job
from workloads.raytracer.orchestrator.verify_stage import finish_verify, launch_verify, poll_verify


def main(argv: list[str] | None = None) -> int:
    """Run one raytracer job; returns the process exit code (0, or 3 on a failed devnet trace)."""
    args = build_parser().parse_args(argv)
    job_started = time.perf_counter()
    scene_path = Path(args.scene).resolve()
    width, height = native.scene_resolution(scene_path)
    job_id, job_dir = resolve_job_dir(args)
    dirs = prepare_job_directories(args, job_dir)
    if args.node_mode == "network":
        wait_for_worker_roles(args, dirs.export_dir)
    compute_in_flight_limit, verify_in_flight_limit = resolve_pipeline_limits(args, dirs.export_dir)

    local_scene = dirs.input_dir / "scene.cfg"
    shutil.copy2(scene_path, local_scene)
    split_path = job_dir / "raytracer-split.json"
    summary_path = job_dir / "raytracer-summary.json"
    progress_path = job_dir / "raytracer-progress.json"
    split = make_split(args, local_scene, split_path)
    fragments = list(split.get("fragments", []))

    state = JobState(
        args=args,
        job_id=job_id,
        job_dir=job_dir,
        export_dir=dirs.export_dir,
        scene_path=scene_path,
        width=width,
        height=height,
        job_started=job_started,
        fragments_dir=dirs.fragments_dir,
        progress_path=progress_path,
        split=split,
        fragments=fragments,
        compute_in_flight_limit=compute_in_flight_limit,
        verify_in_flight_limit=verify_in_flight_limit,
        progress_fragments={
            int(fragment["fragment_index"]): {**fragment, "status": "planned"}
            for fragment in fragments
        },
    )
    state.emitter_node, state.emitter_result = start_emitter(args, dirs.export_dir, job_dir)

    try:
        state.scene_ref = task_input_ref(args, dirs.export_dir, local_scene)
        state.write_progress("split_ready")
        run_fragments(state)
        return finalize_job(state, dirs.reassembled_dir, summary_path)
    finally:
        if state.emitter_node is not None:
            state.emitter_node.stop()


def pipeline_contexts(job_id: str, fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-fragment mutable context passed to the stage callbacks."""
    contexts = []
    for fragment in fragments:
        index = int(fragment["fragment_index"])
        contexts.append(
            {
                "fragment": fragment,
                "index": index,
                "x_start": int(fragment["x_start"]),
                "x_end": int(fragment["x_end"]),
                "y_start": int(fragment["y_start"]),
                "y_end": int(fragment["y_end"]),
                "fragment_id": f"{job_id}-frag-{index:03d}",
            }
        )
    return contexts


def run_fragments(state: JobState) -> None:
    """Compute and verify every fragment within the in-flight limits."""
    # Task completion is signalled immediately by the scheduler's PUB
    # stream.  The next poll still reads the shared durable result, so a
    # missed ZeroMQ message can never lose work or alter correctness.
    event_listener = RpcTaskEventListener()
    try:
        run_bounded_fragment_pipeline(
            pipeline_contexts(state.job_id, state.fragments),
            max_compute_in_flight=state.compute_in_flight_limit,
            max_verify_in_flight=state.verify_in_flight_limit,
            launch_compute=lambda context: launch_compute(state, context),
            poll_compute=lambda context, token: poll_compute(state, context, token),
            launch_verify=lambda context, computed: launch_verify(state, context, computed),
            poll_verify=lambda context, computed, token: poll_verify(state, context, computed, token),
            finish_verify=lambda context, computed, token, verified: finish_verify(
                state, context, computed, token, verified
            ),
            idle=lambda: event_listener.wait(0.1),
        )
    finally:
        event_listener.close()
