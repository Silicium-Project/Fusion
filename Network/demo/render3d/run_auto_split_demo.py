from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from render3d_demo import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SCENE,
    NETWORK_ROOT,
    load_scene,
    ppm_to_png_bytes,
    render_scene,
    sha256_bytes,
    sha256_file,
    submit_task,
    write_json,
)
from run_fragmented_demo import (
    FRAGMENT_COMPUTE_WORKLOAD,
    FRAGMENT_VERIFY_WORKLOAD,
    default_solana_wallet_path,
    image_size,
    p2p_file_path,
    read_p6_ppm,
    resolve_solana_wallet,
    write_p6_ppm,
)
from run_full_demo import clear_previous_result, output_ref_from_compute, result_hash_from_compute, run_node_until_result


@dataclass
class SplitNode:
    fragment_index: int
    y_start: int
    y_end: int
    depth: int
    complexity_score: int
    parent_index: int | None = None
    children: list["SplitNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


def estimate_render_complexity(scene: dict[str, Any], width: int, y_start: int, y_end: int) -> int:
    objects = scene.get("objects") if isinstance(scene.get("objects"), list) else []
    sphere_count = sum(1 for obj in objects if isinstance(obj, dict) and obj.get("type") == "sphere")
    object_factor = max(1, sphere_count)
    return max(1, width * max(1, y_end - y_start) * object_factor)


def build_split_tree(
    scene: dict[str, Any],
    width: int,
    y_start: int,
    y_end: int,
    threshold: int,
    max_depth: int,
    next_index: list[int],
    parent_index: int | None = None,
    depth: int = 0,
) -> SplitNode:
    fragment_index = next_index[0]
    next_index[0] += 1
    complexity = estimate_render_complexity(scene, width, y_start, y_end)
    node = SplitNode(
        fragment_index=fragment_index,
        parent_index=parent_index,
        y_start=y_start,
        y_end=y_end,
        depth=depth,
        complexity_score=complexity,
    )
    can_split = complexity > threshold and depth < max_depth and (y_end - y_start) >= 2
    if can_split:
        mid = (y_start + y_end) // 2
        node.children = [
            build_split_tree(scene, width, y_start, mid, threshold, max_depth, next_index, fragment_index, depth + 1),
            build_split_tree(scene, width, mid, y_end, threshold, max_depth, next_index, fragment_index, depth + 1),
        ]
    return node


def flatten_tree(root: SplitNode) -> list[SplitNode]:
    out = [root]
    for child in root.children:
        out.extend(flatten_tree(child))
    return out


def leaf_nodes(root: SplitNode) -> list[SplitNode]:
    return [node for node in flatten_tree(root) if node.is_leaf]


def tree_to_dict(node: SplitNode) -> dict[str, Any]:
    return {
        "fragment_index": node.fragment_index,
        "parent_index": node.parent_index,
        "y_start": node.y_start,
        "y_end": node.y_end,
        "depth": node.depth,
        "complexity_score": node.complexity_score,
        "is_leaf": node.is_leaf,
        "children": [tree_to_dict(child) for child in node.children],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run render3d with recursive network-style auto split.")
    parser.add_argument("scene", nargs="?", default=str(DEFAULT_SCENE))
    parser.add_argument("--job-id", "--task-id", dest="job_id", default="")
    parser.add_argument("--complexity-threshold", type=int, default=60_000)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--export-dir", default="", help="Defaults to an isolated export folder inside the job directory.")
    parser.add_argument("--reuse-job-dir", action="store_true")
    parser.add_argument("--priority", default="high", choices=["low", "normal", "high", "urgent"])
    parser.add_argument("--p2p-gateway", default="http://127.0.0.1:5001")
    parser.add_argument("--node-mode", default="auto", choices=["auto", "cli", "inline"])
    parser.add_argument("--node-sweeps", type=int, default=30)
    parser.add_argument("--result-timeout-s", type=float, default=60.0)
    parser.add_argument("--node-timeout-s", type=float, default=60.0)
    parser.add_argument("--solana-enable", action="store_true", help="Forward on-chain operations through the node when envelopes provide on_chain metadata.")
    parser.add_argument("--devnet-trace", action="store_true")
    parser.add_argument("--devnet-trace-timeout-s", type=float, default=420.0)
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.environ.get("ANCHOR_WALLET", "")))
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument("--solana-program-id", default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"))
    parser.add_argument("--devnet-tx-delay-ms", type=int, default=int(os.environ.get("SILICIUM_DEVNET_TX_DELAY_MS", "1200")))
    return parser


def run_devnet_trace(args: argparse.Namespace, summary_path: Path) -> dict[str, Any]:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx_not_found")
    wallet_path = resolve_solana_wallet(args.solana_wallet)
    if not wallet_path.exists():
        raise RuntimeError(
            "solana_wallet_not_found:"
            + str(wallet_path)
            + " | Create one with: .\\demo\\render3d\\prepare-devnet-wallet.cmd"
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
        [npx, "ts-node", "scripts/devnet_trace_render3d_fragments.ts", str(summary_path)],
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
    scene = load_scene(scene_path)
    width, height = image_size(scene)
    job_id = args.job_id or f"render-auto-split-{int(time.time())}"
    output_root = Path(args.output_root).resolve()
    job_dir = output_root / job_id
    if job_dir.exists() and any(job_dir.iterdir()) and not args.reuse_job_dir:
        raise RuntimeError(
            f"demo job directory already exists: {job_dir}\n"
            "Use a new --job-id for a fresh demo, or pass --reuse-job-dir intentionally."
        )
    export_dir = Path(args.export_dir).resolve() if args.export_dir else (job_dir / "export").resolve()
    args.export_dir = str(export_dir)

    input_dir = job_dir / "input"
    expected_dir = job_dir / "expected-fragments"
    reassembled_dir = job_dir / "reassembled"
    input_dir.mkdir(parents=True, exist_ok=True)
    expected_dir.mkdir(parents=True, exist_ok=True)
    reassembled_dir.mkdir(parents=True, exist_ok=True)

    scene_copy = input_dir / "scene.json"
    scene_copy.write_text(scene_path.read_text(encoding="utf-8"), encoding="utf-8")
    scene_ref = {
        "protocol": "file",
        "content_id": str(scene_copy),
        "hash": "sha256:" + sha256_file(scene_copy),
    }

    full_ppm = render_scene(scene)
    expected_full_hash = sha256_bytes(full_ppm)
    (job_dir / "expected-full.ppm").write_bytes(full_ppm)
    (job_dir / "expected-full.png").write_bytes(ppm_to_png_bytes(full_ppm))

    root = build_split_tree(
        scene,
        width,
        0,
        height,
        max(1, args.complexity_threshold),
        max(0, args.max_depth),
        [0],
    )
    leaves = sorted(leaf_nodes(root), key=lambda node: (node.y_start, node.fragment_index))
    node_runs: list[dict[str, Any]] = []
    submissions: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []

    for node in leaves:
        fragment_id = f"{job_id}-frag-{node.fragment_index:03d}"
        fragment_ppm = render_scene(scene, node.y_start, node.y_end)
        expected_path = expected_dir / f"fragment-{node.fragment_index:03d}.ppm"
        expected_path.write_bytes(fragment_ppm)
        expected_hash = sha256_bytes(fragment_ppm)
        spec = {
            "schema_version": 1,
            "job_id": job_id,
            "fragment_index": node.fragment_index,
            "parent_index": node.parent_index,
            "fragment_count": len(leaves),
            "y_start": node.y_start,
            "y_end": node.y_end,
            "depth": node.depth,
            "complexity_score": node.complexity_score,
            "scene_p2p_ref": scene_ref,
            "expected_result_sha256": expected_hash,
        }
        spec_path = input_dir / f"fragment-{node.fragment_index:03d}.json"
        write_json(spec_path, spec)
        compute_payload = {
            "task_id": fragment_id,
            "required_roles": ["compute"],
            "priority": args.priority,
            "p2p_ref": {
                "protocol": "file",
                "content_id": str(spec_path),
                "hash": "sha256:" + sha256_file(spec_path),
            },
            "task": {
                "kind": "compute",
                "workload": FRAGMENT_COMPUTE_WORKLOAD,
                **spec,
            },
        }
        clear_previous_result(export_dir, fragment_id)
        submissions.append(submit_task(export_dir, compute_payload))
        compute_result = run_node_until_result(args, "compute", fragment_id, node_runs)

        verify_id = f"{fragment_id}-verify"
        verify_payload = {
            "task_id": verify_id,
            "required_roles": ["verify"],
            "priority": args.priority,
            "p2p_ref": output_ref_from_compute(compute_result),
            "task": {
                "kind": "verify",
                "workload": FRAGMENT_VERIFY_WORKLOAD,
                "expected_hash": "sha256:" + result_hash_from_compute(compute_result),
                "scene_p2p_ref": scene_ref,
                "source_task_id": fragment_id,
                "fragment_index": node.fragment_index,
                "parent_index": node.parent_index,
                "fragment_count": len(leaves),
                "y_start": node.y_start,
                "y_end": node.y_end,
                "depth": node.depth,
                "complexity_score": node.complexity_score,
            },
        }
        clear_previous_result(export_dir, verify_id)
        submissions.append(submit_task(export_dir, verify_payload))
        verify_result = run_node_until_result(args, "verify", verify_id, node_runs)
        fragments.append(
            {
                "fragment_id": fragment_id,
                "verify_id": verify_id,
                "fragment_index": node.fragment_index,
                "parent_index": node.parent_index,
                "y_start": node.y_start,
                "y_end": node.y_end,
                "depth": node.depth,
                "complexity_score": node.complexity_score,
                "expected_hash": expected_hash,
                "compute_result_hash": result_hash_from_compute(compute_result),
                "compute_output_ref": output_ref_from_compute(compute_result),
                "verify_choice": bool(verify_result.get("choice", False)),
                "verify_recomputed_hash": verify_result.get("recomputed_hash", ""),
            }
        )

    rgb_parts: list[bytes] = []
    total_height = 0
    for fragment in sorted(fragments, key=lambda item: (item["y_start"], item["fragment_index"])):
        part_width, part_height, part_rgb = read_p6_ppm(p2p_file_path(fragment["compute_output_ref"]))
        if part_width != width:
            raise ValueError(f"fragment width mismatch: expected {width}, got {part_width}")
        rgb_parts.append(part_rgb)
        total_height += part_height
    if total_height != height:
        raise ValueError(f"reassembled height mismatch: expected {height}, got {total_height}")

    reassembled_ppm = reassembled_dir / "render.ppm"
    reassembled_png = reassembled_dir / "render.png"
    write_p6_ppm(reassembled_ppm, width, height, b"".join(rgb_parts))
    reassembled_png.write_bytes(ppm_to_png_bytes(reassembled_ppm.read_bytes()))
    reassembled_hash = sha256_file(reassembled_ppm)
    success = all(fragment["verify_choice"] for fragment in fragments) and reassembled_hash == expected_full_hash

    summary = {
        "schema_version": 1,
        "demo_mode": "auto_split",
        "job_id": job_id,
        "scene": str(scene_path),
        "job_dir": str(job_dir),
        "export_dir": str(export_dir),
        "split_policy": {
            "kind": "render3d_horizontal_binary",
            "complexity_threshold": args.complexity_threshold,
            "max_depth": args.max_depth,
        },
        "split_tree": tree_to_dict(root),
        "fragment_count": len(fragments),
        "image": {"width": width, "height": height},
        "expected_full_hash": expected_full_hash,
        "reassembled_hash": reassembled_hash,
        "reassembled_ppm": str(reassembled_ppm),
        "reassembled_png": str(reassembled_png),
        "fragments": fragments,
        "submissions": submissions,
        "node_runs": node_runs,
        "success": success,
        "devnet_trace": {"enabled": False, "status": "not_requested"},
    }
    summary_path = job_dir / "auto-split-demo-summary.json"
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
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not success:
        return 2
    if args.devnet_trace and not summary["devnet_trace"].get("ok"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
