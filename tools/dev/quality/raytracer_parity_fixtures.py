#!/usr/bin/env python3
"""Generate the fixtures that keep the Rust tile pipeline (`crates/raytracer`)
byte-for-byte aligned with the Python code still used by the nodes
(`workloads/raytracer`: milestones, sampling, PPM parsing, fragment checks).

The split, fragment-estimate and reassembly cases are frozen: their Python
implementation was removed once the Rust pipeline became the only one, so the
generator keeps the recorded cases from the existing fixture file.

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
    frozen = json.loads(OUTPUT.read_text(encoding="utf-8"))
    split_cases = frozen["split"]
    estimate_cases = frozen["estimate"]
    reassembly = frozen["reassembly"]

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

    validate_cases = []
    tile = pattern_ppm(4, 3, 1)
    tile_hash = hashlib.sha256(tile).hexdigest()
    for label, data, width, height, expected in [
        ("ok", tile, 4, 3, tile_hash),
        ("ok-prefixed-hash", tile, None, None, "sha256:" + tile_hash.upper()),
        ("dimensions", tile, 5, 3, None),
        ("width-only", tile, 5, None, None),
        ("height-only", tile, None, 9, None),
        ("hash", tile, None, None, "0" * 64),
        ("invalid", b"not a ppm", None, None, None),
    ]:
        case = {"label": label, "data": list(data), "width": width, "height": height, "expected_hash": expected}
        try:
            case["ok"] = rw.validate_fragment_ppm(data, task_id=label, expected_width=width, expected_height=height, expected_hash=expected)
        except RuntimeError as exc:
            case["error"] = str(exc)
        validate_cases.append(case)

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
        "validate": validate_cases,
    }
    OUTPUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")  # i18n:ignore -- developer tool output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
