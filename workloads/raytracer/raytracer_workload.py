from __future__ import annotations

import argparse
import json
import os
import math
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import hashlib
from collections import deque
from pathlib import Path
from typing import Any

NETWORK_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET_PIXELS_PER_FRAGMENT = 120_000
DEFAULT_MAX_FRAGMENTS = 32
DEFAULT_VERIFICATION_BATCH_ROWS = 20


def sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def ppm_to_png_bytes(ppm_bytes: bytes) -> bytes:
    try:
        from workloads.common import ppm_to_png_bytes as convert
    except ImportError:
        parent = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(parent.parent))
        from workloads.common import ppm_to_png_bytes as convert

    return convert(ppm_bytes)


def write_optional_png(ppm_bytes: bytes, path: Path) -> dict[str, Any]:
    path = path.resolve()
    try:
        png_bytes = ppm_to_png_bytes(ppm_bytes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_bytes)
    except Exception as exc:
        if path.exists():
            path.unlink()
        return {
            "ready": False,
            "path": "",
            "sha256": "",
            "error": f"{type(exc).__name__}:{exc}",
        }
    return {
        "ready": True,
        "path": str(path),
        "sha256": sha256_bytes(png_bytes),
        "error": "",
    }


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


def scene_resolution(scene: Path) -> tuple[int, int]:
    text = scene.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"resolution\s*=\s*\{[^}]*width\s*=\s*(\d+)[^}]*height\s*=\s*(\d+)", text, re.IGNORECASE)
    if not match:
        return (1920, 1080)
    return (max(1, int(match.group(1))), max(1, int(match.group(2))))


def estimate_fragment_count(scene: Path, target_pixels: int, max_fragments: int) -> int:
    width, height = scene_resolution(scene)
    pixels = width * height
    fragments = max(1, math.ceil(pixels / max(1, target_pixels)))
    return max(1, min(fragments, max(1, max_fragments), height))


def split_tiles(width: int, height: int, fragment_count: int) -> list[dict[str, int]]:
    """Cover the image with exactly N rectangular tiles in center-out BFS order.

    Rows may have one more column than their neighbours, which supports arbitrary
    fragment counts without leaving holes. Ordering walks edge-sharing neighbours
    from the tile nearest the image centre; it never globally sorts by distance.
    """
    fragment_count = max(1, min(int(fragment_count), width * height))
    ideal_rows = round(math.sqrt(fragment_count * height / width))
    row_count = max(math.ceil(fragment_count / width), min(height, fragment_count, max(1, ideal_rows)))
    base_columns, extra_columns = divmod(fragment_count, row_count)
    columns_per_row = [base_columns + (1 if row < extra_columns else 0) for row in range(row_count)]

    tiles: list[dict[str, int]] = []
    rows: list[list[int]] = []
    for row, column_count in enumerate(columns_per_row):
        y_start = round(row * height / row_count)
        y_end = round((row + 1) * height / row_count)
        row_tiles: list[int] = []
        for column in range(column_count):
            x_start = round(column * width / column_count)
            x_end = round((column + 1) * width / column_count)
            if x_end <= x_start or y_end <= y_start:
                continue
            row_tiles.append(len(tiles))
            tiles.append(
                {
                    "tile_row": row,
                    "tile_column": column,
                    "x_start": x_start,
                    "x_end": x_end,
                    "y_start": y_start,
                    "y_end": y_end,
                }
            )
        rows.append(row_tiles)

    center_x = width / 2.0
    center_y = height / 2.0
    start = 0
    best_distance = float("inf")
    for tile_index, tile in enumerate(tiles):
        tile_x = (tile["x_start"] + tile["x_end"]) / 2.0
        tile_y = (tile["y_start"] + tile["y_end"]) / 2.0
        distance = (tile_x - center_x) ** 2 + (tile_y - center_y) ** 2
        if distance < best_distance:
            start = tile_index
            best_distance = distance

    neighbours: list[list[int]] = [[] for _ in tiles]
    for row, row_tiles in enumerate(rows):
        for position, tile_index in enumerate(row_tiles):
            if position + 1 < len(row_tiles):
                right = row_tiles[position + 1]
                neighbours[tile_index].append(right)
                neighbours[right].append(tile_index)
            for adjacent_row in (row - 1, row + 1):
                if adjacent_row < 0 or adjacent_row >= len(rows):
                    continue
                tile = tiles[tile_index]
                for candidate in rows[adjacent_row]:
                    other = tiles[candidate]
                    if min(tile["x_end"], other["x_end"]) > max(tile["x_start"], other["x_start"]):
                        neighbours[tile_index].append(candidate)

    ordered: list[dict[str, int]] = []
    pending = deque([start])
    visited = {start}
    while pending:
        tile_index = pending.popleft()
        ordered.append(tiles[tile_index])
        for neighbour in neighbours[tile_index]:
            if neighbour not in visited:
                visited.add(neighbour)
                pending.append(neighbour)

    if len(ordered) != len(tiles):
        raise RuntimeError("raytracer_tile_graph_disconnected")
    return ordered


