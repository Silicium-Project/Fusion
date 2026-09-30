"""workloads.raytracer.native: Python bridge to the native tile pipeline.

The expected values come from `crates/raytracer/tests/fixtures/python_parity.json`,
recorded from the former Python implementation. The Rust tests check the
library against it; these tests check that the bridge passes arguments and
reports results and errors unchanged.

They need the `silicium-raytracer` binary: SILICIUM_TEST_PIPELINE_BIN (then a
missing binary is an error, as in CI), otherwise `target/release` or
`target/debug` when built, otherwise the tests are skipped.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from workloads.raytracer import native

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((REPO_ROOT / "crates" / "raytracer" / "tests" / "fixtures" / "python_parity.json").read_text("utf-8"))


def _rust_binary() -> Path | None:
    configured = os.environ.get("SILICIUM_TEST_PIPELINE_BIN", "").strip()
    if configured:
        return Path(configured).resolve()
    for profile in ("release", "debug"):
        candidate = REPO_ROOT / "target" / profile / "silicium-raytracer"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


RUST = _rust_binary()
needs_rust = pytest.mark.skipif(RUST is None, reason="silicium-raytracer binary not built")


def pattern_ppm(width: int, height: int, seed: int) -> bytes:
    """Same deterministic image as the fixture and the Rust tests."""
    pixels = bytes((index * 31 + seed * 7) % 256 for index in range(width * height * 3))
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels


@pytest.fixture
def binary(monkeypatch: pytest.MonkeyPatch) -> Path:
    assert RUST is not None
    monkeypatch.delenv("SILICIUM_PIPELINE_BIN", raising=False)
    monkeypatch.setenv("SILICIUM_RAYTRACER_BIN", str(RUST))
    return RUST


def test_binary_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SILICIUM_PIPELINE_BIN", raising=False)
    monkeypatch.delenv("SILICIUM_RAYTRACER_BIN", raising=False)
    with pytest.raises(RuntimeError, match="raytracer_pipeline_binary_missing"):
        native.pipeline_binary()


def test_binary_must_exist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SILICIUM_PIPELINE_BIN", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="raytracer_pipeline_binary_unusable"):
        native.pipeline_binary()


def test_png_preview_never_raises_without_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SILICIUM_PIPELINE_BIN", raising=False)
    monkeypatch.delenv("SILICIUM_RAYTRACER_BIN", raising=False)
    result = native.write_png(pattern_ppm(1, 1, 1), tmp_path / "preview.png")
    assert result["ready"] is False
    assert "raytracer_pipeline_binary_missing" in result["error"]
    assert not (tmp_path / "preview.png").exists()


@needs_rust
@pytest.mark.parametrize("case", FIXTURE["milestones"], ids=lambda case: f"{case['width']}x{case['height']}")
def test_milestones_and_pixel_hash(binary, case) -> None:
    tile = pattern_ppm(case["width"], case["height"], case["seed"])
    manifest = native.build_milestones(tile, case["y_start"], case["batch_rows"], case["x_start"])
    assert manifest == case["manifest"]
    assert native.pixel_sha256(tile) == case["pixel_sha256"]


@needs_rust
@pytest.mark.parametrize("case", FIXTURE["verify"], ids=lambda case: f"{case['image']}-{case['seed']}")
def test_probabilistic_verification(binary, case) -> None:
    image = bytearray(pattern_ppm(6, 50, 9))
    if case["image"] == "tampered":
        image[-1] ^= 0xFF
    got = native.verify_milestones(bytes(image), FIXTURE["selection_manifest"], case["seed"], case["reputation"])
    assert got == case["result"]


@needs_rust
@pytest.mark.parametrize("case", FIXTURE["validate"], ids=lambda case: case["label"])
def test_fragment_validation(binary, case) -> None:
    kwargs = {
        "task_id": case["label"],
        "expected_width": case["width"],
        "expected_height": case["height"],
        "expected_hash": case["expected_hash"],
    }
    data = bytes(case["data"])
    if "error" in case:
        with pytest.raises(RuntimeError) as error:
            native.validate_fragment(data, **kwargs)
        assert str(error.value) == case["error"]
        return
    got = native.validate_fragment(data, **kwargs)
    assert got.pop("pixel_sha256") == native.pixel_sha256(data)
    assert got == case["ok"]


@needs_rust
@pytest.mark.parametrize("case", FIXTURE["resolution"], ids=lambda case: case["scene"][:24])
def test_scene_resolution(binary, tmp_path: Path, case) -> None:
    scene = tmp_path / "scene.cfg"
    scene.write_text(case["scene"], encoding="utf-8")
    assert list(native.scene_resolution(scene)) == case["resolution"]


@needs_rust
def test_png_preview(binary, tmp_path: Path) -> None:
    preview = tmp_path / "preview.png"
    result = native.write_png(pattern_ppm(3, 2, 4), preview)
    assert result["ready"] is True
    assert result["path"] == str(preview.resolve())
    assert preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@needs_rust
def test_png_preview_reports_an_invalid_tile(binary, tmp_path: Path) -> None:
    preview = tmp_path / "preview.png"
    result = native.write_png(b"P3\n1 1\n255\n0 0 0\n", preview)
    assert result["ready"] is False
    assert result["error"].startswith("unsupported_ppm_magic")
    assert not preview.exists()
