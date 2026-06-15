from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

try:
    from .render3d_workload import load_scene, render_scene, sha256_bytes, sha256_file, write_json
except ImportError:  # pragma: no cover - direct script execution
    from render3d_workload import load_scene, render_scene, sha256_bytes, sha256_file, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute a render3d scene or fragment.")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--result-json", default="")
    parser.add_argument("--y-start", type=int, default=0)
    parser.add_argument("--y-end", default="")
    args = parser.parse_args()

    scene_path = Path(args.scene).resolve()
    output_path = Path(args.output).resolve()
    result_json = Path(args.result_json).resolve() if args.result_json else None
    scene = load_scene(scene_path)
    y_end = int(args.y_end) if args.y_end else None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = render_scene(scene, args.y_start, y_end)
    output_path.write_bytes(image_bytes)
    result = {
        "schema_version": 1,
        "workload": "render3d",
        "entrypoint": "compute",
        "scene_path": str(scene_path),
        "scene_sha256": sha256_file(scene_path),
        "result_path": str(output_path),
        "result_sha256": sha256_bytes(image_bytes),
        "result_format": "ppm/p6",
        "fragment": {"y_start": args.y_start, "y_end": y_end},
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if result_json:
        write_json(result_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
