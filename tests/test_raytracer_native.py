"""workloads.raytracer.native: Python entry points of the native tile pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from workloads.raytracer import native
from workloads.raytracer import raytracer_workload as legacy

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _pattern_ppm(width: int, height: int, seed: int) -> bytes:
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


@needs_rust
@pytest.mark.parametrize("width,height,seed,y_start,batch,x_start", [(4, 3, 1, 0, 1, 0), (6, 50, 9, 40, 5, 12), (7, 21, 2, 0, 20, 0)])
def test_milestones_match_the_python_commitment(binary, width, height, seed, y_start, batch, x_start) -> None:
    tile = _pattern_ppm(width, height, seed)
    assert native.build_milestones(tile, y_start, batch, x_start) == legacy.build_verification_milestones(
        tile, y_start, batch, x_start
    )


@needs_rust
@pytest.mark.parametrize(
    "data,width,height,expected",
    [
        (_pattern_ppm(4, 3, 1), 4, 3, "match"),
        (_pattern_ppm(4, 3, 1), None, None, None),
        (_pattern_ppm(4, 3, 1), 5, 3, None),
        (_pattern_ppm(4, 3, 1), 5, None, None),
        (_pattern_ppm(4, 3, 1), None, 9, None),
        (_pattern_ppm(4, 3, 1), None, None, "0" * 64),
        (b"not a ppm", None, None, None),
    ],
)
def test_fragment_validation_matches_python(binary, data, width, height, expected) -> None:
    import hashlib

    if expected == "match":
        expected = "sha256:" + hashlib.sha256(data).hexdigest().upper()
    kwargs = {"expected_width": width, "expected_height": height, "expected_hash": expected}
    try:
        wanted = legacy.validate_fragment_ppm(data, task_id="task-1", **kwargs)
    except RuntimeError as error:
        with pytest.raises(RuntimeError) as got:
            native.validate_fragment(data, task_id="task-1", **kwargs)
        assert str(got.value) == str(error)
        return
    got = native.validate_fragment(data, task_id="task-1", **kwargs)
    assert got.pop("pixel_sha256") == legacy.ppm_pixel_sha256(data)
    assert got == wanted


@needs_rust
def test_pixel_hash_matches_python(binary) -> None:
    tile = _pattern_ppm(5, 4, 3)
    assert native.pixel_sha256(tile) == legacy.ppm_pixel_sha256(tile)


@needs_rust
@pytest.mark.parametrize("reputation", [0.0, 50.0, 100.0])
@pytest.mark.parametrize("tampered", [False, True])
def test_probabilistic_verification_matches_python(binary, reputation, tampered) -> None:
    good = _pattern_ppm(6, 50, 9)
    manifest = legacy.build_verification_milestones(good, 40, 5, 12)
    image = bytearray(good)
    if tampered:
        image[-1] ^= 0xFF
    got = native.verify_milestones(bytes(image), manifest, "seed-abc", reputation)
    assert got == legacy.verify_probabilistic_milestones(bytes(image), manifest, "seed-abc", reputation)
