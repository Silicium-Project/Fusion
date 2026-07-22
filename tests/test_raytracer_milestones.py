import os
import stat

import pytest

from workloads.raytracer.raytracer_workload import build_verification_milestones, prepare_runtime_dir


def _ppm(width: int, height: int, pixels: bytes) -> bytes:
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels


def test_verification_milestones_partition_rows_and_commit_pixels() -> None:
    width = 2
    height = 5
    rows = [bytes([value]) * width * 3 for value in range(height)]
    manifest = build_verification_milestones(
        _ppm(width, height, b"".join(rows)),
        100,
        batch_rows=2,
        fragment_x_start=40,
    )

    assert manifest["strategy"] == "random-tile-row-milestone-v2"
    assert manifest["fragment_x_start"] == 40
    assert manifest["fragment_x_end"] == 42
    assert manifest["fragment_y_start"] == 100
    assert manifest["fragment_y_end"] == 105
    assert manifest["milestone_count"] == 3
    assert [(item["y_start"], item["y_end"]) for item in manifest["milestones"]] == [
        (100, 102),
        (102, 104),
        (104, 105),
    ]
    assert {(item["x_start"], item["x_end"]) for item in manifest["milestones"]} == {(40, 42)}


def test_verification_milestone_only_changes_for_tampered_batch() -> None:
    width = 2
    height = 6
    pixels = bytearray(range(width * height * 3))
    original = build_verification_milestones(_ppm(width, height, bytes(pixels)), 0, batch_rows=2)
    pixels[(2 * width * 3) + 1] ^= 0xFF
    tampered = build_verification_milestones(_ppm(width, height, bytes(pixels)), 0, batch_rows=2)

    changed = [
        index
        for index, (before, after) in enumerate(zip(original["milestones"], tampered["milestones"]))
        if before["pixel_sha256"] != after["pixel_sha256"]
    ]
    assert changed == [1]
    assert original["commitment_hash"] != tampered["commitment_hash"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable mode is not represented on Windows")
def test_runtime_copy_restores_owner_execute_bit(tmp_path) -> None:
    binary = tmp_path / "raytracer"
    binary.write_bytes(b"#!/bin/sh\nexit 0\n")
    binary.chmod(0o644)

    runtime_binary = prepare_runtime_dir(binary, tmp_path / "runtime")

    assert runtime_binary.stat().st_mode & stat.S_IXUSR


def test_runtime_copy_includes_binary_companion_files(tmp_path) -> None:
    binary = tmp_path / "raytracer"
    binary.write_bytes(b"launcher")
    (tmp_path / "raytracer.py").write_bytes(b"implementation")

    runtime_binary = prepare_runtime_dir(binary, tmp_path / "runtime")

    assert runtime_binary.read_bytes() == b"launcher"
    assert (runtime_binary.parent / "raytracer.py").read_bytes() == b"implementation"