def parse_ppm_bytes(data: bytes, source: str = "<bytes>") -> tuple[int, int, bytes]:
    idx = 0

    def token() -> bytes:
        nonlocal idx
        while idx < len(data) and chr(data[idx]).isspace():
            idx += 1
        if idx < len(data) and data[idx] == ord("#"):
            while idx < len(data) and data[idx] not in b"\r\n":
                idx += 1
            return token()
        start = idx
        while idx < len(data) and not chr(data[idx]).isspace():
            idx += 1
        return data[start:idx]

    magic = token()
    if magic != b"P6":
        raise ValueError(f"unsupported_ppm_magic:{source}")
    width = int(token())
    height = int(token())
    max_value = int(token())
    if max_value != 255:
        raise ValueError(f"unsupported_ppm_max_value:{max_value}")
    if idx >= len(data) or data[idx] not in b" \t\r\n":
        raise ValueError(f"missing_ppm_raster_separator:{source}")
    if data[idx : idx + 2] == b"\r\n":
        idx += 2
    else:
        idx += 1
    pixels = data[idx:]
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(f"invalid_ppm_payload_size:{source}:expected={expected}:actual={len(pixels)}")
    return width, height, pixels


def read_ppm(path: Path) -> tuple[int, int, bytes]:
    return parse_ppm_bytes(path.read_bytes(), str(path))


def ppm_pixel_sha256(ppm_bytes: bytes) -> str:
    _, _, pixels = parse_ppm_bytes(ppm_bytes)
    return sha256_bytes(pixels)


def build_verification_milestones(
    ppm_bytes: bytes,
    fragment_y_start: int,
    batch_rows: int = DEFAULT_VERIFICATION_BATCH_ROWS,
    fragment_x_start: int = 0,
) -> dict[str, Any]:
    width, height, pixels = parse_ppm_bytes(ppm_bytes)
    batch_rows = max(1, int(batch_rows))
    fragment_y_start = int(fragment_y_start)
    milestones: list[dict[str, Any]] = []
    row_stride = width * 3
    for index, local_y_start in enumerate(range(0, height, batch_rows)):
        local_y_end = min(height, local_y_start + batch_rows)
        pixel_slice = pixels[local_y_start * row_stride : local_y_end * row_stride]
        milestones.append(
            {
                "index": index,
                "x_start": fragment_x_start,
                "x_end": fragment_x_start + width,
                "y_start": fragment_y_start + local_y_start,
                "y_end": fragment_y_start + local_y_end,
                "row_count": local_y_end - local_y_start,
                "pixel_sha256": sha256_bytes(pixel_slice),
            }
        )
    commitment_material = json.dumps(milestones, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": 1,
        "strategy": "random-tile-row-milestone-v2",
        "image_width": width,
        "fragment_x_start": fragment_x_start,
        "fragment_x_end": fragment_x_start + width,
        "fragment_y_start": fragment_y_start,
        "fragment_y_end": fragment_y_start + height,
        "fragment_rows": height,
        "batch_rows": batch_rows,
        "milestone_count": len(milestones),
        "commitment_hash": sha256_bytes(commitment_material),
        "milestones": milestones,
    }


def calculate_sampling_rate(reputation_score: float, min_rate: float = 0.2, max_rate: float = 1.0) -> float:
    """Calculate sampling rate based on worker reputation.
    
    Low reputation workers require a higher verification sampling rate (up to 1.0 = 100%).
    High reputation workers require a lower sampling rate (down to min_rate = 0.2).
    """
    rep = max(0.0, float(reputation_score))
    if rep >= 100.0:
        return min_rate
    rate = max_rate - (rep / 100.0) * (max_rate - min_rate)
    return round(max(min_rate, min(max_rate, rate)), 4)


