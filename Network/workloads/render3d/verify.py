from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .render3d_workload import load_scene, render_scene, sha256_bytes, write_json
except ImportError:  # pragma: no cover - direct script execution
    from render3d_workload import load_scene, render_scene, sha256_bytes, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a render3d result by deterministic recompute.")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--expected-hash", default="")
    parser.add_argument("--result-json", default="")
    parser.add_argument("--y-start", type=int, default=0)
    parser.add_argument("--y-end", default="")
    args = parser.parse_args()

    scene = load_scene(Path(args.scene).resolve())
    y_end = int(args.y_end) if args.y_end else None
    actual = sha256_bytes(Path(args.result).resolve().read_bytes())
    recomputed = sha256_bytes(render_scene(scene, args.y_start, y_end))
    declared = str(args.expected_hash or "").removeprefix("sha256:")
    verified = actual == recomputed and ((not declared) or declared == actual)
    payload = {
        "schema_version": 1,
        "workload": "render3d",
        "entrypoint": "verify",
        "actual_hash": actual,
        "recomputed_hash": recomputed,
        "expected_hash": declared,
        "verified": verified,
        "choice": verified,
        "fragment": {"y_start": args.y_start, "y_end": y_end},
    }
    if args.result_json:
        write_json(Path(args.result_json).resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
