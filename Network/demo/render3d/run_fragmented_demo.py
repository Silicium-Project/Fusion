from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from render3d_demo import (
    DEFAULT_EXPORT_DIR,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SCENE,
    NETWORK_ROOT,
    load_scene,
    ppm_to_png_bytes,
    render_scene,
    sha256_bytes,
    sha256_file,
    stable_json,
    submit_task,
    write_json,
)
from run_full_demo import (
    clear_previous_result,
    output_ref_from_compute,
    result_hash_from_compute,
    run_node_until_result,
)


FRAGMENT_COMPUTE_WORKLOAD = "calcul/rendering/demo-render3d-fragment"
FRAGMENT_VERIFY_WORKLOAD = "verification/rendering/demo-render3d-fragment"


def image_size(scene: dict[str, Any]) -> tuple[int, int]:
    image = scene.get("image") if isinstance(scene.get("image"), dict) else {}
    width = max(16, min(2048, int(image.get("width", 320))))
    height = max(16, min(2048, int(image.get("height", 200))))
    return width, height


def read_p6_ppm(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    offset = 0

    def token() -> bytes:
        nonlocal offset
        while offset < len(data) and data[offset] in b" \t\r\n":
            offset += 1
        if offset < len(data) and data[offset] == ord("#"):
            while offset < len(data) and data[offset] not in b"\r\n":
                offset += 1
            return token()
        start = offset
        while offset < len(data) and data[offset] not in b" \t\r\n":
            offset += 1
        return data[start:offset]

    if token() != b"P6":
        raise ValueError(f"not a P6 PPM: {path}")
    width = int(token())
    height = int(token())
    max_value = int(token())
    if max_value != 255:
        raise ValueError(f"unsupported PPM max value in {path}: {max_value}")
    while offset < len(data) and data[offset] in b" \t\r\n":
        offset += 1
    rgb = data[offset:]
    expected = width * height * 3
    if len(rgb) != expected:
        raise ValueError(f"bad PPM payload size in {path}: expected {expected}, got {len(rgb)}")
    return width, height, rgb


def write_p6_ppm(path: Path, width: int, height: int, rgb: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + rgb)


def p2p_file_path(ref: dict[str, Any]) -> Path:
    if ref.get("protocol") != "file":
        raise ValueError(f"demo reassemble expects file protocol output_ref, got {ref.get('protocol')}")
    content_id = str(ref.get("content_id") or "")
    if not content_id:
        raise ValueError("missing output_ref content_id")
    return Path(content_id)


def fragment_bands(height: int, count: int) -> list[tuple[int, int]]:
    count = max(1, min(height, count))
    bands = []
    for index in range(count):
        y_start = (height * index) // count
        y_end = (height * (index + 1)) // count
        bands.append((y_start, y_end))
    return bands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the render3d demo as fragmented compute/verify/reassemble.")
    parser.add_argument("scene", nargs="?", default=str(DEFAULT_SCENE))
    parser.add_argument("--job-id", "--task-id", dest="job_id", default="")
    parser.add_argument("--fragments", type=int, default=4)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--export-dir",
        default="",
        help="Queue/export directory. Defaults to an isolated export folder inside the job directory.",
    )
    parser.add_argument(
        "--reuse-job-dir",
        action="store_true",
        help="Allow reusing an existing local demo job directory. Prefer a new --job-id for Devnet demos.",
    )
    parser.add_argument("--priority", default="high", choices=["low", "normal", "high", "urgent"])
    parser.add_argument("--p2p-gateway", default="http://127.0.0.1:5001")
    parser.add_argument("--node-mode", default="auto", choices=["auto", "cli", "inline"])
    parser.add_argument("--node-sweeps", type=int, default=30)
    parser.add_argument("--result-timeout-s", type=float, default=60.0)
    parser.add_argument("--node-timeout-s", type=float, default=60.0)
    parser.add_argument("--solana-enable", action="store_true")
    parser.add_argument("--devnet-trace", action="store_true", help="After local P2P success, write the fragment path to Solana Devnet.")
    parser.add_argument("--devnet-trace-timeout-s", type=float, default=300.0)
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.environ.get("ANCHOR_WALLET", "")))
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument("--solana-program-id", default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA"))
    parser.add_argument("--devnet-tx-delay-ms", type=int, default=int(os.environ.get("SILICIUM_DEVNET_TX_DELAY_MS", "1200")))
    return parser


def default_solana_wallet_path() -> Path:
    return NETWORK_ROOT / ".silicium" / "solana" / "id.json"


def resolve_solana_wallet(raw: str) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return default_solana_wallet_path()


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
            + " | Or pass: --solana-wallet C:\\path\\to\\id.json"
        )
    trace_path = summary_path.with_name("devnet-trace.json")
    env = os.environ.copy()
    env["SILICIUM_TRACE_RESULT_PATH"] = str(trace_path)
    env["ANCHOR_WALLET"] = str(wallet_path)
    env["SOLANA_RPC_URL"] = args.solana_rpc
    env["SOLANA_LAYER_PROGRAM_ID"] = args.solana_program_id
    env["SILICIUM_DEVNET_TX_DELAY_MS"] = str(args.devnet_tx_delay_ms)
    command = [
        npx,
        "ts-node",
        "scripts/devnet_trace_render3d_fragments.ts",
        str(summary_path),
    ]
    completed = subprocess.run(
        command,
        cwd=str(Path(__file__).resolve().parents[2] / "solana-layer"),
        env=env,
        text=True,
        capture_output=True,
        timeout=args.devnet_trace_timeout_s,
        check=False,
    )
    trace = {}
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
    job_id = args.job_id or f"render3d-fragmented-{int(time.time())}"
    output_root = Path(args.output_root).resolve()
    job_dir = output_root / job_id
    if job_dir.exists() and any(job_dir.iterdir()) and not args.reuse_job_dir:
        raise RuntimeError(
            f"demo job directory already exists: {job_dir}\n"
            "Use a new --job-id for a fresh demo, for example --job-id render-frag-005, "
            "or pass --reuse-job-dir if you intentionally want to overwrite local demo files."
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

    bands = fragment_bands(height, args.fragments)
    node_runs: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    submissions: list[dict[str, Any]] = []
    for index, (y_start, y_end) in enumerate(bands):
        fragment_id = f"{job_id}-frag-{index:03d}"
        fragment_ppm = render_scene(scene, y_start, y_end)
        expected_path = expected_dir / f"fragment-{index:03d}.ppm"
        expected_path.write_bytes(fragment_ppm)
        expected_hash = sha256_bytes(fragment_ppm)

        spec = {
            "schema_version": 1,
            "job_id": job_id,
            "fragment_index": index,
            "fragment_count": len(bands),
            "y_start": y_start,
            "y_end": y_end,
            "scene_p2p_ref": scene_ref,
            "expected_result_sha256": expected_hash,
        }
        spec_path = input_dir / f"fragment-{index:03d}.json"
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
                "fragment_index": index,
                "fragment_count": len(bands),
                "y_start": y_start,
                "y_end": y_end,
            },
        }
        clear_previous_result(export_dir, verify_id)
        submissions.append(submit_task(export_dir, verify_payload))
        verify_result = run_node_until_result(args, "verify", verify_id, node_runs)
        fragments.append(
            {
                "fragment_id": fragment_id,
                "verify_id": verify_id,
                "fragment_index": index,
                "y_start": y_start,
                "y_end": y_end,
                "expected_hash": expected_hash,
                "compute_result_hash": result_hash_from_compute(compute_result),
                "compute_output_ref": output_ref_from_compute(compute_result),
                "verify_choice": bool(verify_result.get("choice", False)),
                "verify_recomputed_hash": verify_result.get("recomputed_hash", ""),
            }
        )

    rgb_parts: list[bytes] = []
    total_height = 0
    for fragment in fragments:
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
        "job_id": job_id,
        "scene": str(scene_path),
        "job_dir": str(job_dir),
        "export_dir": str(export_dir),
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
    summary_path = job_dir / "fragmented-demo-summary.json"
    write_json(summary_path, summary)
    if args.devnet_trace or args.solana_enable:
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
    if (args.devnet_trace or args.solana_enable) and not summary["devnet_trace"].get("ok"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