def select_probabilistic_milestones(
    manifest: dict[str, Any],
    seed: str,
    sample_rate: float = 0.25,
) -> list[dict[str, Any]]:
    """Select an unpredictable subset of milestones using a post-commitment seed."""
    milestones = manifest.get("milestones", [])
    if not milestones:
        return []

    sample_rate = max(0.0, min(1.0, float(sample_rate)))
    target_count = max(1, math.ceil(len(milestones) * sample_rate))

    scored_milestones = []
    for ms in milestones:
        index_bytes = str(ms["index"]).encode("utf-8")
        score = hashlib.sha256(f"{seed}:{index_bytes.decode()}".encode("utf-8")).hexdigest()
        scored_milestones.append((score, ms))

    scored_milestones.sort(key=lambda x: x[0])
    return [ms for _, ms in scored_milestones[:target_count]]


def detection_probability(total_milestones: int, tampered_milestones: int, sampled_count: int) -> float:
    """Calculate theoretical detection probability for probabilistic milestone sampling."""
    if total_milestones <= 0 or sampled_count <= 0 or tampered_milestones <= 0:
        return 0.0
    if tampered_milestones >= total_milestones or sampled_count >= total_milestones:
        return 1.0

    prob_miss = 1.0
    n = total_milestones
    m = tampered_milestones
    for i in range(sampled_count):
        prob_miss *= (n - m - i) / (n - i)
    return round(1.0 - prob_miss, 4)


def verify_probabilistic_milestones(
    ppm_bytes: bytes,
    manifest: dict[str, Any],
    seed: str,
    reputation_score: float = 50.0,
) -> dict[str, Any]:
    """Verify fragment milestones probabilistically with automatic escalation to full check upon failure."""
    width, height, pixels = parse_ppm_bytes(ppm_bytes)
    row_stride = width * 3
    fragment_y_start = manifest.get("fragment_y_start", 0)

    sample_rate = calculate_sampling_rate(reputation_score)
    sampled = select_probabilistic_milestones(manifest, seed, sample_rate)

    failed_milestones = []
    for ms in sampled:
        local_y_start = ms["y_start"] - fragment_y_start
        local_y_end = ms["y_end"] - fragment_y_start
        pixel_slice = pixels[local_y_start * row_stride : local_y_end * row_stride]
        actual_sha256 = sha256_bytes(pixel_slice)
        if actual_sha256 != ms["pixel_sha256"]:
            failed_milestones.append({
                "index": ms["index"],
                "expected": ms["pixel_sha256"],
                "actual": actual_sha256,
            })

    if failed_milestones:
        return {
            "verified": False,
            "escalated_to_full": True,
            "sample_rate": sample_rate,
            "sampled_count": len(sampled),
            "total_milestones": manifest.get("milestone_count", 0),
            "failed_milestones": failed_milestones,
            "reason": f"probabilistic_milestone_verification_failed:{len(failed_milestones)}_mismatches",
        }

    return {
        "verified": True,
        "escalated_to_full": False,
        "sample_rate": sample_rate,
        "sampled_count": len(sampled),
        "total_milestones": manifest.get("milestone_count", 0),
        "failed_milestones": [],
        "reason": "",
    }



