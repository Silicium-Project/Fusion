from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

NETWORK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NETWORK_ROOT))
sys.path.insert(0, str(NETWORK_ROOT / "demo"))

from networked.networked_runtime import (  # noqa: E402
    NetworkedOrchestrator,
    fetch_network_content,
    store_network_content,
    store_network_file,
    wait_for_result as wait_for_network_result,
)
from workloads.common import (  # noqa: E402
    clear_previous_result,
    default_solana_wallet_path,
    output_ref_from_compute,
    p2p_file_path,
    resolve_solana_wallet,
    result_hash_from_compute,
    sha256_bytes,
    sha256_file,
    submit_task,
    write_json,
)
from workloads.raytracer.raytracer_workload import scene_resolution  # noqa: E402


def run_node_until_result(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise RuntimeError("local node sweeps are not supported by the raytracer workload; use --node-mode network")

RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD = "calcul/rendering/raytracer-fragment"
RAYTRACER_FRAGMENT_VERIFY_WORKLOAD = "verification/rendering/raytracer-fragment"


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
    parser.add_argument("--network-node-id", default="raytracer-orchestrator")
    parser.add_argument("--network-bind", default="0.0.0.0")
    parser.add_argument("--network-port", type=int, default=46100)
    parser.add_argument("--network-advertise-host", default="127.0.0.1")
    parser.add_argument("--network-advertise-port", type=int, default=46100)
    parser.add_argument("--network-seed-peers", default="")
    parser.add_argument("--network-mesh-key", default=os.environ.get("SILICIUM_MESH_KEY", "demo-mesh"))
    parser.add_argument("--network-start-orchestrator", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--network-role-timeout-s", type=float, default=float(os.environ.get("SILICIUM_NETWORK_ROLE_TIMEOUT_S", "60")))
    parser.add_argument("--min-compute-reputation", type=float, default=float(os.environ.get("SILICIUM_MIN_COMPUTE_REPUTATION", "0")))
    parser.add_argument("--min-verify-reputation", type=float, default=float(os.environ.get("SILICIUM_MIN_VERIFY_REPUTATION", "0")))
    parser.add_argument("--solana-enable", action="store_true")
    parser.add_argument("--devnet-trace", action="store_true")
    parser.add_argument("--devnet-trace-timeout-s", type=float, default=420.0)
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.environ.get("ANCHOR_WALLET", "")))
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument("--solana-program-id", default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA"))
    parser.add_argument("--devnet-tx-delay-ms", type=int, default=int(os.environ.get("SILICIUM_DEVNET_TX_DELAY_MS", "1200")))
    return parser


def wait_for_task_result(args: argparse.Namespace, role: str, task_id: str, node_runs: list[dict[str, Any]]) -> dict[str, Any]:
    if args.node_mode == "network":
        export_dir = Path(args.export_dir).resolve()
        result = wait_for_network_result(export_dir, task_id, args.result_timeout_s)
        node_runs.append(
            {
                "role": role,
                "mode": "network",
                "target_task_id": task_id,
                "target_result_ready": True,
                "handled_by": result.get("node_id", ""),
            }
        )
        return result
    return run_node_until_result(args, role, task_id, node_runs)


def poll_task_result(args: argparse.Namespace, role: str, task_id: str, node_runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if args.node_mode != "network":
        return None
    export_dir = Path(args.export_dir).resolve()
    result_path = export_dir / f"result.{task_id}.json"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if isinstance(result, dict):
            node_runs.append(
                {
                    "role": role,
                    "mode": "network",
                    "target_task_id": task_id,
                    "target_result_ready": True,
                    "handled_by": result.get("node_id", ""),
                }
            )
            return result
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
    return None


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


def portable_network_ref(ref: dict[str, Any]) -> dict[str, Any]:
    shared = ref.get("shared_ref") if isinstance(ref, dict) else None
    if isinstance(shared, dict) and str(shared.get("protocol", "")).lower() == "silicium":
        return shared
    return ref


def orchestrator_pinned_ref(args: argparse.Namespace, export_dir: Path, data: bytes) -> dict[str, Any]:
    if args.node_mode == "network":
        return store_network_content(export_dir, data, args.network_node_id)
    digest = sha256_bytes(data)
    path = export_dir / "p2p" / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return {"protocol": "file", "content_id": str(path), "hash": "sha256:" + digest}


def ensure_task_success(result: dict[str, Any], task_id: str) -> None:
    if result.get("success", True) is not False:
        return
    error = str(result.get("error") or result.get("last_error") or "unknown_error")
    node_id = str(result.get("node_id") or "")
    raise RuntimeError(f"task failed: {task_id} on {node_id}\n{error}")


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
    script = NETWORK_ROOT / "workloads" / "raytracer" / "split.py"
    cmd = [
        sys.executable,
        str(script),
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


def reassemble_fragments(fragment_files: list[tuple[int, Path]], output_ppm: Path, output_png: Path, result_json: Path) -> dict[str, Any]:
    script = NETWORK_ROOT / "workloads" / "raytracer" / "reassemble.py"
    cmd = [sys.executable, str(script)]
    for y_start, fragment_file in sorted(fragment_files, key=lambda item: item[0]):
        cmd.extend(["--fragment", str(fragment_file), "--y-start", str(y_start)])
    cmd.extend(["--output", str(output_ppm), "--png", str(output_png), "--result-json", str(result_json)])
    completed = subprocess.run(cmd, text=True, capture_output=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"raytracer_reassemble_failed:{completed.stderr[-2048:]}")
    return json.loads(result_json.read_text(encoding="utf-8"))


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
    return {
        "enabled": True,
        "ok": completed.returncode == 0,
        "trace_path": str(trace_path),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4096:],
        "stderr_tail": completed.stderr[-4096:],
        "trace": trace,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scene_path = Path(args.scene).resolve()
    width, height = scene_resolution(scene_path)
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

    local_scene = input_dir / "scene.cfg"
    shutil.copy2(scene_path, local_scene)
    split_path = job_dir / "raytracer-split.json"
    summary_path = job_dir / "raytracer-summary.json"
    progress_path = job_dir / "raytracer-progress.json"
    split = make_split(args, local_scene, split_path)
    fragments = list(split.get("fragments", []))

    node_runs: list[dict[str, Any]] = []
    submissions: list[dict[str, Any]] = []
    orchestrator_result: dict[str, Any] = {"enabled": False}
    progress_fragments = {
        int(fragment["fragment_index"]): {**fragment, "status": "planned"}
        for fragment in fragments
    }
    started_unix = time.time()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_unix))

    def write_progress(stage: str, success: bool = False) -> None:
        now_unix = time.time()
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
                "started_utc": started_utc,
                "started_unix": started_unix,
                "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_unix)),
                "updated_unix": now_unix,
                "elapsed_s": round(now_unix - started_unix, 3),
                "image": {"width": width, "height": height},
                "split_policy": split.get("split_policy", {}),
                "fragment_count": len(fragments),
                "fragments": [progress_fragments[index] for index in sorted(progress_fragments)],
                "submissions": submissions,
                "node_runs": node_runs,
                "network": orchestrator_result,
            },
        )

    orchestrator: NetworkedOrchestrator | None = None
    if args.node_mode == "network" and args.network_start_orchestrator:
        if not args.network_mesh_key:
            raise RuntimeError("--network-mesh-key is required for network mode content fetches")
        orchestrator = NetworkedOrchestrator(
            export_dir=export_dir,
            state_dir=job_dir / "_orchestrator_state",
            node_id=args.network_node_id,
            bind=args.network_bind,
            port=args.network_port,
            advertise_host=args.network_advertise_host,
            advertise_port=args.network_advertise_port,
            seed_peers=args.network_seed_peers,
            mesh_key=args.network_mesh_key,
        )
        orchestrator.start()
        orchestrator_result = {
            "enabled": True,
            "node_id": args.network_node_id,
            "public_url": orchestrator.public_url,
            "seed_peers": args.network_seed_peers,
        }
        wait_for_network_role(export_dir, args.network_node_id, "compute", args.network_role_timeout_s)
        wait_for_network_role(export_dir, args.network_node_id, "verify", args.network_role_timeout_s)

    try:
        scene_ref = task_input_ref(args, export_dir, local_scene)
        write_progress("split_ready")
        fragment_files: list[tuple[int, Path]] = []
        compute_jobs: list[dict[str, Any]] = []
        computed_fragments: list[dict[str, Any]] = []
        verify_jobs: list[dict[str, Any]] = []

        for fragment in fragments:
            index = int(fragment["fragment_index"])
            y_start = int(fragment["y_start"])
            y_end = int(fragment["y_end"])
            fragment_id = f"{job_id}-frag-{index:03d}"
            spec = {
                "fragment_index": index,
                "fragment_count": len(fragments),
                "y_start": y_start,
                "y_end": y_end,
                "scene_p2p_ref": scene_ref,
            }
            progress_fragments[index]["status"] = "queued_compute"
            fairness_until_unix = time.time() + min(120.0, max(30.0, float(args.result_timeout_s) * 0.5))
            compute_payload = {
                "task_id": fragment_id,
                "required_roles": ["compute"],
                "priority": args.priority,
                "fairness_until_unix": fairness_until_unix,
                "p2p_ref": bytes_input_ref(args, export_dir, json.dumps(spec, sort_keys=True).encode("utf-8")),
                "task": {
                    "kind": "compute",
                    "workload": RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD,
                    "fairness_until_unix": fairness_until_unix,
                    "fragment_index": index,
                    "fragment_count": len(fragments),
                    "y_start": y_start,
                    "y_end": y_end,
                    "scene_p2p_ref": scene_ref,
                    "timeout_s": int(args.node_timeout_s),
                },
            }
            clear_previous_result(export_dir, fragment_id)
            submissions.append(submit_task(export_dir, compute_payload))
            compute_jobs.append(
                {
                    "index": index,
                    "y_start": y_start,
                    "y_end": y_end,
                    "fragment_id": fragment_id,
                }
            )
        write_progress("compute_queued")

        pending_compute = {str(job["fragment_id"]): dict(job) for job in compute_jobs}
        pending_verify: dict[str, dict[str, Any]] = {}
        verified_indexes: set[int] = set()
        deadline = time.monotonic() + float(args.result_timeout_s)

        while len(verified_indexes) < len(fragments):
            made_progress = False
            for fragment_id, job in list(pending_compute.items()):
                compute_result = poll_task_result(args, "compute", fragment_id, node_runs)
                if compute_result is None:
                    continue
                made_progress = True
                index = int(job["index"])
                y_start = int(job["y_start"])
                y_end = int(job["y_end"])
                try:
                    ensure_task_success(compute_result, fragment_id)
                except RuntimeError as error:
                    progress_fragments[index].update({"status": "compute_failed", "error": str(error)})
                    write_progress("compute_failed")
                    raise
                output_ref = output_ref_from_compute(compute_result)
                result_hash = result_hash_from_compute(compute_result)
                fragment_file = fragments_dir / f"fragment-{index:03d}.ppm"
                fragment_bytes = read_ref_bytes(args, export_dir, output_ref)
                fragment_file.write_bytes(fragment_bytes)
                fragment_files.append((y_start, fragment_file))
                verify_ref = orchestrator_pinned_ref(args, export_dir, fragment_bytes)
                progress_fragments[index].update(
                    {
                        "status": "computed",
                        "result_hash": result_hash,
                        "output_ref": output_ref,
                        "verify_ref": verify_ref,
                        "expected_hash": result_hash,
                        "compute_result_hash": result_hash,
                        "compute_output_ref": output_ref,
                        "compute_node_id": compute_result.get("node_id", ""),
                    }
                )
                computed_fragments.append(
                    {
                        "index": index,
                        "y_start": y_start,
                        "y_end": y_end,
                        "fragment_id": fragment_id,
                        "output_ref": verify_ref,
                        "result_hash": result_hash,
                        "compute_node_id": compute_result.get("node_id", ""),
                    }
                )
                verify_id = f"{fragment_id}-verify"
                verify_fallback_until_unix = time.time() + min(120.0, max(45.0, float(args.result_timeout_s) * 0.5))
                verify_fairness_until_unix = time.time() + min(120.0, max(30.0, float(args.result_timeout_s) * 0.5))
                verify_payload = {
                    "task_id": verify_id,
                    "required_roles": ["verify"],
                    "excluded_node_ids": [str(compute_result.get("node_id") or "")],
                    "excluded_until_unix": verify_fallback_until_unix,
                    "fairness_until_unix": verify_fairness_until_unix,
                    "priority": args.priority,
                    "p2p_ref": verify_ref,
                    "expected_hash": "sha256:" + result_hash.removeprefix("sha256:"),
                    "scene_p2p_ref": scene_ref,
                    "task": {
                        "kind": "verify",
                        "workload": RAYTRACER_FRAGMENT_VERIFY_WORKLOAD,
                        "expected_hash": "sha256:" + result_hash.removeprefix("sha256:"),
                        "scene_p2p_ref": scene_ref,
                        "source_task_id": fragment_id,
                        "excluded_node_ids": [str(compute_result.get("node_id") or "")],
                        "excluded_until_unix": verify_fallback_until_unix,
                        "fairness_until_unix": verify_fairness_until_unix,
                        "fragment_index": index,
                        "fragment_count": len(fragments),
                        "y_start": y_start,
                        "y_end": y_end,
                        "timeout_s": int(args.node_timeout_s),
                    },
                }
                clear_previous_result(export_dir, verify_id)
                submissions.append(submit_task(export_dir, verify_payload))
                progress_fragments[index]["status"] = "queued_verify"
                verify_jobs.append({"index": index, "fragment_id": fragment_id, "verify_id": verify_id})
                pending_verify[verify_id] = {"index": index, "fragment_id": fragment_id, "verify_id": verify_id}
                pending_compute.pop(fragment_id, None)
                write_progress("verify_queued")

            for verify_id, job in list(pending_verify.items()):
                verify_result = poll_task_result(args, "verify", verify_id, node_runs)
                if verify_result is None:
                    continue
                made_progress = True
                index = int(job["index"])
                fragment_id = str(job["fragment_id"])
                try:
                    ensure_task_success(verify_result, verify_id)
                except RuntimeError as error:
                    progress_fragments[index].update({"status": "verify_failed", "error": str(error)})
                    write_progress("verify_failed")
                    raise
                verified = bool(verify_result.get("choice", verify_result.get("verified", False)))
                progress_fragments[index].update(
                    {
                        "status": "verified" if verified else "verify_failed",
                        "verify_id": verify_id,
                        "verify_choice": verified,
                        "verify_recomputed_hash": verify_result.get("recomputed_hash", ""),
                        "verify_node_id": verify_result.get("node_id", ""),
                    }
                )
                pending_verify.pop(verify_id, None)
                write_progress("fragment_verified")
                if not verified:
                    raise RuntimeError(f"raytracer fragment verification failed: {fragment_id}")
                verified_indexes.add(index)

            if len(verified_indexes) >= len(fragments):
                break
            if time.monotonic() >= deadline:
                pending = sorted(list(pending_compute.keys()) + list(pending_verify.keys()))
                for task_id, job in pending_compute.items():
                    progress_fragments[int(job["index"])].update(
                        {"status": "compute_timeout", "error": f"timeout waiting for {task_id}"}
                    )
                for task_id, job in pending_verify.items():
                    progress_fragments[int(job["index"])].update(
                        {"status": "verify_timeout", "error": f"timeout waiting for {task_id}"}
                    )
                write_progress("pipeline_timeout")
                raise TimeoutError(
                    f"raytracer network pipeline timed out after {args.result_timeout_s:.1f}s; pending: {', '.join(pending)}"
                )
            if not made_progress:
                write_progress("pipeline_running")
                time.sleep(0.25)

        reassembled_ppm = reassembled_dir / "render.ppm"
        reassembled_png = reassembled_dir / "render.png"
        reassemble_json = reassembled_dir / "reassemble.json"
        reassembled = reassemble_fragments(fragment_files, reassembled_ppm, reassembled_png, reassemble_json)
        for fragment in progress_fragments.values():
            fragment["status"] = "reassembled"
        completed_unix = time.time()
        summary = {
            "schema_version": 1,
            "mode": "raytracer_network_job",
            "success": True,
            "job_id": job_id,
            "scene": str(scene_path),
            "job_dir": str(job_dir),
            "export_dir": str(export_dir),
            "started_utc": started_utc,
            "started_unix": started_unix,
            "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(completed_unix)),
            "completed_unix": completed_unix,
            "elapsed_s": round(completed_unix - started_unix, 3),
            "image": {"width": width, "height": height},
            "split_policy": split.get("split_policy", {}),
            "fragment_count": len(fragments),
            "fragments": [progress_fragments[index] for index in sorted(progress_fragments)],
            "submissions": submissions,
            "node_runs": node_runs,
            "reassembled_ppm": str(reassembled_ppm),
            "reassembled_png": str(reassembled_png),
            "reassembled_hash": reassembled.get("result_sha256", sha256_file(reassembled_ppm)),
            "devnet_trace": {"enabled": False, "status": "not_requested"},
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
        if orchestrator is not None:
            orchestrator.stop()


if __name__ == "__main__":
    raise SystemExit(main())
