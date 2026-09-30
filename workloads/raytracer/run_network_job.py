"""Legacy orchestration of a full raytracer job on the network.

Called by the BackEnd (internal/silicium/runner.go): splits the scene, dispatches
fragments, challenges milestones, reassembles the image and writes the progress,
fragment previews and receipts that the BackEnd reads (docs/contracts/backend-files.md).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterable

NETWORK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NETWORK_ROOT))

from networked.networked_runtime import (  # noqa: E402
    LocalNetworkEmitter,
    attach_network_content_blobs,
    best_shared_ref,
    dispatch_task_to_scheduler,
    fetch_network_content,
    RpcTaskEventListener,
    store_network_content,
    store_network_file,
)
from workloads.common import (  # noqa: E402
    clear_previous_result,
    default_solana_wallet_path,
    output_ref_from_compute,
    p2p_file_path,
    performance_duration,
    performance_ratio,
    resolve_solana_wallet,
    result_hash_from_compute,
    sha256_bytes,
    sha256_file,
    submit_task,
    write_json,
)
from workloads.raytracer import native  # noqa: E402
from workloads.raytracer.native import pipeline_binary  # noqa: E402
from tools.receipt_verification import (  # noqa: E402
    identity_id_for_key,
    sha256_json,
    stable_json,
    verify_ed25519_signature,
)


RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD = "calcul/rendering/raytracer-fragment"
RAYTRACER_FRAGMENT_VERIFY_WORKLOAD = "verification/rendering/raytracer-fragment"
RAYTRACER_PERFORMANCE_SCHEMA = "silicium.raytracer-performance.v1"


def merge_compute_intervals(records: Iterable[dict[str, Any]]) -> float:
    intervals: list[tuple[float, float]] = []
    for record in records:
        start = performance_duration(record.get("compute_started_unix_ms"))
        finish = performance_duration(record.get("compute_finished_unix_ms"))
        if start > 0 and finish > start:
            intervals.append((start, finish))
    if not intervals:
        return 0.0
    intervals.sort()
    merged_start, merged_finish = intervals[0]
    total = 0.0
    for start, finish in intervals[1:]:
        if start <= merged_finish:
            merged_finish = max(merged_finish, finish)
            continue
        total += merged_finish - merged_start
        merged_start, merged_finish = start, finish
    return performance_duration(total + merged_finish - merged_start)


def build_performance_summary(records: Iterable[dict[str, Any]], total_ms: float) -> dict[str, Any]:
    measured = [record for record in records if isinstance(record, dict)]
    compute_records = [record for record in measured if str(record.get("role", "")) == "compute"]
    verify_records = [record for record in measured if str(record.get("role", "")) == "verify"]
    compute_work_ms = performance_duration(sum(performance_duration(item.get("compute_ms")) for item in compute_records))
    verification_work_ms = performance_duration(sum(performance_duration(item.get("compute_ms")) for item in verify_records))
    compute_wall_ms = merge_compute_intervals(compute_records)
    if compute_wall_ms <= 0 and compute_records:
        compute_wall_ms = performance_duration(max(performance_duration(item.get("compute_ms")) for item in compute_records))
    total_wall_ms = performance_duration(total_ms)
    compute_wall_ms = performance_duration(min(total_wall_ms, compute_wall_ms))
    network_ms = performance_duration(sum(performance_duration(item.get("network_ms")) for item in measured))
    worker_overhead_ms = performance_duration(sum(performance_duration(item.get("worker_overhead_ms")) for item in measured))
    return {
        "schema": RAYTRACER_PERFORMANCE_SCHEMA,
        "total_ms": total_wall_ms,
        "compute_ms": compute_wall_ms,
        "compute_work_ms": compute_work_ms,
        "verification_ms": verification_work_ms,
        "network_ms": network_ms,
        "overhead_ms": performance_duration(max(0.0, total_wall_ms - compute_wall_ms)),
        "worker_overhead_ms": worker_overhead_ms,
        "compute_to_total_ratio": performance_ratio(compute_wall_ms, total_wall_ms),
        "compute_to_network_ratio": performance_ratio(compute_work_ms, network_ms),
        "parallelism_factor": performance_ratio(compute_work_ms, compute_wall_ms),
        "measured_compute_tasks": len(compute_records),
        "measured_verify_tasks": len(verify_records),
        "definition": {
            "total_ms": "wall time from workload start to assembled result",
            "compute_ms": "union of renderer intervals on compute workers; parallel work is counted once",
            "compute_work_ms": "sum of renderer time across compute workers",
            "network_ms": "dispatch, queue/result wait and artifact fetch outside the worker; verification is included",
        },
    }


def validate_compute_receipt(result: dict[str, Any], task_id: str) -> dict[str, Any]:
    receipt = result.get("compute_receipt")
    if not isinstance(receipt, dict):
        raise RuntimeError(f"compute_receipt_missing:{task_id}")
    unsigned = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_hash", "worker_identity_id", "worker_public_key", "worker_signature"}
    }
    expected_hash = sha256_json(unsigned)
    if str(receipt.get("receipt_hash", "")) != expected_hash:
        raise RuntimeError(f"compute_receipt_hash_invalid:{task_id}")
    public_key = str(receipt.get("worker_public_key", ""))
    if identity_id_for_key(public_key) != str(receipt.get("worker_identity_id", "")):
        raise RuntimeError(f"compute_receipt_identity_invalid:{task_id}")
    if not verify_ed25519_signature(
        stable_json(unsigned).encode("utf-8"),
        str(receipt.get("worker_signature", "")),
        public_key,
    ):
        raise RuntimeError(f"compute_receipt_signature_invalid:{task_id}")
    if str(receipt.get("task_id", "")) != task_id:
        raise RuntimeError(f"compute_receipt_task_invalid:{task_id}")
    return receipt


def validate_receipt_attestation(
    verify_result: dict[str, Any],
    compute_receipt_hash: str,
    verify_task_id: str,
) -> dict[str, Any]:
    attestation = verify_result.get("receipt_attestation")
    if not isinstance(attestation, dict):
        raise RuntimeError(f"receipt_attestation_missing:{verify_task_id}")
    unsigned = {
        key: value
        for key, value in attestation.items()
        if key not in {"verifier_identity_id", "verifier_public_key", "verifier_signature"}
    }
    if str(attestation.get("compute_receipt_hash", "")) != compute_receipt_hash:
        raise RuntimeError(f"receipt_attestation_hash_mismatch:{verify_task_id}")
    public_key = str(attestation.get("verifier_public_key", ""))
    if identity_id_for_key(public_key) != str(attestation.get("verifier_identity_id", "")):
        raise RuntimeError(f"receipt_attestation_identity_invalid:{verify_task_id}")
    if not verify_ed25519_signature(
        stable_json(unsigned).encode("utf-8"),
        str(attestation.get("verifier_signature", "")),
        public_key,
    ):
        raise RuntimeError(f"receipt_attestation_signature_invalid:{verify_task_id}")
    if not bool(attestation.get("accepted", False)):
        verification = verify_result.get("verification")
        if not isinstance(verification, dict):
            verification = {}
        raise RuntimeError(
            f"receipt_attestation_rejected:{verify_task_id}"
            f":verifier={attestation.get('verifier_node_id', '')}"
            f":expected={verification.get('expected_pixel_hash', verify_result.get('expected_hash', ''))}"
            f":recomputed={verification.get('recomputed_pixel_hash', verify_result.get('recomputed_hash', ''))}"
        )
    return attestation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run raytracer as a Silicium network workload.")
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
    parser.add_argument("--target-pixels", type=int, default=120_000)
    parser.add_argument("--max-fragments", type=int, default=32)
    parser.add_argument("--fragments", type=int, default=0, help="Optional manual override; 0 keeps automatic split.")
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
    parser.add_argument("--solana-enable", action="store_true")
    parser.add_argument("--devnet-trace", action="store_true")
    parser.add_argument("--devnet-trace-timeout-s", type=float, default=420.0)
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.environ.get("ANCHOR_WALLET", "")))
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument("--solana-program-id", default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"))
    parser.add_argument("--devnet-tx-delay-ms", type=int, default=int(os.environ.get("SILICIUM_DEVNET_TX_DELAY_MS", "1200")))
    return parser


def task_input_ref(args: argparse.Namespace, export_dir: Path, path: Path) -> dict[str, Any]:
    if args.node_mode == "network":
        return store_network_file(export_dir, path, args.network_node_id)
    return {"protocol": "file", "content_id": str(path), "hash": "sha256:" + sha256_file(path)}


def bytes_input_ref(args: argparse.Namespace, export_dir: Path, data: bytes) -> dict[str, Any]:
    if args.node_mode == "network":
        return store_network_content(export_dir, data, args.network_node_id)
    digest = sha256_bytes(data)
    path = export_dir / "p2p" / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return {"protocol": "file", "content_id": str(path), "hash": "sha256:" + digest}


def read_ref_bytes(args: argparse.Namespace, export_dir: Path, ref: dict[str, Any]) -> bytes:
    if args.node_mode == "network":
        return fetch_network_content(export_dir, args.network_node_id, ref, args.network_mesh_key)
    return p2p_file_path(ref).read_bytes()


def task_failure_details(result: dict[str, Any]) -> tuple[str, str]:
    error = str(result.get("error") or result.get("last_error") or "unknown_error").strip()
    error_type = str(result.get("error_type") or "").strip()
    traceback_text = str(result.get("traceback") or result.get("error_traceback") or "").strip()
    detail = error or "unknown_error"
    if error_type and error_type not in detail:
        detail = f"{error_type}: {detail}"
    if traceback_text and traceback_text not in detail:
        detail = f"{detail}\n\nTraceback worker:\n{traceback_text}"
    node_id = str(result.get("node_id") or "")
    return detail, node_id


def is_transient_task_failure(error: str) -> bool:
    normalized = str(error).lower()
    return any(
        marker in normalized
        for marker in (
            "peer_content_not_found:",
            "unknown_peer_for_content:",
            "content_not_found",
            "missing network result after deadline:",
            "timed out",
            "timeout",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
        )
    )


def ensure_task_success(result: dict[str, Any], task_id: str) -> None:
    if result.get("success", True) is not False:
        return
    error, node_id = task_failure_details(result)
    raise RuntimeError(f"task failed: {task_id} on {node_id}\n{error}")


class RetryFragmentStage:
    def __init__(self, reason: str) -> None:
        self.reason = reason


def submit_network_task(
    args: argparse.Namespace,
    export_dir: Path,
    payload: dict[str, Any],
    emitter_node: LocalNetworkEmitter | None,
) -> dict[str, Any]:
    """Queue locally for a shared scheduler, otherwise dispatch to the seed."""
    payload = attach_network_content_blobs(export_dir, payload)
    emitter_node_id = str(getattr(args, "network_node_id", "") or "").strip()
    if emitter_node_id:
        payload.setdefault("emitter_node_id", emitter_node_id)
        payload.setdefault("origin_node_id", emitter_node_id)
    task_id = str(payload.get("task_id", ""))
    required_roles = payload.get("required_roles", [])
    if emitter_node is None:
        submission = submit_task(export_dir, payload)
        submission["scheduler_dispatch"] = {
            "status": "queued_local",
            "target": str(export_dir),
        }
        submission["queue"] = "scheduler://local-export"
        return submission

    # Optional local protobuf/ZeroMQ control plane. It avoids an HTTP round
    # trip when a scheduler gateway is colocated with the node, while retaining
    # the signed HTTP path as a transparent fallback for older releases.
    rpc_endpoint = str(os.environ.get("SILICIUM_RPC_ENDPOINT", "")).strip()
    rpc_fallback_error = ""
    if rpc_endpoint:
        try:
            from tools.rpc_client import RpcClient
            # The experiment API already uses the MCP bearer for the same
            # authenticated control plane.  Reuse it when a dedicated RPC
            # token is not configured; otherwise an in-container renderer
            # silently falls back to the legacy HTTP dispatcher.
            rpc_token = os.environ.get("SILICIUM_RPC_TOKEN", "") or os.environ.get("SILICIUM_MCP_TOKEN", "")
            rpc_result = RpcClient(rpc_endpoint, rpc_token, timeout_ms=3000).call("task.dispatch", payload)
            return {
                "task_id": task_id,
                "required_roles": required_roles,
                "priority": args.priority,
                "status": str(rpc_result.get("status", "dispatched")),
                "queue": "rpc://task.dispatch",
                "scheduler_dispatch": {"status": "dispatched", "target": rpc_endpoint, "transport": "protobuf+zeromq"},
            }
        except Exception as error:
            # A rolling upgrade must not strand work when the sidecar is absent.
            rpc_fallback_error = f"{type(error).__name__}:{error}"

    scheduler_dispatch = dispatch_task_to_scheduler(
        payload,
        args.network_seed_peers,
        args.network_mesh_key,
        export_dir=export_dir,
        node_id=args.network_node_id,
    )
    if rpc_fallback_error:
        scheduler_dispatch = {**scheduler_dispatch, "rpc_fallback_error": rpc_fallback_error}
    return {
        "task_id": task_id,
        "required_roles": required_roles,
        "priority": args.priority,
        "status": scheduler_dispatch["status"],
        "queue": "scheduler://tasks/dispatch",
        "scheduler_dispatch": scheduler_dispatch,
    }


def ensure_submission_success(submission: dict[str, Any]) -> None:
    status = str(submission.get("status", ""))
    if status in {"queued", "dispatched"}:
        return
    dispatch = submission.get("scheduler_dispatch", {})
    raise RuntimeError(
        "scheduler_dispatch_failed:"
        + json.dumps(dispatch, sort_keys=True, separators=(",", ":"))
    )


def run_bounded_fragment_pipeline(
    fragments: list[dict[str, Any]],
    *,
    max_compute_in_flight: int,
    max_verify_in_flight: int,
    launch_compute: Callable[[dict[str, Any]], Any],
    poll_compute: Callable[[dict[str, Any], Any], Any | None],
    launch_verify: Callable[[dict[str, Any], Any], Any],
    poll_verify: Callable[[dict[str, Any], Any, Any], Any | None],
    finish_verify: Callable[[dict[str, Any], Any, Any, Any], None],
    idle: Callable[[], None] = lambda: time.sleep(0.1),
) -> None:
    """Drive independent compute/verify leaves without a global fragment barrier."""
    compute_limit = max(1, max_compute_in_flight or len(fragments) or 1)
    verify_limit = max(1, max_verify_in_flight or len(fragments) or 1)
    pending_compute = deque(fragments)
    pending_verify: deque[tuple[dict[str, Any], Any]] = deque()
    computing: list[tuple[dict[str, Any], Any]] = []
    verifying: list[tuple[dict[str, Any], Any, Any]] = []
    finished = 0

    while finished < len(fragments):
        progressed = False
        while pending_compute and len(computing) < compute_limit:
            fragment = pending_compute.popleft()
            computing.append((fragment, launch_compute(fragment)))
            progressed = True

        for fragment, compute_token in list(computing):
            computed = poll_compute(fragment, compute_token)
            if computed is None:
                continue
            computing.remove((fragment, compute_token))
            if isinstance(computed, RetryFragmentStage):
                pending_compute.append(fragment)
                progressed = True
                continue
            pending_verify.append((fragment, computed))
            progressed = True

        while pending_verify and len(verifying) < verify_limit:
            fragment, computed = pending_verify.popleft()
            verifying.append((fragment, computed, launch_verify(fragment, computed)))
            progressed = True

        for fragment, computed, verify_token in list(verifying):
            verified = poll_verify(fragment, computed, verify_token)
            if verified is None:
                continue
            verifying.remove((fragment, computed, verify_token))
            if isinstance(verified, RetryFragmentStage):
                pending_verify.append((fragment, computed))
                progressed = True
                continue
            finish_verify(fragment, computed, verify_token, verified)
            finished += 1
            progressed = True

        if not progressed:
            idle()


def poll_task_result_attempts(
    export_dir: Path,
    task_id: str,
    late_task_ids: list[str],
    deadline: float,
) -> tuple[str, dict[str, Any]] | None:
    """Return the first valid result, including one from a timed-out predecessor."""
    candidates = [*late_task_ids, task_id]
    for candidate_id in dict.fromkeys(candidates):
        result_path = export_dir / f"result.{candidate_id}.json"
        if not result_path.exists():
            continue
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if candidate_id != task_id and payload.get("success", True) is False:
            continue
        return candidate_id, payload

    # Only the current attempt can terminate the stage through a dead letter.
    # A dead-lettered predecessor remains historical evidence, not a new failure.
    dead_letters_path = export_dir / "dead_letters.ndjson"
    if dead_letters_path.exists():
        for line in dead_letters_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and str(item.get("task_id", "")) == task_id:
                raise RuntimeError(
                    "network task dead-lettered: "
                    + str(item.get("last_error", "unknown_error"))
                    + f" ({task_id})"
                )
    if time.monotonic() > deadline:
        result_path = export_dir / f"result.{task_id}.json"
        raise TimeoutError(f"missing network result after deadline: {result_path}")
    return None


def refresh_attempt_deadline(
    export_dir: Path,
    token: dict[str, Any],
    execution_timeout_s: float,
) -> float:
    """Switch from the queue deadline to a fresh execution deadline once claimed."""
    execution_deadline = token.get("execution_deadline")
    if execution_deadline is not None:
        return float(execution_deadline)

    task_id = str(token["task_id"])
    task_path = export_dir / "tasks" / f"{task_id}.json"
    try:
        envelope = json.loads(task_path.read_text(encoding="utf-8")) if task_path.exists() else {}
    except json.JSONDecodeError:
        envelope = {}
    status = str(envelope.get("status", "")).strip().lower() if isinstance(envelope, dict) else ""
    if status in {"claimed", "dispatched", "in_progress", "processing", "running"}:
        execution_deadline = time.monotonic() + max(1.0, execution_timeout_s)
        token["execution_deadline"] = execution_deadline
        return float(execution_deadline)
    return float(token["queue_deadline"])


def discovered_role_capacity(
    export_dir: Path,
    node_id: str,
    role: str,
    required_features: Iterable[str] = (),
) -> int:
    """Count currently discovered HTTP peers that advertise a workload role."""
    peers_path = export_dir / f"node.{node_id}.peers.json"
    try:
        payload = json.loads(peers_path.read_text(encoding="utf-8")) if peers_path.exists() else {}
    except json.JSONDecodeError:
        payload = {}
    peers = payload.get("peers", []) if isinstance(payload, dict) else []
    wanted = role.strip().lower()
    wanted_features = {str(feature).strip() for feature in required_features if str(feature).strip()}
    eligible = {
        str(peer.get("node_id", "")).strip()
        for peer in peers
        if isinstance(peer, dict)
        and wanted
        in {
            str(value).strip().lower()
            for value in (peer.get("roles", []) if isinstance(peer.get("roles"), list) else [])
        }
        and str(peer.get("http_base_url", "")).strip()
        and str(peer.get("node_id", "")).strip()
        and wanted_features.issubset(
            {str(feature).strip() for feature in (peer.get("features", []) if isinstance(peer.get("features"), list) else [])}
        )
    }
    return max(1, len(eligible))


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


def resolve_in_flight_limit(configured: int, export_dir: Path, node_id: str, role: str) -> int:
    return max(1, configured) if configured > 0 else discovered_role_capacity(export_dir, node_id, role)


def ensure_raytracer_compute_contract(result: dict[str, Any], task_id: str) -> None:
    compute = result.get("compute")
    mode = str(compute.get("mode", "")) if isinstance(compute, dict) else ""
    executed = bool(compute.get("executed", False)) if isinstance(compute, dict) else False
    milestones = result.get("verification_milestones")
    if mode != "raytracer-fragment" or not executed or not isinstance(milestones, dict):
        node_id = str(result.get("node_id") or "")
        raise RuntimeError(
            "raytracer_compute_contract_invalid:"
            f"task={task_id}:node={node_id}:mode={mode or 'missing'}:executed={str(executed).lower()}"
        )


def wait_for_network_role(export_dir: Path, node_id: str, role: str, timeout_s: float = 20.0) -> None:
    peers_path = export_dir / f"node.{node_id}.peers.json"
    deadline = time.monotonic() + timeout_s
    wanted = role.lower()
    while time.monotonic() <= deadline:
        try:
            payload = json.loads(peers_path.read_text(encoding="utf-8")) if peers_path.exists() else {}
        except json.JSONDecodeError:
            payload = {}
        peers = payload.get("peers", []) if isinstance(payload, dict) else []
        for peer in peers:
            if not isinstance(peer, dict):
                continue
            roles = {str(item).lower() for item in peer.get("roles", []) if str(item).strip()}
            if wanted in roles and str(peer.get("http_base_url", "")).strip():
                return
        time.sleep(0.25)
    raise TimeoutError(f"missing network peer with role {role!r} after {timeout_s:.1f}s: {peers_path}")


def make_split(args: argparse.Namespace, scene_path: Path, split_path: Path) -> dict[str, Any]:
    cmd = [
        pipeline_binary(),
        "split",
        str(scene_path),
        "--output",
        str(split_path),
        "--target-pixels",
        str(args.target_pixels),
        "--max-fragments",
        str(args.max_fragments),
    ]
    if args.fragments > 0:
        cmd.extend(["--fragments", str(args.fragments)])
    completed = subprocess.run(cmd, text=True, capture_output=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"raytracer_split_failed:{completed.stderr[-2048:]}")
    return json.loads(split_path.read_text(encoding="utf-8"))


def reassemble_fragments(fragment_files: list[tuple[int, int, Path]], output_ppm: Path, output_png: Path, result_json: Path) -> dict[str, Any]:
    cmd = [pipeline_binary(), "reassemble"]
    for x_start, y_start, fragment_file in fragment_files:
        cmd.extend(
            [
                "--fragment", str(fragment_file),
                "--x-start", str(x_start),
                "--y-start", str(y_start),
            ]
        )
    cmd.extend(["--output", str(output_ppm), "--png", str(output_png)])
    completed = subprocess.run(cmd, text=True, capture_output=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"raytracer_reassemble_failed:{completed.stderr[-2048:]}")
    # The CLI prints its result on stdout; keep it next to the image as before.
    result_json.write_text(completed.stdout, encoding="utf-8")
    return json.loads(completed.stdout)


def run_devnet_trace(args: argparse.Namespace, summary_path: Path) -> dict[str, Any]:
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
    env = os.environ.copy()
    env["SILICIUM_TRACE_RESULT_PATH"] = str(trace_path)
    env["ANCHOR_WALLET"] = str(wallet_path)
    env["SOLANA_RPC_URL"] = args.solana_rpc
    env["SOLANA_LAYER_PROGRAM_ID"] = args.solana_program_id
    env["SILICIUM_DEVNET_TX_DELAY_MS"] = str(args.devnet_tx_delay_ms)
    completed = subprocess.run(
        [npx, "ts-node", "scripts/devnet_trace_fragments.ts", str(summary_path)],
        cwd=str(NETWORK_ROOT / "solana-layer"),
        env=env,
        text=True,
        capture_output=True,
        timeout=args.devnet_trace_timeout_s,
        check=False,
    )
    trace: dict[str, Any] = {}
    if trace_path.exists():
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            trace = payload
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    job_started = time.perf_counter()
    scene_path = Path(args.scene).resolve()
    width, height = native.scene_resolution(scene_path)
    job_id = args.job_id or f"raytracer-auto-{int(time.time())}"
    output_root = Path(args.output_root).resolve()
    job_dir = output_root / job_id
    if job_dir.exists() and any(job_dir.iterdir()) and not args.reuse_job_dir:
        raise RuntimeError(
            f"job directory already exists: {job_dir}\n"
            "Use a new --job-id for a fresh run, or pass --reuse-job-dir intentionally."
        )

    export_dir = Path(args.export_dir).resolve() if args.export_dir else (job_dir / "export").resolve()
    args.export_dir = str(export_dir)
    input_dir = job_dir / "input"
    fragments_dir = job_dir / "fragments"
    reassembled_dir = job_dir / "reassembled"
    input_dir.mkdir(parents=True, exist_ok=True)
    fragments_dir.mkdir(parents=True, exist_ok=True)
    reassembled_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    if args.node_mode == "network":
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

    local_scene = input_dir / "scene.cfg"
    shutil.copy2(scene_path, local_scene)
    split_path = job_dir / "raytracer-split.json"
    summary_path = job_dir / "raytracer-summary.json"
    progress_path = job_dir / "raytracer-progress.json"
    split = make_split(args, local_scene, split_path)
    fragments = list(split.get("fragments", []))

    node_runs: list[dict[str, Any]] = []
    submissions: list[dict[str, Any]] = []
    performance_records: list[dict[str, Any]] = []
    emitter_result: dict[str, Any] = {"enabled": False}
    progress_fragments = {
        int(fragment["fragment_index"]): {**fragment, "status": "planned"}
        for fragment in fragments
    }

    def write_progress(stage: str, success: bool = False) -> None:
        write_json(
            progress_path,
            {
                "schema_version": 1,
                "mode": "raytracer_network_job",
                "progress": True,
                "stage": stage,
                "success": success,
                "job_id": job_id,
                "job_dir": str(job_dir),
                "export_dir": str(export_dir),
                "scene": str(scene_path),
                "image": {"width": width, "height": height},
                "split_policy": split.get("split_policy", {}),
                "fragment_count": len(fragments),
                "pipeline_limits": {
                    "compute": compute_in_flight_limit,
                    "verify": verify_in_flight_limit,
                },
                "fragments": [progress_fragments[index] for index in sorted(progress_fragments)],
                "submissions": submissions,
                "node_runs": node_runs,
                "performance": build_performance_summary(
                    performance_records,
                    (time.perf_counter() - job_started) * 1000.0,
                ),
                "network": emitter_result,
                "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    def orchestration_performance_record(
        role: str,
        context: dict[str, Any],
        token: dict[str, Any],
        result: dict[str, Any],
        *,
        artifact_fetch_ms: float = 0.0,
    ) -> dict[str, Any]:
        worker_performance = result.get("performance") if isinstance(result.get("performance"), dict) else {}
        worker_total_ms = performance_duration(
            worker_performance.get("workload_total_ms")
            or worker_performance.get("total_ms")
            or result.get("duration_ms")
        )
        compute_ms = performance_duration(worker_performance.get("compute_ms"))
        worker_network_ms = performance_duration(
            worker_performance.get("worker_network_ms")
            or worker_performance.get("network_ms")
        )
        worker_overhead_ms = performance_duration(
            worker_performance.get("workload_overhead_ms")
            or worker_performance.get("overhead_ms")
        )
        dispatch_ms = performance_duration(token.get("dispatch_ms"))
        result_wait_ms = performance_duration(token.get("result_wait_ms"))
        artifact_fetch_ms = performance_duration(artifact_fetch_ms)
        external_network_ms = performance_duration(
            dispatch_ms + max(0.0, result_wait_ms - worker_total_ms) + artifact_fetch_ms
        )
        total_ms = performance_duration(dispatch_ms + result_wait_ms + artifact_fetch_ms)
        network_ms = performance_duration(external_network_ms + worker_network_ms)
        record = {
            "schema": RAYTRACER_PERFORMANCE_SCHEMA,
            "role": role,
            "fragment_index": int(context["index"]),
            "task_id": str(token.get("resolved_task_id") or token.get("task_id") or ""),
            "node_id": str(result.get("node_id", "")),
            "total_ms": total_ms,
            "compute_ms": compute_ms,
            "network_ms": network_ms,
            "external_network_ms": external_network_ms,
            "worker_total_ms": worker_total_ms,
            "worker_network_ms": worker_network_ms,
            "worker_overhead_ms": worker_overhead_ms,
            "dispatch_ms": dispatch_ms,
            "result_wait_ms": result_wait_ms,
            "artifact_fetch_ms": artifact_fetch_ms,
            "overhead_ms": performance_duration(max(0.0, total_ms - compute_ms)),
            "compute_to_total_ratio": performance_ratio(compute_ms, total_ms),
            "compute_to_network_ratio": performance_ratio(compute_ms, network_ms),
            "compute_started_unix_ms": performance_duration(worker_performance.get("compute_started_unix_ms")),
            "compute_finished_unix_ms": performance_duration(worker_performance.get("compute_finished_unix_ms")),
        }
        return record

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


    try:
        scene_ref = task_input_ref(args, export_dir, local_scene)
        write_progress("split_ready")
        fragment_files: list[tuple[int, int, Path]] = []

        pipeline_fragments = []
        for fragment in fragments:
            index = int(fragment["fragment_index"])
            pipeline_fragments.append(
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

        def retry_transient_stage(
            context: dict[str, Any],
            token: dict[str, Any],
            *,
            stage: str,
            error: str,
            node_id: str = "",
        ) -> RetryFragmentStage | None:
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
                    export_dir,
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
            retries = progress_fragments[index].setdefault("retries", [])
            if isinstance(retries, list):
                retries.append(retry)
            if "missing network result after deadline:" in error.lower():
                late_task_ids = context.setdefault(f"{stage}_late_task_ids", [])
                timed_out_task_id = str(token.get("task_id", ""))
                if isinstance(late_task_ids, list) and timed_out_task_id not in late_task_ids:
                    late_task_ids.append(timed_out_task_id)
            progress_fragments[index].update(
                {
                    "status": f"{stage}_retrying",
                    f"{stage}_attempt": attempt,
                    f"{stage}_max_attempts": max_attempts,
                    "last_transient_error": error,
                }
            )
            write_progress(f"{stage}_retrying")
            return RetryFragmentStage(error)

        def launch_compute(context: dict[str, Any]) -> dict[str, Any]:
            index = int(context["index"])
            x_start = int(context["x_start"])
            x_end = int(context["x_end"])
            y_start = int(context["y_start"])
            y_end = int(context["y_end"])
            fragment_id = str(context["fragment_id"])
            attempt = int(context.get("compute_attempt", 0)) + 1
            context["compute_attempt"] = attempt
            task_id = fragment_id if attempt == 1 else f"{fragment_id}-compute-retry-{attempt:02d}"
            spec = {
                "fragment_index": index,
                "fragment_count": len(fragments),
                "x_start": x_start,
                "x_end": x_end,
                "y_start": y_start,
                "y_end": y_end,
                "scene_p2p_ref": scene_ref,
                "verification_batch_rows": max(1, int(args.verification_batch_rows)),
            }
            progress_fragments[index].update(
                {
                    "status": "queued_compute",
                    "compute_attempt": attempt,
                    "compute_max_attempts": max(1, int(args.max_compute_attempts)),
                }
            )
            dispatch_started = time.perf_counter()
            compute_payload = {
                "task_id": task_id,
                "required_roles": ["compute"],
                # Do not send latency-sensitive tiles to a legacy worker
                # whose renderer progress writes serialize the pixel loop.
                "required_features": ["raytracer_fastpath_v1"],
                "priority": args.priority,
                "excluded_peer_ids": list(context.get("compute_excluded_peer_ids", [])),
                "p2p_ref": bytes_input_ref(args, export_dir, json.dumps(spec, sort_keys=True).encode("utf-8")),
                "task": {
                    "kind": "compute",
                    "workload": RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD,
                    "required_features": ["raytracer_fastpath_v1"],
                    "inline_input": spec,
                    "fragment_index": index,
                    "fragment_count": len(fragments),
                    "x_start": x_start,
                    "x_end": x_end,
                    "y_start": y_start,
                    "y_end": y_end,
                    "verification_batch_rows": max(1, int(args.verification_batch_rows)),
                    "scene_p2p_ref": scene_ref,
                    "timeout_s": int(args.node_timeout_s),
                    "root_job_id": job_id,
                },
            }
            # The scheduler is the durable result sink.  An emitter launched
            # inside a backend/API container usually advertises 127.0.0.1 or
            # an ephemeral port; placing that URL in the envelope makes a
            # remote worker return the tile to *its own* localhost.  Keep a
            # direct return as an explicit opt-in for externally reachable
            # emitters only, and otherwise let the scheduler set its public
            # /results/dispatch endpoint during the claim.
            if emitter_node is not None and os.environ.get("SILICIUM_RAYTRACER_DIRECT_RESULT_RETURN", "") == "1":
                compute_payload["origin_result_return_url"] = emitter_node.public_url.rstrip("/") + "/results/dispatch"
            clear_previous_result(export_dir, task_id)
            if args.node_mode == "network":
                submission = submit_network_task(args, export_dir, compute_payload, emitter_node)
            else:
                submission = submit_task(export_dir, compute_payload)
            submissions.append(submission)
            try:
                ensure_submission_success(submission)
            except RuntimeError as error:
                progress_fragments[index].update({"status": "compute_dispatch_failed", "error": str(error)})
                write_progress("compute_dispatch_failed")
                raise
            dispatch_ms = performance_duration((time.perf_counter() - dispatch_started) * 1000.0)
            write_progress("compute_queued")
            return {
                "task_id": task_id,
                "attempt": attempt,
                "queue_deadline": time.monotonic() + args.result_timeout_s,
                "dispatch_ms": dispatch_ms,
                "result_wait_started": time.perf_counter(),
            }

        def poll_compute(
            context: dict[str, Any],
            token: dict[str, Any],
        ) -> dict[str, Any] | RetryFragmentStage | None:
            index = int(context["index"])
            x_start = int(context["x_start"])
            x_end = int(context["x_end"])
            y_start = int(context["y_start"])
            y_end = int(context["y_end"])
            fragment_id = str(context["fragment_id"])
            task_id = str(token["task_id"])
            try:
                deadline = refresh_attempt_deadline(export_dir, token, float(args.node_timeout_s))
                resolved = poll_task_result_attempts(
                    export_dir,
                    task_id,
                    list(context.get("compute_late_task_ids", [])),
                    deadline,
                )
            except Exception as error:
                retry = retry_transient_stage(context, token, stage="compute", error=str(error))
                if retry is not None:
                    return retry
                progress_fragments[index].update({"status": "compute_failed", "error": str(error)})
                write_progress("compute_failed")
                raise
            if resolved is None:
                return None
            resolved_task_id, compute_result = resolved
            token["resolved_task_id"] = resolved_task_id
            result_wait_started = token.get("result_wait_started")
            if result_wait_started is not None:
                try:
                    token["result_wait_ms"] = performance_duration(
                        (time.perf_counter() - float(result_wait_started)) * 1000.0
                    )
                except (TypeError, ValueError):
                    token["result_wait_ms"] = 0.0
            node_runs.append(
                {
                    "role": "compute",
                    "mode": "network",
                    "target_task_id": resolved_task_id,
                    "target_result_ready": True,
                    "handled_by": compute_result.get("node_id", ""),
                }
            )
            if compute_result.get("success", True) is False:
                task_error, failed_node_id = task_failure_details(compute_result)
                retry = retry_transient_stage(
                    context,
                    token,
                    stage="compute",
                    error=task_error,
                    node_id=failed_node_id,
                )
                if retry is not None:
                    return retry
            try:
                ensure_task_success(compute_result, resolved_task_id)
                ensure_raytracer_compute_contract(compute_result, resolved_task_id)
                compute_receipt = validate_compute_receipt(compute_result, resolved_task_id)
                output_ref = output_ref_from_compute(compute_result)
                result_hash = result_hash_from_compute(compute_result)
                artifact_fetch_started = time.perf_counter()
                fragment_bytes = read_ref_bytes(args, export_dir, output_ref)
                artifact_fetch_ms = performance_duration((time.perf_counter() - artifact_fetch_started) * 1000.0)
                fragment_metadata = native.validate_fragment(
                    fragment_bytes,
                    task_id=resolved_task_id,
                    expected_width=x_end - x_start,
                    expected_height=y_end - y_start,
                    expected_hash=result_hash,
                )
                worker_milestones = compute_result.get("verification_milestones")
                expected_milestones = native.build_milestones(
                    fragment_bytes,
                    y_start,
                    max(1, int(args.verification_batch_rows)),
                    x_start,
                )
                if worker_milestones != expected_milestones:
                    raise RuntimeError("raytracer_milestone_commitment_invalid")
            except Exception as error:
                progress_fragments[index].update({"status": "compute_failed", "error": str(error)})
                write_progress("compute_failed")
                raise
            compute_performance = orchestration_performance_record(
                "compute",
                context,
                token,
                compute_result,
                artifact_fetch_ms=artifact_fetch_ms,
            )
            performance_records.append(compute_performance)
            if node_runs:
                node_runs[-1]["performance"] = compute_performance
            fragment_file = fragments_dir / f"fragment-{index:03d}.ppm"
            fragment_png = fragments_dir / f"fragment-{index:03d}.png"
            fragment_file.write_bytes(fragment_bytes)
            preview = native.write_png(fragment_bytes, fragment_png)
            fragment_files.append((x_start, y_start, fragment_file))
            progress_fragments[index].update(
                {
                    "status": "computed",
                    "preview_ready": preview["ready"],
                    "preview_path": preview["path"],
                    "preview_error": preview["error"],
                    "fragment_width": fragment_metadata["width"],
                    "fragment_height": fragment_metadata["height"],
                    "result_hash": result_hash,
                    "output_ref": output_ref,
                    "expected_hash": result_hash,
                    "compute_result_hash": result_hash,
                    "compute_output_ref": output_ref,
                    "verification_mode": expected_milestones["strategy"],
                    "verification_commitment_hash": expected_milestones["commitment_hash"],
                    "verification_milestone_count": expected_milestones["milestone_count"],
                    "compute_receipt_hash": compute_receipt["receipt_hash"],
                    "compute_billable_work_units": int(compute_receipt.get("billable_work_units", 0) or 0),
                    "performance": compute_performance,
                }
            )
            write_progress("fragment_computed")
            return {
                "compute_result": compute_result,
                "compute_task_id": resolved_task_id,
                "expected_milestones": expected_milestones,
                "result_hash": result_hash,
                "output_ref": output_ref,
                "compute_receipt": compute_receipt,
            }

        def launch_verify(context: dict[str, Any], computed: dict[str, Any]) -> dict[str, Any]:
            index = int(context["index"])
            x_start = int(context["x_start"])
            x_end = int(context["x_end"])
            y_start = int(context["y_start"])
            y_end = int(context["y_end"])
            fragment_id = str(context["fragment_id"])
            compute_result = computed["compute_result"]
            compute_task_id = str(computed["compute_task_id"])
            compute_receipt = computed["compute_receipt"]
            expected_milestones = computed["expected_milestones"]
            attempt = int(context.get("verify_attempt", 0)) + 1
            context["verify_attempt"] = attempt
            verify_id = (
                f"{fragment_id}-verify"
                if attempt == 1
                else f"{fragment_id}-verify-retry-{attempt:02d}"
            )
            challenged_milestone = secrets.choice(expected_milestones["milestones"])
            challenge = {
                "schema_version": 1,
                "strategy": expected_milestones["strategy"],
                "challenge_nonce": secrets.token_hex(16),
                "source_task_id": compute_task_id,
                "fragment_index": index,
                "fragment_rows": expected_milestones["fragment_rows"],
                "milestone_count": expected_milestones["milestone_count"],
                "commitment_hash": expected_milestones["commitment_hash"],
                "milestone": challenged_milestone,
            }
            verify_challenges = context.setdefault("verify_challenges", {})
            if isinstance(verify_challenges, dict):
                verify_challenges[verify_id] = challenge
            challenge_ref = bytes_input_ref(
                args,
                export_dir,
                json.dumps(challenge, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            )
            verify_excluded_peer_ids = {
                str(value)
                for value in context.get("verify_excluded_peer_ids", [])
                if str(value).strip()
            }
            # Preserve independent verification whenever another verifier is
            # available. In a one-node network, excluding the compute node
            # leaves every verify task permanently unclaimable.
            if discovered_role_capacity(
                export_dir,
                args.network_node_id,
                "verify",
            ) > 1:
                verify_excluded_peer_ids.add(str(compute_result.get("node_id", "")))
            dispatch_started = time.perf_counter()
            verify_payload = {
                "task_id": verify_id,
                "required_roles": ["verify"],
                "required_features": ["raytracer_fastpath_v1"],
                "priority": args.priority,
                "p2p_ref": challenge_ref,
                "expected_hash": "sha256:" + str(challenged_milestone["pixel_sha256"]),
                "excluded_peer_ids": sorted(verify_excluded_peer_ids - {""}),
                "scene_p2p_ref": scene_ref,
                "task": {
                    "kind": "verify",
                    "workload": RAYTRACER_FRAGMENT_VERIFY_WORKLOAD,
                    "required_features": ["raytracer_fastpath_v1"],
                    "inline_input": challenge,
                    "expected_hash": "sha256:" + str(challenged_milestone["pixel_sha256"]),
                    "verification_mode": expected_milestones["strategy"],
                    "max_sample_rows": max(1, int(args.verification_batch_rows)),
                    "scene_p2p_ref": scene_ref,
                    "source_task_id": compute_task_id,
                    "source_node_id": str(compute_result.get("node_id", "")),
                    "source_output_ref": best_shared_ref(computed["output_ref"]),
                    "fragment_index": index,
                    "fragment_count": len(fragments),
                    "x_start": x_start,
                    "x_end": x_end,
                    "y_start": y_start,
                    "y_end": y_end,
                    "timeout_s": int(args.node_timeout_s),
                    "root_job_id": job_id,
                    "compute_receipt_hash": str(compute_receipt["receipt_hash"]),
                },
            }
            if emitter_node is not None and os.environ.get("SILICIUM_RAYTRACER_DIRECT_RESULT_RETURN", "") == "1":
                verify_payload["origin_result_return_url"] = emitter_node.public_url.rstrip("/") + "/results/dispatch"
            clear_previous_result(export_dir, verify_id)
            if args.node_mode == "network":
                submission = submit_network_task(args, export_dir, verify_payload, emitter_node)
            else:
                submission = submit_task(export_dir, verify_payload)
            submissions.append(submission)
            try:
                ensure_submission_success(submission)
            except RuntimeError as error:
                progress_fragments[index].update({"status": "verify_dispatch_failed", "error": str(error)})
                write_progress("verify_dispatch_failed")
                raise
            dispatch_ms = performance_duration((time.perf_counter() - dispatch_started) * 1000.0)
            progress_fragments[index]["status"] = "queued_verify"
            write_progress("verify_queued")
            return {
                "task_id": verify_id,
                "attempt": attempt,
                "challenge": challenge,
                "queue_deadline": time.monotonic() + args.result_timeout_s,
                "dispatch_ms": dispatch_ms,
                "result_wait_started": time.perf_counter(),
            }

        def poll_verify(
            context: dict[str, Any],
            _computed: dict[str, Any],
            token: dict[str, Any],
        ) -> dict[str, Any] | RetryFragmentStage | None:
            index = int(context["index"])
            verify_id = str(token["task_id"])
            try:
                deadline = refresh_attempt_deadline(export_dir, token, float(args.node_timeout_s))
                resolved = poll_task_result_attempts(
                    export_dir,
                    verify_id,
                    list(context.get("verify_late_task_ids", [])),
                    deadline,
                )
            except Exception as error:
                retry = retry_transient_stage(context, token, stage="verify", error=str(error))
                if retry is not None:
                    return retry
                progress_fragments[index].update({"status": "verify_failed", "error": str(error)})
                write_progress("verify_failed")
                raise
            if resolved is None:
                return None
            resolved_verify_id, verify_result = resolved
            token["resolved_task_id"] = resolved_verify_id
            result_wait_started = token.get("result_wait_started")
            if result_wait_started is not None:
                try:
                    token["result_wait_ms"] = performance_duration(
                        (time.perf_counter() - float(result_wait_started)) * 1000.0
                    )
                except (TypeError, ValueError):
                    token["result_wait_ms"] = 0.0
            verify_challenges = context.get("verify_challenges", {})
            if isinstance(verify_challenges, dict):
                token["resolved_challenge"] = verify_challenges.get(resolved_verify_id, token["challenge"])
            node_runs.append(
                {
                    "role": "verify",
                    "mode": "network",
                    "target_task_id": resolved_verify_id,
                    "target_result_ready": True,
                    "handled_by": verify_result.get("node_id", ""),
                }
            )
            if verify_result.get("success", True) is False:
                task_error, failed_node_id = task_failure_details(verify_result)
                retry = retry_transient_stage(
                    context,
                    token,
                    stage="verify",
                    error=task_error,
                    node_id=failed_node_id,
                )
                if retry is not None:
                    return retry
            return verify_result

        def finish_verify(
            context: dict[str, Any],
            _computed: dict[str, Any],
            token: dict[str, Any],
            verify_result: dict[str, Any],
        ) -> None:
            index = int(context["index"])
            fragment_id = str(context["fragment_id"])
            verify_id = str(token.get("resolved_task_id") or token["task_id"])
            try:
                ensure_task_success(verify_result, verify_id)
            except RuntimeError as error:
                progress_fragments[index].update({"status": "verify_failed", "error": str(error)})
                write_progress("verify_failed")
                raise
            verified = bool(verify_result.get("choice", verify_result.get("verified", False)))
            compute_receipt = _computed["compute_receipt"]
            receipt_attestation = validate_receipt_attestation(
                verify_result,
                str(compute_receipt["receipt_hash"]),
                verify_id,
            )
            verify_receipt = validate_compute_receipt(verify_result, verify_id)
            verify_performance = orchestration_performance_record("verify", context, token, verify_result)
            performance_records.append(verify_performance)
            if node_runs:
                node_runs[-1]["performance"] = verify_performance
            progress_fragments[index].update(
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
            write_progress("fragment_verified")
            if not verified:
                raise RuntimeError(f"raytracer fragment verification failed: {fragment_id}")

        # Task completion is signalled immediately by the scheduler's PUB
        # stream.  The next poll still reads the shared durable result, so a
        # missed ZeroMQ message can never lose work or alter correctness.
        event_listener = RpcTaskEventListener()
        try:
            run_bounded_fragment_pipeline(
                pipeline_fragments,
                max_compute_in_flight=compute_in_flight_limit,
                max_verify_in_flight=verify_in_flight_limit,
                launch_compute=launch_compute,
                poll_compute=poll_compute,
                launch_verify=launch_verify,
                poll_verify=poll_verify,
                finish_verify=finish_verify,
                idle=lambda: event_listener.wait(0.1),
            )
        finally:
            event_listener.close()

        reassembled_ppm = reassembled_dir / "render.ppm"
        reassembled_png = reassembled_dir / "render.png"
        reassemble_json = reassembled_dir / "reassemble.json"
        reassembled = reassemble_fragments(fragment_files, reassembled_ppm, reassembled_png, reassemble_json)
        for fragment in progress_fragments.values():
            fragment["status"] = "reassembled"
        accepted_fragments = [
            fragment
            for fragment in progress_fragments.values()
            if isinstance(fragment.get("receipt_attestation"), dict)
            and fragment["receipt_attestation"].get("accepted") is True
        ]
        receipt_hashes = [
            value
            for fragment in accepted_fragments
            for value in (
                str(fragment.get("compute_receipt_hash", "")),
                str(fragment.get("verify_receipt_hash", "")),
            )
            if value
        ]
        summary = {
            "schema_version": 1,
            "mode": "raytracer_network_job",
            "success": True,
            "job_id": job_id,
            "scene": str(scene_path),
            "job_dir": str(job_dir),
            "export_dir": str(export_dir),
            "image": {"width": width, "height": height},
            "split_policy": split.get("split_policy", {}),
            "fragment_count": len(fragments),
            "fragments": [progress_fragments[index] for index in sorted(progress_fragments)],
            "submissions": submissions,
            "node_runs": node_runs,
            "reassembled_ppm": str(reassembled_ppm),
            "reassembled_png": str(reassembled.get("result_png_path") or ""),
            "reassembled_png_ready": bool(reassembled.get("result_png_ready", False)),
            "reassembled_png_error": str(reassembled.get("result_png_error") or ""),
            "reassembled_hash": reassembled.get("result_sha256", sha256_file(reassembled_ppm)),
            "result_path": str(reassembled.get("result_png_path") or reassembled_ppm),
            "performance": build_performance_summary(
                performance_records,
                (time.perf_counter() - job_started) * 1000.0,
            ),
            "devnet_trace": {"enabled": False, "status": "not_requested"},
            "billing": {
                "schema": "silicium.verified-billing.v1",
                "billable_work_units": sum(
                    int(fragment.get("compute_billable_work_units", 0) or 0)
                    + int(fragment.get("verify_billable_work_units", 0) or 0)
                    for fragment in accepted_fragments
                ),
                "unit_policy": "deterministic rendered and sampled pixels; self-reported CPU is non-billable",
                "receipt_hashes": receipt_hashes,
                "receipt_set_hash": sha256_json(receipt_hashes),
            },
        }
        write_json(summary_path, summary)
        if args.devnet_trace:
            try:
                summary["devnet_trace"] = run_devnet_trace(args, summary_path)
                summary["devnet_trace"]["status"] = "submitted" if summary["devnet_trace"].get("ok") else "failed"
            except Exception as exc:
                summary["devnet_trace"] = {
                    "enabled": True,
                    "ok": False,
                    "status": "failed",
                    "error": str(exc),
                }
            write_json(summary_path, summary)
        write_progress("reassembled", success=True)
        print(json.dumps(summary, indent=2, sort_keys=True))
        if args.devnet_trace and not summary["devnet_trace"].get("ok"):
            return 3
        return 0
    finally:
        if emitter_node is not None:
            emitter_node.stop()


if __name__ == "__main__":
    raise SystemExit(main())
