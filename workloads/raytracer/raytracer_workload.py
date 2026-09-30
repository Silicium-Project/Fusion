"""Raytracer node entry points: `compute`, `verify` and `validate` one tile.

Rendering is done by the native binary (SILICIUM_RAYTRACER_BIN); tile checks
(milestones, probabilistic verification, fragment validation, PNG previews)
go through `workloads.raytracer.native`, which calls the same binary.
Run as `compute.py` / `verify.py` or `raytracer_workload.py <command>`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

NETWORK_ROOT = Path(__file__).resolve().parents[2]

try:
    from workloads.common import performance_duration, sha256_bytes, sha256_file, write_json
except ImportError:  # run as a script from workloads/raytracer/ (compute.py, verify.py...)
    sys.path.insert(0, str(NETWORK_ROOT))
    from workloads.common import performance_duration, sha256_bytes, sha256_file, write_json

from workloads.raytracer import native  # noqa: E402

DEFAULT_VERIFICATION_BATCH_ROWS = 20


def raytracer_binary() -> Path:
    override = os.environ.get("SILICIUM_RAYTRACER_BIN", "").strip()
    if not override:
        raise RuntimeError("raytracer_binary_missing: set SILICIUM_RAYTRACER_BIN to the worker-local raytracer executable")
    candidate = Path(override).expanduser()
    if not candidate.exists():
        raise RuntimeError(f"raytracer_binary_missing: {candidate}")
    return candidate.resolve()


def prepare_runtime_dir(binary: Path, runtime_dir: Path) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    assets_override = os.environ.get("SILICIUM_RAYTRACER_ASSETS_DIR", "").strip()
    assets = Path(assets_override).expanduser() if assets_override else binary.parent / "assets"
    if assets.exists() and assets.is_dir():
        shutil.copytree(assets, runtime_dir / "assets", dirs_exist_ok=True)
    for companion in binary.parent.iterdir():
        if companion != binary and companion.is_file():
            shutil.copy2(companion, runtime_dir / companion.name)
    target = runtime_dir / binary.name
    shutil.copy2(binary, target)
    if os.name != "nt":
        # Deployment and P2P copies can arrive as 0644. This runtime copy is
        # private to the process, so restore only the owner's execute bit.
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return target


def cached_runtime_binary(binary: Path) -> Path:
    """Stage a worker binary/assets once instead of copying them per tile.

    A tile is intentionally rendered in an isolated temporary output
    directory, but copying a large native binary and its assets for every
    tile can dominate the actual render time.  Keep the immutable runtime
    staged for the lifetime of the worker process/cache and reuse it.
    """
    assets_override = os.environ.get("SILICIUM_RAYTRACER_ASSETS_DIR", "").strip()
    assets = Path(assets_override).expanduser() if assets_override else binary.parent / "assets"
    try:
        stat = binary.stat()
        fingerprint = f"{binary.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{assets.resolve()}"
    except OSError:
        fingerprint = str(binary)
    key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    cache_root = Path(
        os.environ.get(
            "SILICIUM_RAYTRACER_RUNTIME_CACHE",
            str(Path(tempfile.gettempdir()) / "silicium-raytracer-cache"),
        )
    ).expanduser()
    runtime_dir = cache_root / key
    target = runtime_dir / binary.name
    if target.exists():
        return target
    staging = cache_root / f".{key}.staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        staged = prepare_runtime_dir(binary, staging)
        runtime_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            staging.replace(runtime_dir)
        except FileExistsError:
            shutil.rmtree(staging, ignore_errors=True)
        return runtime_dir / binary.name if target.exists() else staged
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def newest_ppm(directory: Path) -> Path:
    ppm_files = sorted(directory.glob("*.ppm"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not ppm_files:
        raise RuntimeError("raytracer_output_missing")
    return ppm_files[0]


def run_raytracer(
    scene: Path,
    output: Path,
    timeout_s: int = 240,
    y_start: int | None = None,
    y_end: int | None = None,
    x_start: int | None = None,
    x_end: int | None = None,
    progress_file: Path | None = None,
) -> dict[str, Any]:
    scene = scene.resolve()
    output = output.resolve()
    binary = raytracer_binary()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="silicium-raytracer-") as tmpdir:
        runtime_binary = cached_runtime_binary(binary)
        runtime_dir = runtime_binary.parent
        command_prefix = [str(runtime_binary)]
        if runtime_binary.suffix.lower() == ".py":
            command_prefix = [sys.executable, str(runtime_binary)]
        cmd = [*command_prefix, str(scene), "--output", str(output)]
        if y_start is not None:
            cmd.extend(["--y-start", str(y_start)])
        if y_end is not None:
            cmd.extend(["--y-end", str(y_end)])
        if x_start is not None:
            cmd.extend(["--x-start", str(x_start)])
        if x_end is not None:
            cmd.extend(["--x-end", str(x_end)])
        if progress_file is not None:
            cmd.extend(["--progress-file", str(progress_file.resolve())])
        process_started = time.perf_counter()
        completed = subprocess.run(
            cmd,
            cwd=runtime_dir,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        execution_duration_ms = performance_duration((time.perf_counter() - process_started) * 1000.0)
        if completed.returncode != 0:
            raise RuntimeError(
                "raytracer_failed:"
                + "\nstdout:\n"
                + completed.stdout[-4096:]
                + "\nstderr:\n"
                + completed.stderr[-4096:]
            )
        if not output.exists():
            generated = newest_ppm(runtime_dir)
            shutil.copy2(generated, output)

    result_bytes = output.read_bytes()
    renderer_telemetry: dict[str, Any] = {}
    for line in reversed(completed.stderr.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("renderer"):
            renderer_telemetry = candidate
            break
    renderer_duration_ms = performance_duration(renderer_telemetry.get("duration_ms"))
    compute_duration_ms = renderer_duration_ms or execution_duration_ms
    return {
        "binary": str(binary),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4096:],
        "stderr": completed.stderr[-4096:],
        "renderer_telemetry": renderer_telemetry,
        "execution_duration_ms": execution_duration_ms,
        "renderer_duration_ms": renderer_duration_ms,
        "performance": {
            "schema": "silicium.raytracer-performance.v1",
            "compute_ms": compute_duration_ms,
            "process_ms": execution_duration_ms,
            "renderer_ms": renderer_duration_ms,
        },
        "result_sha256": sha256_bytes(result_bytes),
        "result_path": str(output),
        "result_format": "ppm/p6",
    }


def command_compute(args: argparse.Namespace) -> int:
    scene = Path(args.scene).resolve()
    output = Path(args.output).resolve()
    y_start = int(args.y_start) if args.y_start != "" else None
    y_end = int(args.y_end) if args.y_end != "" else None
    x_start = int(args.x_start) if args.x_start != "" else None
    x_end = int(args.x_end) if args.x_end != "" else None
    progress_file = Path(args.progress_file).resolve() if args.progress_file else None
    result = run_raytracer(
        scene,
        output,
        int(args.timeout_s),
        y_start,
        y_end,
        x_start,
        x_end,
        progress_file,
    )
    # --- Issue #85: validate the binary P6 output before signing ---
    _ppm_bytes = output.read_bytes()
    try:
        native.validate_fragment(_ppm_bytes, task_id=str(output))
    except RuntimeError as exc:
        raise RuntimeError(f"raytracer_compute_invalid_output:{exc}") from exc
    result["p6_validated"] = True
    result["verification_milestones"] = native.build_milestones(
        _ppm_bytes,
        y_start or 0,
        int(args.verification_batch_rows),
        x_start or 0,
    )
    png_path = Path(args.png).resolve() if args.png else None
    if png_path:
        png = native.write_png(_ppm_bytes, png_path)
        result["result_png_ready"] = png["ready"]
        result["result_png_path"] = png["path"]
        result["result_png_sha256"] = png["sha256"]
        result["result_png_error"] = png["error"]
    result.update(
        {
            "schema_version": 1,
            "workload": "raytracer",
            "entrypoint": "compute",
            "success": True,
            "scene_path": str(scene),
            "scene_sha256": sha256_file(scene),
            "fragment_count": 1,
            "fragments": [
                {
                    "fragment_index": 0,
                    "fragment_id": "raytracer-frag-000",
                    "status": "reassembled",
                    "depth": 0,
                    "is_leaf": True,
                    "y_start": y_start,
                    "y_end": y_end,
                    "x_start": x_start,
                    "x_end": x_end,
                    "result_hash": result["result_sha256"],
                    "expected_hash": result["result_sha256"],
                }
            ],
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    if png_path:
        result["reassembled_png"] = str(png_path)
    result["reassembled_ppm"] = str(output)
    result["reassembled_hash"] = result["result_sha256"]
    if args.result_json:
        write_json(Path(args.result_json).resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    scene = Path(args.scene).resolve()
    result_path = Path(args.result).resolve()
    declared = str(args.expected_hash or "").removeprefix("sha256:")
    y_start = int(args.y_start) if args.y_start != "" else None
    y_end = int(args.y_end) if args.y_end != "" else None
    x_start = int(args.x_start) if args.x_start != "" else None
    x_end = int(args.x_end) if args.x_end != "" else None
    actual_hash = sha256_file(result_path)
    recompute_error = ""
    recomputed_hash = ""
    recompute_performance: dict[str, Any] = {}
    verification_mode = "declared-hash"
    verified = False
    recompute_match = False

    hash_integrity_ok = (not declared) or declared == actual_hash
    probabilistic_result = None

    if args.manifest and hash_integrity_ok:
        manifest = json.loads(Path(args.manifest).read_text("utf-8"))
        ppm_bytes = result_path.read_bytes()
        probabilistic_result = native.verify_milestones(
            ppm_bytes, manifest, str(args.seed), float(args.reputation_score)
        )
        if probabilistic_result["verified"]:
            verified = True
            verification_mode = "probabilistic-milestones"
        elif probabilistic_result.get("escalated_to_full"):
            verification_mode = "probabilistic-escalated"

    if not verified and hash_integrity_ok:
        with tempfile.TemporaryDirectory(prefix="silicium-raytracer-verify-") as tmpdir:
            recomputed_path = Path(tmpdir) / "recomputed.ppm"
            try:
                recomputed = run_raytracer(scene, recomputed_path, int(args.timeout_s), y_start, y_end, x_start, x_end)
                recomputed_hash = str(recomputed.get("result_sha256") or "")
                if isinstance(recomputed.get("performance"), dict):
                    recompute_performance = dict(recomputed["performance"])
            except Exception as exc:
                recompute_error = str(exc)
        recompute_match = bool(recomputed_hash) and actual_hash == recomputed_hash
        verified = recompute_match
        if verification_mode == "declared-hash":
            verification_mode = "full-recompute"

    payload = {
        "schema_version": 1,
        "workload": "raytracer",
        "entrypoint": "verify",
        "actual_hash": actual_hash,
        "recomputed_hash": recomputed_hash,
        "recompute_error": recompute_error,
        "recompute_match": recompute_match,
        "expected_hash": declared,
        "verification_mode": verification_mode,
        "verified": verified,
        "choice": verified,
        "fragment": {"x_start": x_start, "x_end": x_end, "y_start": y_start, "y_end": y_end},
    }
    if probabilistic_result:
        payload["probabilistic_metrics"] = probabilistic_result
    if recompute_performance:
        payload["performance"] = recompute_performance
    if args.result_json:
        write_json(Path(args.result_json).resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verified else 2


def command_validate(args: argparse.Namespace) -> int:
    """Standalone CLI subcommand: validate a P6 PPM binary fragment."""
    fragment_path = Path(args.fragment).resolve()
    if not fragment_path.exists():
        print(json.dumps({"error": f"file_not_found:{fragment_path}", "valid": False}))
        return 1
    fragment_bytes = fragment_path.read_bytes()
    expected_width = int(args.width) if args.width else None
    expected_height = int(args.height) if args.height else None
    expected_hash = args.expected_hash or None
    try:
        result = native.validate_fragment(
            fragment_bytes,
            task_id=str(fragment_path.name),
            expected_width=expected_width,
            expected_height=expected_height,
            expected_hash=expected_hash,
        )
        result["fragment"] = str(fragment_path)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"valid": False, "error": str(exc), "fragment": str(fragment_path)}))
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Silicium raytracer workload entrypoints.")
    sub = parser.add_subparsers(dest="command")

    compute = sub.add_parser("compute")
    compute.add_argument("--scene", required=True)
    compute.add_argument("--output", required=True)
    compute.add_argument("--png", default="")
    compute.add_argument("--result-json", default="")
    compute.add_argument("--timeout-s", default="240")
    compute.add_argument("--y-start", default="")
    compute.add_argument("--y-end", default="")
    compute.add_argument("--x-start", default="")
    compute.add_argument("--x-end", default="")
    compute.add_argument("--verification-batch-rows", default=str(DEFAULT_VERIFICATION_BATCH_ROWS))
    compute.add_argument("--progress-file", default="")
    compute.set_defaults(func=command_compute)

    verify = sub.add_parser("verify")
    verify.add_argument("--scene", required=True)
    verify.add_argument("--result", required=True)
    verify.add_argument("--expected-hash", default="")
    verify.add_argument("--result-json", default="")
    verify.add_argument("--timeout-s", default="240")
    verify.add_argument("--y-start", default="")
    verify.add_argument("--y-end", default="")
    verify.add_argument("--x-start", default="")
    verify.add_argument("--x-end", default="")
    verify.add_argument("--manifest", default="")
    verify.add_argument("--seed", default="")
    verify.add_argument("--reputation-score", type=float, default=50.0)
    verify.set_defaults(func=command_verify)

    validate = sub.add_parser("validate", help="Validate a P6 PPM binary fragment (issue #85)")
    validate.add_argument("fragment", help="Path to the PPM file to validate")
    validate.add_argument("--width", default="", help="Expected pixel width")
    validate.add_argument("--height", default="", help="Expected pixel height")
    validate.add_argument("--expected-hash", default="", help="Expected SHA-256 (with or without sha256: prefix)")
    validate.set_defaults(func=command_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
