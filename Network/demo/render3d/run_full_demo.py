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

from render3d_demo import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SCENE,
    NETWORK_ROOT,
    build_compute_payload,
    build_demo,
    build_verify_payload,
    submit_task,
    write_json,
)


class DemoError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def wait_for_result(export_dir: Path, task_id: str, timeout_s: float) -> dict[str, Any]:
    result_path = export_dir / f"result.{task_id}.json"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() <= deadline:
        if result_path.exists():
            return read_json(result_path)
        time.sleep(0.25)
    raise TimeoutError(f"missing result file after {timeout_s:.1f}s: {result_path}")


def result_path(export_dir: Path, task_id: str) -> Path:
    return export_dir / f"result.{task_id}.json"


def clear_previous_result(export_dir: Path, task_id: str) -> None:
    for prefix in ("result", "logs"):
        path = export_dir / f"{prefix}.{task_id}.json"
        if path.exists():
            path.unlink()


def find_openssl() -> Path | None:
    found = shutil.which("openssl")
    if found:
        return Path(found)
    if os.name != "nt":
        return None

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        Path(program_files) / "OpenSSL-Win64" / "bin" / "openssl.exe",
        Path(program_files) / "OpenSSL-Win32" / "bin" / "openssl.exe",
        Path(program_files_x86) / "OpenSSL-Win32" / "bin" / "openssl.exe",
        Path(program_files) / "Git" / "usr" / "bin" / "openssl.exe",
        Path(program_files_x86) / "Git" / "usr" / "bin" / "openssl.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def node_environment() -> dict[str, str]:
    env = os.environ.copy()
    openssl = find_openssl()
    if openssl is not None:
        openssl_dir = str(openssl.parent)
        path = env.get("PATH", "")
        parts = [part for part in path.split(os.pathsep) if part]
        if openssl_dir not in parts:
            env["PATH"] = openssl_dir + os.pathsep + path
    return env


