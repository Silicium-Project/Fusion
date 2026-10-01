"""Verify stage of a fragment: challenge one committed milestone on another worker.

After a tile is computed, one of its milestones is picked at random (with a
fresh nonce) and sent to a verifier, which re-renders only those rows. The
fragment is accepted when the verifier's signed attestation of the compute
receipt is valid and positive.
"""
from __future__ import annotations

import json
import secrets
import time
from typing import Any

from networked.networked_runtime import best_shared_ref
from workloads.common import performance_duration
from workloads.raytracer.orchestrator.constants import (
    RAYTRACER_FASTPATH_FEATURE,
    RAYTRACER_FRAGMENT_VERIFY_WORKLOAD,
)
from workloads.raytracer.orchestrator.content_refs import bytes_input_ref
from workloads.raytracer.orchestrator.failures import ensure_task_success
from workloads.raytracer.orchestrator.job_state import JobState
from workloads.raytracer.orchestrator.peers import discovered_role_capacity
from workloads.raytracer.orchestrator.performance import orchestration_performance_record
from workloads.raytracer.orchestrator.pipeline import RetryFragmentStage
from workloads.raytracer.orchestrator.receipts import validate_compute_receipt, validate_receipt_attestation
from workloads.raytracer.orchestrator.stage_common import (
    poll_stage_attempt,
    register_stage_result,
    retry_failed_result,
    submit_stage_task,
)


