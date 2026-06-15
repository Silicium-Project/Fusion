from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORKLOAD_ROOT = Path(__file__).resolve().parent
NETWORK_ROOT = WORKLOAD_ROOT.parents[1]
DEFAULT_SCENE = NETWORK_ROOT / "demo" / "render3d" / "scene.json"
DEFAULT_EXPORT_DIR = NETWORK_ROOT / ".silicium" / "mcp" / "export"
DEFAULT_OUTPUT_ROOT = NETWORK_ROOT / ".silicium" / "demo" / "render3d"


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, value: float) -> "Vec3":
        return Vec3(self.x * value, self.y * value, self.z * value)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def normalized(self) -> "Vec3":
        length = math.sqrt(max(1e-12, self.dot(self)))
        return self * (1.0 / length)


def vec3(value: Any, default: tuple[float, float, float]) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        return Vec3(*default)
    return Vec3(float(value[0]), float(value[1]), float(value[2]))


def color(value: Any, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        return default
    return tuple(max(0, min(255, int(channel))) for channel in value)  # type: ignore[return-value]


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def ppm_to_png_bytes(ppm: bytes) -> bytes:
    offset = 0

    def read_token() -> bytes:
        nonlocal offset
        while offset < len(ppm) and ppm[offset] in b" \t\r\n":
            offset += 1
        if offset < len(ppm) and ppm[offset] == ord("#"):
            while offset < len(ppm) and ppm[offset] not in b"\r\n":
                offset += 1
            return read_token()
        start = offset
        while offset < len(ppm) and ppm[offset] not in b" \t\r\n":
            offset += 1
        return ppm[start:offset]

    magic = read_token()
    if magic != b"P6":
        raise ValueError("only binary P6 PPM files are supported")
    width = int(read_token())
    height = int(read_token())
    max_value = int(read_token())
    if max_value != 255:
        raise ValueError("only 8-bit PPM files are supported")
    while offset < len(ppm) and ppm[offset] in b" \t\r\n":
        offset += 1
    rgb = ppm[offset:]
    expected = width * height * 3
    if len(rgb) != expected:
        raise ValueError(f"invalid PPM payload size: expected {expected}, got {len(rgb)}")

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(rgb[y * stride : (y + 1) * stride])

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def write_png_from_ppm(ppm_path: Path, png_path: Path) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(ppm_to_png_bytes(ppm_path.read_bytes()))


def intersect_sphere(origin: Vec3, direction: Vec3, center: Vec3, radius: float) -> float | None:
    oc = origin - center
    a = direction.dot(direction)
    b = 2.0 * oc.dot(direction)
    c = oc.dot(oc) - radius * radius
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0:
        return None
    root = math.sqrt(discriminant)
    near = (-b - root) / (2.0 * a)
    far = (-b + root) / (2.0 * a)
    if near > 1e-4:
        return near
    if far > 1e-4:
        return far
    return None


def render_scene(scene: dict[str, Any], y_start: int = 0, y_end: int | None = None) -> bytes:
    image = scene.get("image") if isinstance(scene.get("image"), dict) else {}
    camera = scene.get("camera") if isinstance(scene.get("camera"), dict) else {}
    light = scene.get("light") if isinstance(scene.get("light"), dict) else {}
    objects = scene.get("objects") if isinstance(scene.get("objects"), list) else []

    width = max(16, min(2048, int(image.get("width", 320))))
    height = max(16, min(2048, int(image.get("height", 200))))
    y_start = max(0, min(height, int(y_start)))
    y_end = height if y_end is None else max(0, min(height, int(y_end)))
    if y_end <= y_start:
        raise ValueError("invalid render band")
    fragment_height = y_end - y_start
    background = color(image.get("background"), (18, 24, 38))

    origin = vec3(camera.get("position"), (0.0, 0.4, 3.8))
    look_at = vec3(camera.get("look_at"), (0.0, 0.0, 0.0))
    forward = (look_at - origin).normalized()
    right = forward.cross(Vec3(0.0, 1.0, 0.0)).normalized()
    up = right.cross(forward).normalized()
    fov = math.radians(float(camera.get("fov_degrees", 45)))
    scale = math.tan(fov * 0.5)
    aspect = width / height

    light_dir = vec3(light.get("direction"), (-0.4, -0.8, -0.5)).normalized() * -1.0
    ambient = max(0.0, min(1.0, float(light.get("ambient", 0.22))))

    spheres: list[dict[str, Any]] = []
    for obj in objects:
        if isinstance(obj, dict) and obj.get("type") == "sphere":
            spheres.append(obj)

    pixels = bytearray()
    for y in range(y_start, y_end):
        py = (1.0 - 2.0 * ((y + 0.5) / height)) * scale
        for x in range(width):
            px = (2.0 * ((x + 0.5) / width) - 1.0) * aspect * scale
            ray = (forward + right * px + up * py).normalized()
            best_t = float("inf")
            best_obj: dict[str, Any] | None = None
            for sphere in spheres:
                hit = intersect_sphere(
                    origin,
                    ray,
                    vec3(sphere.get("center"), (0.0, 0.0, 0.0)),
                    float(sphere.get("radius", 0.5)),
                )
                if hit is not None and hit < best_t:
                    best_t = hit
                    best_obj = sphere
            if best_obj is None:
                vignette = 0.82 + 0.18 * (1.0 - abs((y / max(1, height - 1)) - 0.5))
                pixels.extend(max(0, min(255, int(c * vignette))) for c in background)
                continue

            center = vec3(best_obj.get("center"), (0.0, 0.0, 0.0))
            hit_point = origin + ray * best_t
            normal = (hit_point - center).normalized()
            diffuse = max(0.0, normal.dot(light_dir))
            shade = ambient + (1.0 - ambient) * diffuse
            base = color(best_obj.get("color"), (220, 220, 220))
            pixels.extend(max(0, min(255, int(channel * shade))) for channel in base)

    header = f"P6\n{width} {fragment_height}\n255\n".encode("ascii")
    return header + bytes(pixels)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True), encoding="utf-8")