def run_inline_node_pass(args: argparse.Namespace, role: str, task_id: str, fallback_error: str = "") -> dict[str, Any]:
    sys.path.insert(0, str(NETWORK_ROOT))
    from tools.network_node import (
        NodeConfig,
        P2PClient,
        RoleRuntime,
        atomic_write_json,
        sha256_bytes,
        sha256_json,
        stable_json,
        utc_now,
    )

    export_dir = Path(args.export_dir).resolve()
    state_dir = (Path(args.output_root).resolve() / "_inline_node_state" / role).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    config = NodeConfig(
        export_dir=export_dir,
        roles={role},
        node_id=f"demo-render3d-inline-{role}",
        idle_ms=0,
        once=True,
        max_items=1,
        p2p_gateway=args.p2p_gateway,
        state_dir=state_dir,
        solana_enable=False,
        solana_rpc="https://api.devnet.solana.com",
        solana_program_id="",
        solana_wallet="",
        solana_bridge=NETWORK_ROOT / "tools" / "solana_layer_bridge.cjs",
        solana_timeout_s=45,
        max_retries=0,
        worker_binary="",
        worker_mode="demo",
        bootstrap_worker=False,
        gossip_enable=False,
        gossip_bind="127.0.0.1",
        gossip_port=0,
        peer_http_bind="127.0.0.1",
        peer_http_port=0,
        peer_advertise_host="127.0.0.1",
        peer_advertise_port=0,
        gossip_advertise_host="127.0.0.1",
        gossip_advertise_port=0,
        seed_peers=[],
        mesh_key="",
        peer_sync_interval_s=0,
        peer_event_limit=0,
        peer_stale_after_s=0,
        relay_enable=False,
        relay_hops=0,
        identity_key_path="",
        reputation_score=0.0,
        replication_factor=0,
        replication_quorum=0,
        discovery_seeds=[],
        discovery_sync_interval_s=0,
        remote_dispatch_enable=False,
        remote_dispatch_limit=0,
        nat_punch_enable=False,
        solana_reputation_enable=False,
        solana_reputation_refresh_s=0,
        scheduler_onchain_weight=0.0,
        scheduler_offchain_weight=1.0,
        scheduler_capacity_weight=0.0,
    )
    envelope_path = export_dir / "tasks" / f"{task_id}.json"
    envelope = read_json(envelope_path)
    task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
    p2p = P2PClient(args.p2p_gateway, export_dir)
    runtime = RoleRuntime(config, p2p)

    started = time.monotonic()
    p2p_data, p2p_meta = p2p.fetch(envelope.get("p2p_ref"))
    role_output = runtime.run_task(envelope, task, p2p_data, p2p_meta)
    result = {
        "success": True,
        "envelope_kind": "task",
        "task_id": task_id,
        "required_roles": envelope.get("required_roles", []),
        "priority": envelope.get("priority", "normal"),
        "input": p2p_meta,
        "input_hash": sha256_bytes(p2p_data),
        **role_output,
    }
    result["result_hash"] = str(role_output.get("result_hash") or sha256_json(result))
    result["proof_ref"] = p2p.put_local(stable_json(result).encode("utf-8"))
    result.update(
        {
            "schema_version": 1,
            "node_id": config.node_id,
            "roles": sorted(config.roles),
            "finished_utc": utc_now(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    )
    log_payload = {
        "schema_version": 1,
        "item_id": task_id,
        "ok": True,
        "error": "",
        "duration_ms": result["duration_ms"],
    }
    atomic_write_json(export_dir / f"result.{task_id}.json", result)
    atomic_write_json(export_dir / f"logs.{task_id}.json", log_payload)
    envelope["status"] = "completed"
    envelope["handled_by"] = config.node_id
    envelope["handled_utc"] = result["finished_utc"]
    envelope["result_hash"] = result["result_hash"]
    envelope["result_resource"] = f"resources://silicium/results/by-task/{task_id}"
    atomic_write_json(envelope_path, envelope)
    return {
        "role": role,
        "mode": "inline",
        "fallback_error": fallback_error[-1200:],
        "returncode": 0,
        "stdout_tail": "",
        "stderr_tail": "",
    }


def run_cli_node_once(args: argparse.Namespace, role: str) -> dict[str, Any]:
    openssl = find_openssl()
    if openssl is None:
        raise DemoError(
            "OpenSSL is required for --node-mode cli because the signed P2P node identity uses it. "
            "Run: .\\start-silicium-windows.cmd -InstallSystemDeps -SkipDashboard -SkipWorldNode"
        )

    command = [
        sys.executable,
        str(NETWORK_ROOT / "silicium"),
        "node",
        "start",
        "--once",
        "--max-items",
        "1",
        "--roles",
        role,
        "--node-id",
        f"demo-render3d-{role}",
        "--export-dir",
        str(Path(args.export_dir).resolve()),
        "--state-dir",
        str((Path(args.output_root).resolve() / "_node_state" / role).resolve()),
        "--p2p-gateway",
        args.p2p_gateway,
    ]
    if args.solana_enable:
        command.append("--solana-enable")
    completed = subprocess.run(
        command,
        cwd=str(NETWORK_ROOT),
        text=True,
        capture_output=True,
        timeout=args.node_timeout_s,
        env=node_environment(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "node pass failed for role "
            + role
            + "\nstdout:\n"
            + completed.stdout[-4000:]
            + "\nstderr:\n"
            + completed.stderr[-4000:]
        )
    return {
        "role": role,
        "mode": "cli",
        "openssl": str(openssl),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def compact_error(message: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return ""
    for line in reversed(lines):
        if "FileNotFoundError" in line or "openssl" in line:
            return line[:500]
    return lines[-1][:500]


def run_node_once(args: argparse.Namespace, role: str, task_id: str) -> dict[str, Any]:
    if args.node_mode == "inline":
        return run_inline_node_pass(args, role, task_id)
    try:
        return run_cli_node_once(args, role)
    except RuntimeError as exc:
        message = str(exc)
        if args.node_mode == "auto" and ("openssl" in message or "FileNotFoundError" in message):
            return run_inline_node_pass(args, role, task_id, compact_error(message))
        raise


def run_node_until_result(args: argparse.Namespace, role: str, task_id: str, node_runs: list[dict[str, Any]]) -> dict[str, Any]:
    export_dir = Path(args.export_dir).resolve()
    deadline = time.monotonic() + args.result_timeout_s
    attempts = 0
    while time.monotonic() <= deadline and attempts < args.node_sweeps:
        if result_path(export_dir, task_id).exists():
            return read_json(result_path(export_dir, task_id))
        attempts += 1
        run = run_node_once(args, role, task_id)
        run["target_task_id"] = task_id
        run["sweep"] = attempts
        run["target_result_ready"] = result_path(export_dir, task_id).exists()
        node_runs.append(run)
        if run["target_result_ready"]:
            return read_json(result_path(export_dir, task_id))
        time.sleep(0.25)
    raise TimeoutError(
        f"missing result file after {attempts} node sweep(s) and {args.result_timeout_s:.1f}s: "
        f"{result_path(export_dir, task_id)}"
    )


def output_ref_from_compute(result: dict[str, Any]) -> dict[str, Any]:
    ref = result.get("output_ref")
    if not isinstance(ref, dict):
        raise ValueError("compute result does not contain output_ref")
    return ref


def result_hash_from_compute(result: dict[str, Any]) -> str:
    raw = str(result.get("result_hash") or "")
    if not raw:
        raise ValueError("compute result does not contain result_hash")
    return raw.removeprefix("sha256:")


def command_run(args: argparse.Namespace) -> int:
    scene_path = Path(args.scene).resolve()
    task_id = args.task_id or f"render3d-full-{int(time.time())}"
    output_root = Path(args.output_root).resolve()
    export_dir = Path(args.export_dir).resolve()
    priority = args.priority

    manifest = build_demo(scene_path, output_root, task_id)
    job_dir = Path(manifest["result_path"]).parents[1]
    compute_payload = build_compute_payload(manifest, priority)
    write_json(job_dir / "compute-task.json", compute_payload)
    clear_previous_result(export_dir, task_id)
    compute_submission = submit_task(export_dir, compute_payload)

    node_runs = []
    compute_result = run_node_until_result(args, "compute", task_id, node_runs)

    verify_payload = build_verify_payload(
        manifest,
        compute_payload,
        output_ref_from_compute(compute_result),
        result_hash_from_compute(compute_result),
        priority,
    )
    write_json(job_dir / "verify-task.json", verify_payload)
    verify_task_id = str(verify_payload["task_id"])
    clear_previous_result(export_dir, verify_task_id)
    verify_submission = submit_task(export_dir, verify_payload)

    verify_result = run_node_until_result(args, "verify", verify_task_id, node_runs)

    summary = {
        "schema_version": 1,
        "task_id": task_id,
        "verify_task_id": verify_task_id,
        "scene": str(scene_path),
        "job_dir": str(job_dir),
        "export_dir": str(export_dir),
        "manifest": manifest,
        "submissions": {
            "compute": compute_submission,
            "verify": verify_submission,
        },
        "node_runs": node_runs,
        "compute_result_file": str((export_dir / f"result.{task_id}.json").resolve()),
        "verify_result_file": str((export_dir / f"result.{verify_task_id}.json").resolve()),
        "compute_output_ref": output_ref_from_compute(compute_result),
        "compute_result_hash": result_hash_from_compute(compute_result),
        "verify_choice": bool(verify_result.get("choice", False)),
        "verify_recomputed_hash": verify_result.get("recomputed_hash", ""),
        "success": bool(compute_result.get("success", False)) and bool(verify_result.get("choice", False)),
    }
    write_json(job_dir / "full-demo-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["success"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the manual render3d demo end-to-end through the Silicium node queue."
    )
    parser.add_argument("scene", nargs="?", default=str(DEFAULT_SCENE))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--priority", default="high", choices=["low", "normal", "high", "urgent"])
    parser.add_argument("--p2p-gateway", default="http://127.0.0.1:5001")
    parser.add_argument("--node-mode", default="auto", choices=["auto", "cli", "inline"])
    parser.add_argument("--node-sweeps", type=int, default=12)
    parser.add_argument("--result-timeout-s", type=float, default=20.0)
    parser.add_argument("--node-timeout-s", type=float, default=60.0)
    parser.add_argument("--solana-enable", action="store_true")
    parser.set_defaults(func=command_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except DemoError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
