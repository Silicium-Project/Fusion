#!/usr/bin/env python3
"""Generate the fixtures that keep the Rust tile pipeline (`crates/raytracer`)
byte-for-byte aligned with the legacy Python one (`workloads/raytracer`).

Run from Network/: `python3 tools/dev/quality/raytracer_parity_fixtures.py`.
The Rust tests (`cargo test -p silicium-raytracer`) read the output.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from workloads.raytracer import raytracer_workload as rw  # noqa: E402

OUTPUT = ROOT / "crates" / "raytracer" / "tests" / "fixtures" / "python_parity.json"


def pattern_ppm(width: int, height: int, seed: int) -> bytes:
    """Deterministic test image; the Rust tests build the same bytes."""
    pixels = bytes((index * 31 + seed * 7) % 256 for index in range(width * height * 3))
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels


def main() -> int:
    split_cases = []
    for width, height in [(320, 200), (1920, 1080), (7, 3), (1, 1), (640, 480), (100, 1000), (33, 17)]:
        for count in [1, 2, 3, 4, 5, 7, 9, 12, 16, 17, 31, 32, 64]:
            split_cases.append({"width": width, "height": height, "count": count, "tiles": rw.split_tiles(width, height, count)})

    estimate_cases = []
    for width, height, target, maximum in [(320, 200, 120_000, 32), (1920, 1080, 120_000, 32), (100, 3, 10, 32), (4000, 4000, 1, 16), (10, 10, 0, 0)]:
        scene_text = f"camera : {{ resolution = {{ width = {width} height = {height} }} }}"
        estimate_cases.append({"scene": scene_text, "target": target, "max": maximum})

    resolution_texts = [
        "camera : { resolution = { width = 64 height = 32 } fieldOfView = 60 }",
        "CAMERA: { RESOLUTION = { WIDTH = 800\n HEIGHT = 600 } }",
        "camera : { fieldOfView = 60 }",
        "resolution = { linewidth = 3 width = 10 height = 20 }",
        "resolution={width=0 height=0}",
        "resolution = { height = 5 width = 6 }",
    ]
    tmp = ROOT / ".silicium" / "parity-scene.cfg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    resolution_cases = []
    for text in resolution_texts:
        tmp.write_text(text, encoding="utf-8")
        resolution_cases.append({"scene": text, "resolution": list(rw.scene_resolution(tmp))})
    for case in estimate_cases:
        tmp.write_text(case["scene"], encoding="utf-8")
        case["count"] = rw.estimate_fragment_count(tmp, case["target"], case["max"])
    tmp.unlink()

    milestone_cases = []
    for width, height, seed, y_start, x_start, batch in [(16, 45, 1, 0, 0, 20), (5, 7, 2, 108, 320, 2), (3, 1, 3, 5, 0, 20), (8, 20, 4, 0, 16, 20), (4, 9, 5, 0, 0, 0)]:
        ppm = pattern_ppm(width, height, seed)
        milestone_cases.append(
            {
                "width": width,
                "height": height,
                "seed": seed,
                "y_start": y_start,
                "x_start": x_start,
                "batch_rows": batch,
                "pixel_sha256": rw.ppm_pixel_sha256(ppm),
                "manifest": rw.build_verification_milestones(ppm, y_start, batch, x_start),
            }
        )

    sampling_rates = [{"reputation": rep, "rate": rw.calculate_sampling_rate(rep)} for rep in [-5, 0, 12.5, 33.3, 50, 77.7, 99.99, 100, 150]]

    base_manifest = rw.build_verification_milestones(pattern_ppm(6, 50, 9), 40, 5, 12)
    selection_cases = []
    for seed in ["", "nonce-1", "abc", "f" * 64]:
        for rate in [0.0, 0.1, 0.25, 0.5, 1.0]:
            chosen = rw.select_probabilistic_milestones(base_manifest, seed, rate)
            selection_cases.append({"seed": seed, "rate": rate, "indices": [item["index"] for item in chosen]})

    detection_cases = []
    for total, tampered, sampled in [(10, 1, 3), (10, 0, 3), (10, 10, 1), (5, 2, 5), (100, 3, 25), (7, 2, 3), (0, 1, 1)]:
        detection_cases.append({"total": total, "tampered": tampered, "sampled": sampled, "probability": rw.detection_probability(total, tampered, sampled)})

    verify_cases = []
    good = pattern_ppm(6, 50, 9)
    tampered = bytearray(good)
    tampered[-1] ^= 0xFF
    for label, ppm in [("good", good), ("tampered", bytes(tampered))]:
        for seed, reputation in [("s1", 50.0), ("s2", 100.0), ("s3", 0.0)]:
            verify_cases.append(
                {
                    "image": label,
                    "seed": seed,
                    "reputation": reputation,
                    "result": rw.verify_probabilistic_milestones(ppm, base_manifest, seed, reputation),
                }
            )

    fragments = [(0, 0, pattern_ppm(4, 3, 1)), (4, 0, pattern_ppm(3, 3, 2)), (0, 3, pattern_ppm(7, 2, 3))]
    width = max(x + int(p.split(b"\n")[1].split()[0]) for x, _, p in fragments)
    reassembly = {"fragments": [{"x": x, "y": y, "width": int(p.split(b"\n")[1].split()[0]), "height": int(p.split(b"\n")[1].split()[1]), "seed": s} for (x, y, p), s in zip(fragments, [1, 2, 3])]}
    out = ROOT / ".silicium" / "parity-reassembled.ppm"
    args = type("A", (), {})()
    args.output = str(out)
    args.fragment = []
    args.x_start = []
    args.y_start = []
    args.png = ""
    args.result_json = ""
    frag_paths = []
    for index, (x, y, ppm) in enumerate(fragments):
        path = ROOT / ".silicium" / f"parity-frag-{index}.ppm"
        path.write_bytes(ppm)
        frag_paths.append(path)
        args.fragment.append(str(path))
        args.x_start.append(str(x))
        args.y_start.append(str(y))
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        rw.command_reassemble(args)
    reassembly["sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
    reassembly["width"] = width
    for path in [out, *frag_paths]:
        path.unlink()

    parse_errors = []
    for label, data in [
        ("p3", b"P3\n1 1\n255\n\x00\x00\x00"),
        ("sixteen-bit", b"P6\n1 1\n65535\n\x00\x00\x00\x00\x00\x00"),
        ("truncated", b"P6\n2 2\n255\n\x00\x00\x00"),
        ("comment", b"P6\n# note\n1 1\n255\n\x01\x02\x03"),
        ("crlf", b"P6\r\n1 1\r\n255\r\n\n\x02\x03"),
        ("no-separator", b"P6\n1 1\n255"),
    ]:
        try:
            parsed = rw.parse_ppm_bytes(data, label)
            parse_errors.append({"label": label, "data": list(data), "ok": [parsed[0], parsed[1], hashlib.sha256(parsed[2]).hexdigest()]})
        except ValueError as exc:
            parse_errors.append({"label": label, "data": list(data), "error": str(exc)})

    payload = {
        "generator": "tools/dev/quality/raytracer_parity_fixtures.py",
        "split": split_cases,
        "estimate": estimate_cases,
        "resolution": resolution_cases,
        "milestones": milestone_cases,
        "sampling_rates": sampling_rates,
        "selection_manifest": base_manifest,
        "selection": selection_cases,
        "detection": detection_cases,
        "verify": verify_cases,
        "reassembly": reassembly,
        "parse": parse_errors,
    }
    OUTPUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")  # i18n:ignore -- developer tool output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
