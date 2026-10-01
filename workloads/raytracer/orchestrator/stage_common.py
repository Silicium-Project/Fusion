"""Steps shared by the compute and verify stages.

Submitting a stage task, polling its attempt with the retry policy, and the
bookkeeping done when a result arrives. The stage-specific payloads and
result checks are in `compute_stage` and `verify_stage`.
"""
from __future__ import annotations

import os
from typing import Any

from workloads.common import clear_previous_result, submit_task
from workloads.raytracer.orchestrator.dispatch import ensure_submission_success, submit_network_task
from workloads.raytracer.orchestrator.failures import task_failure_details
from workloads.raytracer.orchestrator.job_state import JobState
from workloads.raytracer.orchestrator.performance import record_result_wait
from workloads.raytracer.orchestrator.pipeline import RetryFragmentStage
from workloads.raytracer.orchestrator.polling import poll_task_result_attempts, refresh_attempt_deadline
from workloads.raytracer.orchestrator.retries import retry_transient_stage


def submit_stage_task(state: JobState, payload: dict[str, Any], index: int, stage: str) -> None:
    """Submit a compute/verify task and record the submission.

    On a refused submission the fragment is marked `<stage>_dispatch_failed`
    and the RuntimeError propagates (it aborts the job).
    """
    emitter_node = state.emitter_node
    # The scheduler is the durable result sink.  An emitter launched
    # inside a backend/API container usually advertises 127.0.0.1 or
    # an ephemeral port; placing that URL in the envelope makes a
    # remote worker return the tile to *its own* localhost.  Keep a
    # direct return as an explicit opt-in for externally reachable
    # emitters only, and otherwise let the scheduler set its public
    # /results/dispatch endpoint during the claim.
    if emitter_node is not None and os.environ.get("SILICIUM_RAYTRACER_DIRECT_RESULT_RETURN", "") == "1":
        payload["origin_result_return_url"] = emitter_node.public_url.rstrip("/") + "/results/dispatch"
    task_id = payload["task_id"]
    clear_previous_result(state.export_dir, task_id)
    if state.args.node_mode == "network":
        submission = submit_network_task(state.args, state.export_dir, payload, emitter_node)
    else:
        submission = submit_task(state.export_dir, payload)
    state.submissions.append(submission)
    try:
        ensure_submission_success(submission)
    except RuntimeError as error:
        state.fail_fragment(index, f"{stage}_dispatch_failed", error)
        raise


def poll_stage_attempt(
    state: JobState,
    context: dict[str, Any],
    token: dict[str, Any],
    stage: str,
) -> tuple[str, dict[str, Any]] | RetryFragmentStage | None:
    """Poll the current attempt (and late predecessors) of `stage`.

    Returns `(resolved_task_id, result)`, None while waiting, or a
    RetryFragmentStage after a transient polling error (timeout, dead letter
    matching a transient marker). Other errors mark the fragment
    `<stage>_failed` and propagate.
    """
    index = int(context["index"])
    task_id = str(token["task_id"])
    try:
        deadline = refresh_attempt_deadline(state.export_dir, token, float(state.args.node_timeout_s))
        return poll_task_result_attempts(
            state.export_dir,
            task_id,
            list(context.get(f"{stage}_late_task_ids", [])),
            deadline,
        )
    except Exception as error:
        retry = retry_transient_stage(state, context, token, stage=stage, error=str(error))
        if retry is not None:
            return retry
        state.fail_fragment(index, f"{stage}_failed", error)
        raise


def register_stage_result(
    state: JobState,
    token: dict[str, Any],
    stage: str,
    resolved_task_id: str,
    result: dict[str, Any],
) -> None:
    """Bookkeeping when a result arrives: resolved id, wait time and node run."""
    token["resolved_task_id"] = resolved_task_id
    record_result_wait(token)
    state.record_node_run(stage, resolved_task_id, result)


def retry_failed_result(
    state: JobState,
    context: dict[str, Any],
    token: dict[str, Any],
    stage: str,
    result: dict[str, Any],
) -> RetryFragmentStage | None:
    """Retry when the worker reported a transient failure; None means "carry on".

    A non-transient failure also returns None: the caller's success check then
    raises with the worker's error.
    """
    if result.get("success", True) is False:
        task_error, failed_node_id = task_failure_details(result)
        return retry_transient_stage(
            state,
            context,
            token,
            stage=stage,
            error=task_error,
            node_id=failed_node_id,
        )
    return None
