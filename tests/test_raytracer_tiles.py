import shutil
from pathlib import Path

from workloads.raytracer.raytracer_workload import parse_ppm_bytes, run_raytracer
from workloads.raytracer.run_network_job import build_performance_summary


def test_raytracer_rectangular_crop_matches_full_render(tmp_path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("SILICIUM_RAYTRACER_BIN", str(root / "tests" / "fixtures" / "python_raytracer.py"))
    scene = root / "workloads" / "raytracer" / "examples" / "demo-scene.cfg"
    full_path = tmp_path / "full.ppm"
    tile_path = tmp_path / "tile.ppm"

    run_raytracer(scene, full_path)
    run_raytracer(scene, tile_path, y_start=40, y_end=90, x_start=70, x_end=150)

    full_width, _, full_pixels = parse_ppm_bytes(full_path.read_bytes())
    tile_width, tile_height, tile_pixels = parse_ppm_bytes(tile_path.read_bytes())
    expected = bytearray()
    for y in range(40, 90):
        start = (y * full_width + 70) * 3
        expected.extend(full_pixels[start : start + tile_width * 3])
    assert (tile_width, tile_height) == (80, 50)
    assert tile_pixels == bytes(expected)


def test_uploaded_scene_file_runs_through_compute_path(tmp_path, monkeypatch) -> None:
    """Exercise the same file-backed path used by a site-created job."""
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("SILICIUM_RAYTRACER_BIN", str(root / "tests" / "fixtures" / "python_raytracer.py"))
    source = root / "workloads" / "raytracer" / "examples" / "demo-scene.cfg"
    submitted_scene = tmp_path / "site-render-42" / "input" / "demo-scene.cfg"
    submitted_scene.parent.mkdir(parents=True)
    shutil.copy2(source, submitted_scene)

    output = tmp_path / "site-render-42" / "fragments" / "fragment-000.ppm"
    result = run_raytracer(submitted_scene, output, y_start=0, y_end=20, x_start=0, x_end=32)

    width, height, pixels = parse_ppm_bytes(output.read_bytes(), str(output))
    assert result["returncode"] == 0
    assert result["result_path"] == str(output.resolve())
    assert result["performance"]["compute_ms"] > 0
    assert (width, height) == (32, 20)
    assert len(pixels) == width * height * 3


def test_performance_summary_merges_parallel_compute_intervals() -> None:
    records = [
        {
            "role": "compute",
            "compute_ms": 100,
            "network_ms": 25,
            "worker_overhead_ms": 30,
            "compute_started_unix_ms": 1_000,
            "compute_finished_unix_ms": 1_100,
        },
        {
            "role": "compute",
            "compute_ms": 150,
            "network_ms": 35,
            "worker_overhead_ms": 40,
            "compute_started_unix_ms": 1_050,
            "compute_finished_unix_ms": 1_200,
        },
        {"role": "verify", "compute_ms": 20, "network_ms": 10},
    ]

    summary = build_performance_summary(records, 300)

    assert summary["compute_ms"] == 200
    assert summary["compute_work_ms"] == 250
    assert summary["verification_ms"] == 20
    assert summary["network_ms"] == 70
    assert summary["compute_to_total_ratio"] == 0.6667
    assert summary["compute_to_network_ratio"] == 3.5714
    assert summary["parallelism_factor"] == 1.25
