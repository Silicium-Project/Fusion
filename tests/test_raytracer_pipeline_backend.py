"""run_network_job.py drives the same tile pipeline in Rust or Python."""

from __future__ import annotations

import json
import os
import shutil
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


def _split_args() -> types.SimpleNamespace:
    return types.SimpleNamespace(target_pixels=65536, max_fragments=64, fragments=0)


def test_pipeline_backend_defaults_to_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SILICIUM_PIPELINE_BIN", raising=False)
    assert run_network_job.pipeline_binary() is None
    assert run_network_job.pipeline_backend() == "python"


def test_pipeline_binary_must_be_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SILICIUM_PIPELINE_BIN", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="raytracer_pipeline_binary_unusable"):
        run_network_job.pipeline_binary()


@needs_rust
def test_rust_and_python_pipelines_agree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    results = {}
    for backend in ("python", "rust"):
        work = tmp_path / backend
        work.mkdir()
        if backend == "rust":
            monkeypatch.setenv("SILICIUM_PIPELINE_BIN", str(RUST))
        else:
            monkeypatch.delenv("SILICIUM_PIPELINE_BIN", raising=False)
        assert run_network_job.pipeline_backend() == backend
        plan = run_network_job.make_split(_split_args(), SCENE, work / "split.json")
        fragments = []
        for fragment in plan["fragments"]:
            output = work / f"{fragment['fragment_id']}.ppm"
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
        summary = run_network_job.reassemble_fragments(
            fragments, work / "render.ppm", work / "render.png", work / "reassemble.json"
        )
        assert json.loads((work / "reassemble.json").read_text(encoding="utf-8")) == summary
        results[backend] = (plan, summary, (work / "render.ppm").read_bytes())

    python_plan, python_summary, python_ppm = results["python"]
    rust_plan, rust_summary, rust_ppm = results["rust"]
    assert rust_plan == python_plan
    assert rust_ppm == python_ppm
    assert rust_summary["result_sha256"] == python_summary["result_sha256"]
    assert rust_summary["fragment_count"] == python_summary["fragment_count"]
    assert rust_summary["result_png_ready"] is python_summary["result_png_ready"] is True
