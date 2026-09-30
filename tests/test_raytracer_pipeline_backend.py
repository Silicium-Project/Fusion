"""run_network_job.py drives the native tile pipeline (silicium-raytracer)."""

from __future__ import annotations

import os
import subprocess
import types
from pathlib import Path

import pytest

from workloads.raytracer import run_network_job

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENE = REPO_ROOT / "workloads" / "raytracer" / "examples" / "silicium-multi-fragment-scene.cfg"


def _rust_binary() -> Path | None:
    configured = os.environ.get("SILICIUM_TEST_PIPELINE_BIN", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(REPO_ROOT / "target" / "release" / "silicium-raytracer")
    candidates.append(REPO_ROOT / "target" / "debug" / "silicium-raytracer")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


RUST = _rust_binary()
needs_rust = pytest.mark.skipif(RUST is None, reason="silicium-raytracer binary not built")


def test_pipeline_binary_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SILICIUM_PIPELINE_BIN", raising=False)
    monkeypatch.delenv("SILICIUM_RAYTRACER_BIN", raising=False)
    with pytest.raises(RuntimeError, match="raytracer_pipeline_binary_missing"):
        run_network_job.pipeline_binary()


def test_pipeline_binary_must_be_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SILICIUM_PIPELINE_BIN", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="raytracer_pipeline_binary_unusable"):
        run_network_job.pipeline_binary()


def test_renderer_binary_is_the_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    renderer = tmp_path / "silicium-raytracer"
    renderer.write_text("#!/bin/sh\n", encoding="utf-8")
    renderer.chmod(0o755)
    monkeypatch.delenv("SILICIUM_PIPELINE_BIN", raising=False)
    monkeypatch.setenv("SILICIUM_RAYTRACER_BIN", str(renderer))
    assert run_network_job.pipeline_binary() == str(renderer)


@needs_rust
def test_split_render_and_reassemble_a_job(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SILICIUM_PIPELINE_BIN", str(RUST))
    args = types.SimpleNamespace(target_pixels=65536, max_fragments=64, fragments=0)
    plan = run_network_job.make_split(args, SCENE, tmp_path / "split.json")
    assert plan["fragment_count"] == len(plan["fragments"]) > 1
    width, height = plan["image"]["width"], plan["image"]["height"]
    assert sum(
        (f["x_end"] - f["x_start"]) * (f["y_end"] - f["y_start"]) for f in plan["fragments"]
    ) == width * height

    fragments = []
    for fragment in plan["fragments"]:
        output = tmp_path / f"{fragment['fragment_id']}.ppm"
        subprocess.run(
            [
                str(RUST), str(SCENE), "--output", str(output),
                "--x-start", str(fragment["x_start"]), "--x-end", str(fragment["x_end"]),
                "--y-start", str(fragment["y_start"]), "--y-end", str(fragment["y_end"]),
            ],
            check=True,
            capture_output=True,
        )
        fragments.append((fragment["x_start"], fragment["y_start"], output))
    full = tmp_path / "full.ppm"
    subprocess.run([str(RUST), str(SCENE), "--output", str(full)], check=True, capture_output=True)

    summary = run_network_job.reassemble_fragments(
        fragments, tmp_path / "render.ppm", tmp_path / "render.png", tmp_path / "reassemble.json"
    )
    assert (tmp_path / "render.ppm").read_bytes() == full.read_bytes()
    assert summary["fragment_count"] == len(fragments)
    assert summary["result_png_ready"] is True
    assert (tmp_path / "reassemble.json").is_file()
