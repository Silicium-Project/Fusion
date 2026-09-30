"""Calls into the native tile pipeline (`silicium-raytracer` sub-commands).

The Rust binary is the single implementation of the tile pipeline: scene
size, splitting, reassembly, milestone commitments, probabilistic milestone
checks, fragment validation and PNG previews. Python code (orchestrator and
nodes) goes through the functions of this module instead of re-implementing
them; there is no Python PPM parser any more.

The binary is the renderer itself: nodes find it through
SILICIUM_RAYTRACER_BIN, the orchestrator through SILICIUM_PIPELINE_BIN.
Each sub-command prints one JSON object (see crates/raytracer/README.md).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Exit codes of the sub-commands (crates/raytracer/src/commands.rs).
EXIT_OK = 0
EXIT_INVALID_INPUT = 1
EXIT_VERIFICATION_FAILED = 2


def pipeline_binary() -> str:
    """Path of the native binary.

    SILICIUM_PIPELINE_BIN wins; otherwise the renderer (SILICIUM_RAYTRACER_BIN,
    the same binary) is used. Relative paths resolve from the working
    directory, like the renderer lookup.
    """
    for variable in ("SILICIUM_PIPELINE_BIN", "SILICIUM_RAYTRACER_BIN"):
        configured = os.environ.get(variable, "").strip()
        if not configured:
            continue
        candidate = Path(configured).expanduser().resolve()
        if not (candidate.is_file() and os.access(candidate, os.X_OK)):
            raise RuntimeError(f"raytracer_pipeline_binary_unusable:{candidate}")
        return str(candidate)
    raise RuntimeError("raytracer_pipeline_binary_missing")


def run_command(
    name: str,
    arguments: list[str],
    *,
    allowed_codes: tuple[int, ...] = (EXIT_OK,),
    timeout: float = 60.0,
) -> tuple[dict[str, Any], int]:
    """Run `silicium-raytracer <name> <arguments>`; return (JSON output, exit code).

    An exit code outside `allowed_codes` raises with the command's stderr.
    """
    completed = subprocess.run(
        [pipeline_binary(), name, *arguments],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode not in allowed_codes:
        raise RuntimeError(f"raytracer_{name}_failed:{completed.stderr[-2048:]}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"raytracer_{name}_output_invalid:{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"raytracer_{name}_output_invalid")
    return payload, completed.returncode


def _with_temp_file(data: bytes, suffix: str, action):
    """Write `data` to a private temporary file and call `action(path)`."""
    with tempfile.TemporaryDirectory(prefix="silicium-native-") as directory:
        path = Path(directory) / f"input{suffix}"
        path.write_bytes(data)
        return action(path)


def build_milestones(ppm: bytes, y_start: int, batch_rows: int, x_start: int) -> dict[str, Any]:
    """Milestone commitment of a rendered tile (`silicium-raytracer milestones`).

    The manifest lists the pixel hash of every block of `batch_rows` rows and
    a commitment hash over all of them; the orchestrator compares it with the
    one returned by the compute node.
    """

    def milestones(path: Path) -> dict[str, Any]:
        payload, _ = run_command(
            "milestones",
            [str(path), "--y-start", str(y_start), "--batch-rows", str(batch_rows), "--x-start", str(x_start)],
        )
        return payload

    return _with_temp_file(ppm, ".ppm", milestones)


def validate_fragment(
    ppm: bytes,
    *,
    task_id: str,
    expected_width: int | None = None,
    expected_height: int | None = None,
    expected_hash: str | None = None,
) -> dict[str, Any]:
    """Check a rendered tile (`silicium-raytracer validate`).

    Returns width, height, sha256 (whole file), pixel_sha256 (raster only) and
    valid_p6. Raises RuntimeError with the raytracer_fragment_* error code on
    an invalid format, size or hash.
    """
    arguments = ["--task-id", task_id]
    if expected_width is not None:
        arguments += ["--width", str(expected_width)]
    if expected_height is not None:
        arguments += ["--height", str(expected_height)]
    if expected_hash:
        arguments += ["--expected-hash", expected_hash]

    def validate(path: Path) -> dict[str, Any]:
        payload, code = run_command(
            "validate", [str(path), *arguments], allowed_codes=(EXIT_OK, EXIT_INVALID_INPUT)
        )
        if code != EXIT_OK:
            raise RuntimeError(str(payload.get("error") or "raytracer_fragment_invalid"))
        payload.pop("fragment", None)
        return payload

    return _with_temp_file(ppm, ".ppm", validate)


def pixel_sha256(ppm: bytes) -> str:
    """SHA-256 of the raster of a P6 image (header excluded)."""
    return str(validate_fragment(ppm, task_id="pixel-hash")["pixel_sha256"])


def verify_milestones(ppm: bytes, manifest: dict[str, Any], seed: str, reputation: float) -> dict[str, Any]:
    """Probabilistic milestone check (`silicium-raytracer verify`).

    Samples milestones (more for a low reputation), recomputes their pixel
    hashes from `ppm` and returns the verification result (`verified`,
    sampled indices, failures, `escalated_to_full`).
    """
    with tempfile.TemporaryDirectory(prefix="silicium-native-") as directory:
        tile_path = Path(directory) / "tile.ppm"
        manifest_path = Path(directory) / "manifest.json"
        tile_path.write_bytes(ppm)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        payload, _ = run_command(
            "verify",
            [str(tile_path), "--manifest", str(manifest_path), "--seed", seed, "--reputation", str(reputation)],
            allowed_codes=(EXIT_OK, EXIT_VERIFICATION_FAILED),
        )
    return payload


def write_png(ppm: bytes, path: Path) -> dict[str, Any]:
    """PNG preview of a tile (`silicium-raytracer png`).

    Never raises: a preview is optional, so a failure is reported as
    `{"ready": False, "error": ...}` and no file is left at `path`.
    """
    path = path.resolve()

    def convert(source: Path) -> dict[str, Any]:
        payload, _ = run_command(
            "png", [str(source), "--output", str(path)], allowed_codes=(EXIT_OK, EXIT_INVALID_INPUT)
        )
        return payload

    try:
        return _with_temp_file(ppm, ".ppm", convert)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        path.unlink(missing_ok=True)
        return {"ready": False, "path": "", "sha256": "", "error": str(exc)}


def scene_resolution(scene: Path) -> tuple[int, int]:
    """(width, height) declared by a scene file, 1920x1080 when it does not say."""
    payload, _ = run_command("resolution", [str(scene)])
    return int(payload["width"]), int(payload["height"])
