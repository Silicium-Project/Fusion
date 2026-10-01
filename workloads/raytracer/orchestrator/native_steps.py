"""Job-level calls to the native binary: split the scene, reassemble the image.

Tile-level helpers (resolution, fragment validation, milestones, previews)
are in `workloads/raytracer/native.py`; these two sub-commands take
orchestrator arguments and paths, so they stay with the orchestrator.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from workloads.raytracer.native import pipeline_binary


def make_split(args: argparse.Namespace, scene_path: Path, split_path: Path) -> dict[str, Any]:
    """Run `silicium-raytracer split` and return the split plan written to `split_path`."""
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
    """Run `silicium-raytracer reassemble` on `(x_start, y_start, ppm)` tiles and return its JSON result."""
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
