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


def test_calculate_sampling_rate_scales_with_reputation() -> None:
    from workloads.raytracer.raytracer_workload import calculate_sampling_rate

    # Worker with 0 reputation -> 1.0 (100% full verification)
    assert calculate_sampling_rate(0.0) == 1.0
    # Worker with 50 reputation -> 0.6 (60% sampling)
    assert calculate_sampling_rate(50.0) == 0.6
    # Worker with 100 reputation -> 0.2 (20% sampling)
    assert calculate_sampling_rate(100.0) == 0.2
    # High reputation worker capped at min_rate = 0.2
    assert calculate_sampling_rate(150.0) == 0.2


def test_select_probabilistic_milestones_is_deterministic_per_seed() -> None:
    from workloads.raytracer.raytracer_workload import build_verification_milestones, select_probabilistic_milestones

    width = 2
    height = 20
    rows = [bytes([val]) * width * 3 for val in range(height)]
    manifest = build_verification_milestones(_ppm(width, height, b"".join(rows)), 0, batch_rows=2)

    # 10 milestones total, 30% sample rate -> 3 milestones selected
    sample1 = select_probabilistic_milestones(manifest, seed="nonce-12345", sample_rate=0.3)
    sample2 = select_probabilistic_milestones(manifest, seed="nonce-12345", sample_rate=0.3)
    sample_diff_seed = select_probabilistic_milestones(manifest, seed="nonce-99999", sample_rate=0.3)

    assert len(sample1) == 3
    assert [ms["index"] for ms in sample1] == [ms["index"] for ms in sample2]
    assert [ms["index"] for ms in sample1] != [ms["index"] for ms in sample_diff_seed]


def test_detection_probability_calculation() -> None:
    from workloads.raytracer.raytracer_workload import detection_probability

    # If 0 tampered -> 0% detection
    assert detection_probability(10, 0, 3) == 0.0
    # If 1 tampered out of 10, sampling 3 -> 30% detection
    assert detection_probability(10, 1, 3) == 0.3
    # If 5 tampered out of 10, sampling 3 -> ~91.7% detection
    assert detection_probability(10, 5, 3) == 0.9167
    # Full sampling -> 100% detection
    assert detection_probability(10, 1, 10) == 1.0


def test_verify_probabilistic_milestones_passes_and_escalates_on_tampering() -> None:
    from workloads.raytracer.raytracer_workload import build_verification_milestones, verify_probabilistic_milestones

    width = 2
    height = 10
    pixels = bytearray(range(width * height * 3))
    clean_ppm = _ppm(width, height, bytes(pixels))
    manifest = build_verification_milestones(clean_ppm, 0, batch_rows=2)

    # 1. Clean verification with reputation = 100 (20% sampling)
    res_clean = verify_probabilistic_milestones(clean_ppm, manifest, seed="seed-abc", reputation_score=100.0)
    assert res_clean["verified"] is True
    assert res_clean["escalated_to_full"] is False

    # 2. Tampered verification
    tampered_pixels = bytearray(pixels)
    tampered_pixels[0] ^= 0xFF
    tampered_ppm = _ppm(width, height, bytes(tampered_pixels))
    res_tampered = verify_probabilistic_milestones(tampered_ppm, manifest, seed="seed-abc", reputation_score=0.0)

    assert res_tampered["verified"] is False
    assert res_tampered["escalated_to_full"] is True
    assert len(res_tampered["failed_milestones"]) > 0

