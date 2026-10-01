"""Retry policy of the compute and verify stages.

A transient failure (see `failures.is_transient_task_failure`) is retried up to
`--max-compute-attempts` / `--max-verify-attempts`, preferably on another
worker. A timed-out attempt is remembered as "late": its result is still
accepted if it arrives while the retry runs.
"""
from __future__ import annotations

from typing import Any, Iterable

from workloads.raytracer.orchestrator.failures import is_transient_task_failure
from workloads.raytracer.orchestrator.job_state import JobState
from workloads.raytracer.orchestrator.peers import discovered_role_capacity
from workloads.raytracer.orchestrator.pipeline import RetryFragmentStage


def retry_excluded_peer_ids(
    current: Iterable[str],
    failed_node_id: str,
    available_capacity: int,
    error: str,
) -> tuple[list[str], bool]:
    """Prefer another worker while keeping at least one eligible peer."""  # i18n:ignore - developer documentation
    excluded = {str(value).strip() for value in current if str(value).strip()}
    failed = str(failed_node_id).strip()
    if failed:
        excluded.add(failed)

    no_alternative = bool(excluded) and max(1, int(available_capacity)) <= len(excluded)
    unknown_timeout = not failed and any(
        marker in str(error).lower()
        for marker in ("missing network result after deadline:", "timeout", "timed out")  # i18n:ignore - internal error classifiers
    )
    relaxed = no_alternative or (bool(excluded) and unknown_timeout)
    if relaxed:
        excluded.clear()
    return sorted(excluded), relaxed


def retry_transient_stage(
    state: JobState,
    context: dict[str, Any],
    token: dict[str, Any],
    *,
    stage: str,
    error: str,
    node_id: str = "",
) -> RetryFragmentStage | None:
    """Schedule a new attempt of `stage` for a transient failure, or return None to fail.

    Updates the fragment context (excluded peers, late task ids) and the
    progress file (`<stage>_retrying`).
    """
    args = state.args
    index = int(context["index"])
    attempt = int(token.get("attempt", 1))
    max_attempts = max(
        1,
        int(args.max_compute_attempts if stage == "compute" else args.max_verify_attempts),
    )
    if not is_transient_task_failure(error) or attempt >= max_attempts:
        return None
    excluded_key = f"{stage}_excluded_peer_ids"
    excluded, relaxed_exclusions = retry_excluded_peer_ids(
        context.get(excluded_key, []),
        node_id,
        discovered_role_capacity(
            state.export_dir,
            args.network_node_id,
            stage,
        ),
        error,
    )
    context[excluded_key] = excluded
    retry = {
        "stage": stage,
        "attempt": attempt,
        "next_attempt": attempt + 1,
        "task_id": str(token.get("task_id", "")),
        "failed_node_id": node_id,
        "relaxed_exclusions": relaxed_exclusions,
        "error": error,
    }
    retries = state.progress_fragments[index].setdefault("retries", [])
    if isinstance(retries, list):
        retries.append(retry)
    _remember_late_task(context, token, stage=stage, error=error)
    state.progress_fragments[index].update(
        {
            "status": f"{stage}_retrying",
            f"{stage}_attempt": attempt,
            f"{stage}_max_attempts": max_attempts,
            "last_transient_error": error,
        }
    )
    state.write_progress(f"{stage}_retrying")
    return RetryFragmentStage(error)


def _remember_late_task(context: dict[str, Any], token: dict[str, Any], *, stage: str, error: str) -> None:
    """Keep a timed-out task id so a late result can still complete the stage."""
    if "missing network result after deadline:" in error.lower():
        late_task_ids = context.setdefault(f"{stage}_late_task_ids", [])
        timed_out_task_id = str(token.get("task_id", ""))
        if isinstance(late_task_ids, list) and timed_out_task_id not in late_task_ids:
            late_task_ids.append(timed_out_task_id)
