"""Final step of a job: reassemble the image and write the summary.

The summary (`raytracer-summary.json`) is parsed by the BackEnd
(`parseRaytracerSummary` in internal/silicium/runner.go); its field names are
part of docs/contracts/backend-files.md. Billing only counts fragments whose
receipt attestation was accepted.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.receipt_verification import sha256_json
from workloads.common import sha256_file, write_json
from workloads.raytracer.orchestrator.devnet import run_devnet_trace
from workloads.raytracer.orchestrator.job_state import JobState
from workloads.raytracer.orchestrator.native_steps import reassemble_fragments

# Process exit code when the requested devnet trace failed (the image itself is fine).
EXIT_DEVNET_TRACE_FAILED = 3


def finalize_job(state: JobState, reassembled_dir: Path, summary_path: Path) -> int:
    """Reassemble, write summary and final progress, print the summary; return the exit code."""
    args = state.args
    reassembled_ppm = reassembled_dir / "render.ppm"
    reassembled_png = reassembled_dir / "render.png"
    reassemble_json = reassembled_dir / "reassemble.json"
    reassembled = reassemble_fragments(state.fragment_files, reassembled_ppm, reassembled_png, reassemble_json)
    for fragment in state.progress_fragments.values():
        fragment["status"] = "reassembled"
    summary = build_job_summary(state, reassembled_ppm, reassembled)
    write_json(summary_path, summary)
    if args.devnet_trace:
        summary["devnet_trace"] = _devnet_trace_block(state, summary_path)
        write_json(summary_path, summary)
    state.write_progress("reassembled", success=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.devnet_trace and not summary["devnet_trace"].get("ok"):
        return EXIT_DEVNET_TRACE_FAILED
    return 0


def accepted_fragments(state: JobState) -> list[dict[str, Any]]:
    """Progress entries whose verifier attestation was accepted (the billable ones)."""
    return [
        fragment
        for fragment in state.progress_fragments.values()
        if isinstance(fragment.get("receipt_attestation"), dict)
        and fragment["receipt_attestation"].get("accepted") is True
    ]


def receipt_hashes_of(fragments: list[dict[str, Any]]) -> list[str]:
    """Compute then verify receipt hash of each fragment, skipping empty ones."""
    return [
        value
        for fragment in fragments
        for value in (
            str(fragment.get("compute_receipt_hash", "")),
            str(fragment.get("verify_receipt_hash", "")),
        )
        if value
    ]


def build_job_summary(state: JobState, reassembled_ppm: Path, reassembled: dict[str, Any]) -> dict[str, Any]:
    """Summary of a successful job (before the optional devnet trace)."""
    accepted = accepted_fragments(state)
    receipt_hashes = receipt_hashes_of(accepted)
    return {
        "schema_version": 1,
        "mode": "raytracer_network_job",
        "success": True,
        "job_id": state.job_id,
        "scene": str(state.scene_path),
        "job_dir": str(state.job_dir),
        "export_dir": str(state.export_dir),
        "image": {"width": state.width, "height": state.height},
        "split_policy": state.split.get("split_policy", {}),
        "fragment_count": len(state.fragments),
        "fragments": state.sorted_progress_fragments(),
        "submissions": state.submissions,
        "node_runs": state.node_runs,
        "reassembled_ppm": str(reassembled_ppm),
        "reassembled_png": str(reassembled.get("result_png_path") or ""),
        "reassembled_png_ready": bool(reassembled.get("result_png_ready", False)),
        "reassembled_png_error": str(reassembled.get("result_png_error") or ""),
        # The fallback is evaluated eagerly (the PPM is hashed even when the
        # CLI reported result_sha256); kept as-is.
        "reassembled_hash": reassembled.get("result_sha256", sha256_file(reassembled_ppm)),
        "result_path": str(reassembled.get("result_png_path") or reassembled_ppm),
        "performance": state.performance_summary(),
        "devnet_trace": {"enabled": False, "status": "not_requested"},
        "billing": {
            "schema": "silicium.verified-billing.v1",
            "billable_work_units": sum(
                int(fragment.get("compute_billable_work_units", 0) or 0)
                + int(fragment.get("verify_billable_work_units", 0) or 0)
                for fragment in accepted
            ),
            "unit_policy": "deterministic rendered and sampled pixels; self-reported CPU is non-billable",
            "receipt_hashes": receipt_hashes,
            "receipt_set_hash": sha256_json(receipt_hashes),
        },
    }


def _devnet_trace_block(state: JobState, summary_path: Path) -> dict[str, Any]:
    """Run the devnet trace; any error becomes a failed `devnet_trace` block."""
    try:
        devnet_trace = run_devnet_trace(state.args, summary_path)
        devnet_trace["status"] = "submitted" if devnet_trace.get("ok") else "failed"
    except Exception as exc:
        devnet_trace = {
            "enabled": True,
            "ok": False,
            "status": "failed",
            "error": str(exc),
        }
    return devnet_trace