def load_scene(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scene root must be an object")
    return payload


def submit_task(export_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    sys.path.insert(0, str(NETWORK_ROOT))
    from tools.mcp_server import McpTaskStore

    return McpTaskStore(export_dir).submit(payload)


def build_compute_payload(manifest: dict[str, Any], priority: str) -> dict[str, Any]:
    return {
        "task_id": manifest["task_id"],
        "required_roles": ["compute"],
        "priority": priority,
        "p2p_ref": {
            "protocol": "file",
            "content_id": manifest["scene_path"],
            "hash": "sha256:" + manifest["scene_sha256"],
        },
        "task": {
            "kind": "compute",
            "workload": "calcul/rendering/demo-render3d",
            "scene_sha256": manifest["scene_sha256"],
            "expected_result_sha256": manifest["result_sha256"],
            "result_path": manifest["result_path"],
            "result_format": manifest["result_format"],
            "note": "Manual render3d demo task. The scene file is provided directly to the network.",
        },
    }


def build_verify_payload(
    manifest: dict[str, Any],
    compute_payload: dict[str, Any],
    p2p_ref: dict[str, Any],
    expected_hash: str,
    priority: str,
) -> dict[str, Any]:
    return {
        "task_id": f"{manifest['task_id']}-verify",
        "required_roles": ["verify"],
        "priority": priority,
        "p2p_ref": p2p_ref,
        "task": {
            "kind": "verify",
            "workload": "verification/rendering/demo-render3d",
            "expected_hash": "sha256:" + expected_hash.removeprefix("sha256:"),
            "scene_p2p_ref": compute_payload["p2p_ref"],
            "source_task_id": manifest["task_id"],
        },
    }


def build_demo(scene_path: Path, output_root: Path, task_id: str) -> dict[str, Any]:
    scene = load_scene(scene_path)
    job_dir = output_root / task_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    scene_copy = input_dir / "scene.json"
    shutil.copyfile(scene_path, scene_copy)

    image_bytes = render_scene(scene)
    image_path = output_dir / "render.ppm"
    image_path.write_bytes(image_bytes)
    preview_path = output_dir / "render.png"
    preview_path.write_bytes(ppm_to_png_bytes(image_bytes))

    scene_hash = sha256_file(scene_copy)
    image_hash = sha256_bytes(image_bytes)
    manifest = {
        "schema_version": 1,
        "task_id": task_id,
        "workload": "calcul/rendering/demo-render3d",
        "scene_path": str(scene_copy.resolve()),
        "scene_sha256": scene_hash,
        "result_path": str(image_path.resolve()),
        "preview_path": str(preview_path.resolve()),
        "result_sha256": image_hash,
        "result_format": "ppm/p6",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(job_dir / "manifest.json", manifest)
    return manifest


def command_render(args: argparse.Namespace) -> int:
    scene_path = Path(args.scene).resolve()
    task_id = args.task_id or f"render3d-{int(time.time())}"
    manifest = build_demo(scene_path, Path(args.output_root).resolve(), task_id)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def command_submit(args: argparse.Namespace) -> int:
    scene_path = Path(args.scene).resolve()
    task_id = args.task_id or f"render3d-{int(time.time())}"
    output_root = Path(args.output_root).resolve()
    export_dir = Path(args.export_dir).resolve()
    manifest = build_demo(scene_path, output_root, task_id)

    compute_payload = build_compute_payload(manifest, args.priority)
    verify_payload = build_verify_payload(
        manifest,
        compute_payload,
        {
            "protocol": "file",
            "content_id": manifest["result_path"],
            "hash": "sha256:" + manifest["result_sha256"],
        },
        manifest["result_sha256"],
        args.priority,
    )

    write_json(Path(manifest["result_path"]).parents[1] / "compute-task.json", compute_payload)
    write_json(Path(manifest["result_path"]).parents[1] / "verify-task.json", verify_payload)

    result = {
        "manifest": manifest,
        "submitted": [],
    }
    if not args.no_queue:
        result["submitted"].append(submit_task(export_dir, compute_payload))
        result["submitted"].append(submit_task(export_dir, verify_payload))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_worker_run(args: argparse.Namespace) -> int:
    scene_path = Path(args.scene).resolve()
    output_path = Path(args.output).resolve()
    result_json = Path(args.result_json).resolve() if args.result_json else None
    scene = load_scene(scene_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    y_end = int(args.y_end) if args.y_end else None
    image_bytes = render_scene(scene, int(args.y_start), y_end)
    output_path.write_bytes(image_bytes)

    result = {
        "schema_version": 1,
        "workload": "calcul/rendering/demo-render3d",
        "scene_path": str(scene_path),
        "scene_sha256": sha256_file(scene_path),
        "result_path": str(output_path),
        "result_sha256": sha256_bytes(image_bytes),
        "result_format": "ppm/p6",
        "fragment": {
            "y_start": int(args.y_start),
            "y_end": y_end,
        },
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if result_json is not None:
        write_json(result_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_convert(args: argparse.Namespace) -> int:
    ppm_path = Path(args.ppm).resolve()
    png_path = Path(args.png).resolve() if args.png else ppm_path.with_suffix(".png")
    write_png_from_ppm(ppm_path, png_path)
    result = {
        "schema_version": 1,
        "ppm_path": str(ppm_path),
        "png_path": str(png_path),
        "png_sha256": sha256_file(png_path),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Silicium render3d workload entrypoints.")
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="Render a scene locally and write demo artifacts.")
    render.add_argument("scene", nargs="?", default=str(DEFAULT_SCENE))
    render.add_argument("--task-id", default="")
    render.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    render.set_defaults(func=command_render)

    submit = sub.add_parser("submit", help="Render, build Silicium task envelopes, and queue them.")
    submit.add_argument("scene", nargs="?", default=str(DEFAULT_SCENE))
    submit.add_argument("--task-id", default="")
    submit.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    submit.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    submit.add_argument("--priority", default="high", choices=["low", "normal", "high", "urgent"])
    submit.add_argument("--no-queue", action="store_true", help="Only write task JSON files; do not enqueue them.")
    submit.set_defaults(func=command_submit)

    worker = sub.add_parser("worker-run", help="Renderer entrypoint used by network_node.")
    worker.add_argument("--scene", required=True)
    worker.add_argument("--output", required=True)
    worker.add_argument("--result-json", default="")
    worker.add_argument("--y-start", type=int, default=0)
    worker.add_argument("--y-end", default="")
    worker.set_defaults(func=command_worker_run)

    convert = sub.add_parser("convert", help="Convert a P6 PPM render output to PNG.")
    convert.add_argument("ppm")
    convert.add_argument("png", nargs="?")
    convert.set_defaults(func=command_convert)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
