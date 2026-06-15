from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .render3d_workload import ppm_to_png_bytes, sha256_file, write_json
except ImportError:  # pragma: no cover - direct script execution
    from render3d_workload import ppm_to_png_bytes, sha256_file, write_json


def read_p6_ppm(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    offset = 0

    def token() -> bytes:
        nonlocal offset
        while offset < len(data) and data[offset] in b" \t\r\n":
            offset += 1
        if offset < len(data) and data[offset] == ord("#"):
            while offset < len(data) and data[offset] not in b"\r\n":
                offset += 1
            return token()
        start = offset
        while offset < len(data) and data[offset] not in b" \t\r\n":
            offset += 1
        return data[start:offset]

    if token() != b"P6":
        raise ValueError(f"not a P6 PPM: {path}")
    width = int(token())
    height = int(token())
    max_value = int(token())
    if max_value != 255:
        raise ValueError(f"unsupported PPM max value in {path}: {max_value}")
    while offset < len(data) and data[offset] in b" \t\r\n":
        offset += 1
    rgb = data[offset:]
    if len(rgb) != width * height * 3:
        raise ValueError(f"bad PPM payload size in {path}")
    return width, height, rgb


def main() -> int:
    parser = argparse.ArgumentParser(description="Reassemble render3d horizontal PPM fragments.")
    parser.add_argument("--fragment", action="append", required=True, help="Fragment PPM path in top-to-bottom order.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--png", default="")
    parser.add_argument("--result-json", default="")
    args = parser.parse_args()

    parts = [Path(path).resolve() for path in args.fragment]
    width = 0
    total_height = 0
    rgb_parts: list[bytes] = []
    for path in parts:
        part_width, part_height, rgb = read_p6_ppm(path)
        if width and part_width != width:
            raise ValueError(f"fragment width mismatch: expected {width}, got {part_width}")
        width = part_width
        total_height += part_height
        rgb_parts.append(rgb)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(f"P6\n{width} {total_height}\n255\n".encode("ascii") + b"".join(rgb_parts))
    png_path = Path(args.png).resolve() if args.png else output.with_suffix(".png")
    png_path.write_bytes(ppm_to_png_bytes(output.read_bytes()))
    payload = {
        "schema_version": 1,
        "workload": "render3d",
        "entrypoint": "reassemble",
        "fragment_count": len(parts),
        "result_path": str(output),
        "preview_path": str(png_path),
        "result_sha256": sha256_file(output),
        "preview_sha256": sha256_file(png_path),
    }
    if args.result_json:
        write_json(Path(args.result_json).resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