def launch_verify(state: JobState, context: dict[str, Any], computed: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a new verify attempt (with a fresh challenge) and return its polling token."""
    args = state.args
    index = int(context["index"])
    fragment_id = str(context["fragment_id"])
    attempt = int(context.get("verify_attempt", 0)) + 1
    context["verify_attempt"] = attempt
    verify_id = (
        f"{fragment_id}-verify"
        if attempt == 1
        else f"{fragment_id}-verify-retry-{attempt:02d}"
    )
    challenge = _build_challenge(context, computed)
    # Every attempt has its own challenge; a late result is checked against
    # the challenge of the attempt that produced it.
    verify_challenges = context.setdefault("verify_challenges", {})
    if isinstance(verify_challenges, dict):
        verify_challenges[verify_id] = challenge
    challenge_ref = bytes_input_ref(
        args,
        state.export_dir,
        json.dumps(challenge, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )
    excluded_peer_ids = _verify_excluded_peer_ids(state, context, computed)
    dispatch_started = time.perf_counter()
    verify_payload = _verify_payload(state, context, computed, verify_id, challenge, challenge_ref, excluded_peer_ids)
    submit_stage_task(state, verify_payload, index, "verify")
    dispatch_ms = performance_duration((time.perf_counter() - dispatch_started) * 1000.0)
    state.progress_fragments[index]["status"] = "queued_verify"
    state.write_progress("verify_queued")
    return {
        "task_id": verify_id,
        "attempt": attempt,
        "challenge": challenge,
        "queue_deadline": time.monotonic() + args.result_timeout_s,
        "dispatch_ms": dispatch_ms,
        "result_wait_started": time.perf_counter(),
    }


def _build_challenge(context: dict[str, Any], computed: dict[str, Any]) -> dict[str, Any]:
    """Pick one committed milestone at random and wrap it with a fresh nonce."""
    expected_milestones = computed["expected_milestones"]
    challenged_milestone = secrets.choice(expected_milestones["milestones"])
    return {
        "schema_version": 1,
        "strategy": expected_milestones["strategy"],
        "challenge_nonce": secrets.token_hex(16),
        "source_task_id": str(computed["compute_task_id"]),
        "fragment_index": int(context["index"]),
        "fragment_rows": expected_milestones["fragment_rows"],
        "milestone_count": expected_milestones["milestone_count"],
        "commitment_hash": expected_milestones["commitment_hash"],
        "milestone": challenged_milestone,
    }


def _verify_excluded_peer_ids(state: JobState, context: dict[str, Any], computed: dict[str, Any]) -> set[str]:
    """Peers that must not verify this fragment (previous failures, the compute node)."""
    excluded = {
        str(value)
        for value in context.get("verify_excluded_peer_ids", [])
        if str(value).strip()
    }
    # Preserve independent verification whenever another verifier is
    # available. In a one-node network, excluding the compute node
    # leaves every verify task permanently unclaimable.
    if discovered_role_capacity(
        state.export_dir,
        state.args.network_node_id,
        "verify",
    ) > 1:
        excluded.add(str(computed["compute_result"].get("node_id", "")))
    return excluded


def _verify_payload(
    state: JobState,
    context: dict[str, Any],
    computed: dict[str, Any],
    verify_id: str,
    challenge: dict[str, Any],
    challenge_ref: dict[str, Any],
    excluded_peer_ids: set[str],
) -> dict[str, Any]:
    """Scheduler envelope of a verify task."""
    args = state.args
    compute_result = computed["compute_result"]
    expected_milestones = computed["expected_milestones"]
    expected_hash = "sha256:" + str(challenge["milestone"]["pixel_sha256"])
    return {
        "task_id": verify_id,
        "required_roles": ["verify"],
        "required_features": [RAYTRACER_FASTPATH_FEATURE],
        "priority": args.priority,
        "p2p_ref": challenge_ref,
        "expected_hash": expected_hash,
        "excluded_peer_ids": sorted(excluded_peer_ids - {""}),
        "scene_p2p_ref": state.scene_ref,
        "task": {
            "kind": "verify",
            "workload": RAYTRACER_FRAGMENT_VERIFY_WORKLOAD,
            "required_features": [RAYTRACER_FASTPATH_FEATURE],
            "inline_input": challenge,
            "expected_hash": expected_hash,
            "verification_mode": expected_milestones["strategy"],
            "max_sample_rows": max(1, int(args.verification_batch_rows)),
            "scene_p2p_ref": state.scene_ref,
            "source_task_id": str(computed["compute_task_id"]),
            "source_node_id": str(compute_result.get("node_id", "")),
            "source_output_ref": best_shared_ref(computed["output_ref"]),
            "fragment_index": int(context["index"]),
            "fragment_count": len(state.fragments),
            "x_start": int(context["x_start"]),
            "x_end": int(context["x_end"]),
            "y_start": int(context["y_start"]),
            "y_end": int(context["y_end"]),
            "timeout_s": int(args.node_timeout_s),
            "root_job_id": state.job_id,
            "compute_receipt_hash": str(computed["compute_receipt"]["receipt_hash"]),
        },
    }


def poll_verify(
    state: JobState,
    context: dict[str, Any],
    _computed: dict[str, Any],
    token: dict[str, Any],
) -> dict[str, Any] | RetryFragmentStage | None:
    """Poll a verify attempt; returns the verify result, None while waiting, or a RetryFragmentStage."""
    resolved = poll_stage_attempt(state, context, token, "verify")
    if resolved is None or isinstance(resolved, RetryFragmentStage):
        return resolved
    resolved_verify_id, verify_result = resolved
    register_stage_result(state, token, "verify", resolved_verify_id, verify_result)
    verify_challenges = context.get("verify_challenges", {})
    if isinstance(verify_challenges, dict):
        token["resolved_challenge"] = verify_challenges.get(resolved_verify_id, token["challenge"])
    retry = retry_failed_result(state, context, token, "verify", verify_result)
    if retry is not None:
        return retry
    return verify_result


def finish_verify(
    state: JobState,
    context: dict[str, Any],
    computed: dict[str, Any],
    token: dict[str, Any],
    verify_result: dict[str, Any],
) -> None:
    """Check the verify result and its receipts, record them, and fail the job on rejection."""
    index = int(context["index"])
    fragment_id = str(context["fragment_id"])
    verify_id = str(token.get("resolved_task_id") or token["task_id"])
    try:
        ensure_task_success(verify_result, verify_id)
    except RuntimeError as error:
        state.fail_fragment(index, "verify_failed", error)
        raise
    verified = bool(verify_result.get("choice", verify_result.get("verified", False)))
    compute_receipt = computed["compute_receipt"]
    # Unlike the compute checks, receipt errors here propagate without
    # marking the fragment failed in the progress file (kept as before).
    receipt_attestation = validate_receipt_attestation(
        verify_result,
        str(compute_receipt["receipt_hash"]),
        verify_id,
    )
    verify_receipt = validate_compute_receipt(verify_result, verify_id)
    verify_performance = orchestration_performance_record("verify", context, token, verify_result)
    state.record_performance(verify_performance)
    state.progress_fragments[index].update(
        {
            "status": "verified" if verified else "verify_failed",
            "verify_id": verify_id,
            "verify_choice": verified,
            "verify_recomputed_hash": verify_result.get("recomputed_hash", ""),
            "verification_challenge": token.get("resolved_challenge", token["challenge"]),
            "verification_result": verify_result.get("verification", {}),
            "compute_receipt_hash": compute_receipt["receipt_hash"],
            "compute_billable_work_units": int(compute_receipt.get("billable_work_units", 0) or 0),
            "verify_receipt_hash": verify_receipt["receipt_hash"],
            "verify_billable_work_units": int(verify_receipt.get("billable_work_units", 0) or 0),
            "receipt_attestation": receipt_attestation,
            "verify_performance": verify_performance,
        }
    )
    state.write_progress("fragment_verified")
    if not verified:
        raise RuntimeError(f"raytracer fragment verification failed: {fragment_id}")