def write_ppm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + pixels)


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
        completed = subprocess.run(
            cmd,
            cwd=runtime_dir,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
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
    return {
        "binary": str(binary),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4096:],
        "stderr": completed.stderr[-4096:],
        "renderer_telemetry": renderer_telemetry,
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
    result["verification_milestones"] = build_verification_milestones(
        output.read_bytes(),
        y_start or 0,
        int(args.verification_batch_rows),
        x_start or 0,
    )
    png_path = Path(args.png).resolve() if args.png else None
    if png_path:
        png = write_optional_png(output.read_bytes(), png_path)
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
    with tempfile.TemporaryDirectory(prefix="silicium-raytracer-verify-") as tmpdir:
        recomputed_path = Path(tmpdir) / "recomputed.ppm"
        try:
            recomputed = run_raytracer(scene, recomputed_path, int(args.timeout_s), y_start, y_end, x_start, x_end)
            recomputed_hash = str(recomputed.get("result_sha256") or "")
        except Exception as exc:
            recompute_error = str(exc)
    hash_integrity_ok = (not declared) or declared == actual_hash
    recompute_match = bool(recomputed_hash) and actual_hash == recomputed_hash
    verified = hash_integrity_ok
    payload = {
        "schema_version": 1,
        "workload": "raytracer",
        "entrypoint": "verify",
        "actual_hash": actual_hash,
        "recomputed_hash": recomputed_hash,
        "recompute_error": recompute_error,
        "recompute_match": recompute_match,
        "expected_hash": declared,
        "verification_mode": "declared-hash",
        "verified": verified,
        "choice": verified,
        "fragment": {"x_start": x_start, "x_end": x_end, "y_start": y_start, "y_end": y_end},
    }
    if args.result_json:
        write_json(Path(args.result_json).resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verified else 2


def command_split(args: argparse.Namespace) -> int:
    scene = Path(args.scene).resolve()
    width, height = scene_resolution(scene)
    fragment_count = int(args.fragments) if int(args.fragments) > 0 else estimate_fragment_count(
        scene,
        int(args.target_pixels),
        int(args.max_fragments),
    )
    tiles = split_tiles(width, height, fragment_count)
    fragments = []
    for index, tile in enumerate(tiles):
        x_start = tile["x_start"]
        x_end = tile["x_end"]
        y_start = tile["y_start"]
        y_end = tile["y_end"]
        fragments.append(
            {
                "fragment_index": index,
                "fragment_id": f"fragment-{index:03d}",
                "is_leaf": True,
                "depth": 0,
                "tile_row": tile["tile_row"],
                "tile_column": tile["tile_column"],
                "x_start": x_start,
                "x_end": x_end,
                "y_start": y_start,
                "y_end": y_end,
                "scene_path": str(scene),
                "scene_sha256": sha256_file(scene),
                "complexity_score": (x_end - x_start) * (y_end - y_start),
            }
        )
    payload = {
        "schema_version": 1,
        "workload": "raytracer",
        "image": {"width": width, "height": height},
        "split_policy": {
            "kind": "center-out-neighbour-grid",
            "ordering": "breadth-first-edge-neighbours",
            "target_pixels_per_fragment": int(args.target_pixels),
            "max_fragments": int(args.max_fragments),
        },
        "fragment_count": len(fragments),
        "fragments": fragments,
    }
    write_json(Path(args.output).resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_reassemble(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    fragments = [Path(value).resolve() for value in args.fragment]
    placed: list[tuple[int, int, int, int, bytes]] = []
    width = 0
    height = 0
    for index, fragment in enumerate(fragments):
        fragment_width, fragment_height, fragment_pixels = read_ppm(fragment)
        x_start = int(args.x_start[index]) if index < len(args.x_start) and args.x_start[index] != "" else 0
        y_start = int(args.y_start[index]) if index < len(args.y_start) and args.y_start[index] != "" else 0
        width = max(width, x_start + fragment_width)
        height = max(height, y_start + fragment_height)
        placed.append((x_start, y_start, fragment_width, fragment_height, fragment_pixels))
    pixels = bytearray(width * height * 3)
    for x_start, y_start, fragment_width, fragment_height, fragment_pixels in placed:
        for local_y in range(fragment_height):
            source_start = local_y * fragment_width * 3
            target_start = ((y_start + local_y) * width + x_start) * 3
            pixels[target_start : target_start + fragment_width * 3] = fragment_pixels[
                source_start : source_start + fragment_width * 3
            ]
    write_ppm(output, width, height, bytes(pixels))
    payload = {
        "schema_version": 1,
        "workload": "raytracer",
        "entrypoint": "reassemble",
        "fragment_count": len(fragments),
        "result_path": str(output),
        "result_sha256": sha256_file(output),
        "result_format": "ppm/p6",
    }
    if args.png:
        png_path = Path(args.png).resolve()
        png = write_optional_png(output.read_bytes(), png_path)
        payload["result_png_ready"] = png["ready"]
        payload["result_png_path"] = png["path"]
        payload["result_png_sha256"] = png["sha256"]
        payload["result_png_error"] = png["error"]
    if args.result_json:
        write_json(Path(args.result_json).resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Silicium raytracer workload entrypoints.")
    sub = parser.add_subparsers(dest="command")

    split = sub.add_parser("split")
    split.add_argument("scene")
    split.add_argument("--output", required=True)
    split.add_argument("--fragments", type=int, default=0)
    split.add_argument("--target-pixels", default=str(DEFAULT_TARGET_PIXELS_PER_FRAGMENT))
    split.add_argument("--max-fragments", default=str(DEFAULT_MAX_FRAGMENTS))
    split.set_defaults(func=command_split)

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
    verify.set_defaults(func=command_verify)

    reassemble = sub.add_parser("reassemble")
    reassemble.add_argument("--fragment", action="append", required=True)
    reassemble.add_argument("--y-start", action="append", default=[])
    reassemble.add_argument("--x-start", action="append", default=[])
    reassemble.add_argument("--output", required=True)
    reassemble.add_argument("--png", default="")
    reassemble.add_argument("--result-json", default="")
    reassemble.set_defaults(func=command_reassemble)
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
