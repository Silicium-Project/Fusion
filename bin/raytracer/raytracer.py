#!/usr/bin/env python3
"""
Silicium Native Python Raytracer Fallback
Renders .cfg scene files to binary PPM (P6) format with support for raytraced spheres, planes, and point lights.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

class Vec3:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalize(self) -> Vec3:
        l = self.length()
        if l == 0:
            return Vec3(0, 0, 0)
        return Vec3(self.x / l, self.y / l, self.z / l)

class Ray:
    __slots__ = ("origin", "direction")

    def __init__(self, origin: Vec3, direction: Vec3) -> None:
        self.origin = origin
        self.direction = direction.normalize()

    def point_at(self, t: float) -> Vec3:
        return self.origin + self.direction * t

class Sphere:
    def __init__(self, pos: Vec3, radius: float, color: Vec3) -> None:
        self.pos = pos
        self.radius = float(radius)
        self.color = color

    def intersect(self, ray: Ray) -> tuple[float, Vec3] | None:
        oc = ray.origin - self.pos
        b = 2.0 * oc.dot(ray.direction)
        c = oc.dot(oc) - self.radius * self.radius
        disc = b * b - 4 * c
        if disc < 0:
            return None
        sqrt_d = math.sqrt(disc)
        t1 = (-b - sqrt_d) / 2.0
        t2 = (-b + sqrt_d) / 2.0
        t = t1 if t1 > 0.001 else (t2 if t2 > 0.001 else None)
        if t is None:
            return None
        hit = ray.point_at(t)
        normal = (hit - self.pos).normalize()
        return t, normal

class Plane:
    def __init__(self, pos: Vec3, normal: Vec3, color: Vec3) -> None:
        self.pos = pos
        self.normal = normal.normalize()
        self.color = color

    def intersect(self, ray: Ray) -> tuple[float, Vec3] | None:
        denom = self.normal.dot(ray.direction)
        if abs(denom) < 1e-6:
            return None
        t = (self.pos - ray.origin).dot(self.normal) / denom
        if t <= 0.001:
            return None
        normal = self.normal if denom < 0 else self.normal * -1.0
        return t, normal

class Light:
    def __init__(self, pos: Vec3, intensity: float) -> None:
        self.pos = pos
        self.intensity = float(intensity)

def parse_cfg(path: Path) -> tuple[int, int, float, Vec3, list[Any], list[Light]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    
    # Default resolution & camera settings
    width, height = 320, 200
    fov = 55.0
    cam_pos = Vec3(0, 0, 0)
    
    w_match = re.search(r"width\s*=\s*(\d+)", text, re.IGNORECASE)
    h_match = re.search(r"height\s*=\s*(\d+)", text, re.IGNORECASE)
    if w_match:
        width = int(w_match.group(1))
    if h_match:
        height = int(h_match.group(1))

    fov_match = re.search(r"fieldOfView\s*=\s*([\d.]+)", text, re.IGNORECASE)
    if fov_match:
        fov = float(fov_match.group(1))

    cam_pos_match = re.search(r"camera\s*:[\s\S]*?position\s*=\s*\{[^}]*x\s*=\s*([-\d.]+)[^}]*y\s*=\s*([-\d.]+)[^}]*z\s*=\s*([-\d.]+)", text, re.IGNORECASE)
    if cam_pos_match:
        cam_pos = Vec3(float(cam_pos_match.group(1)), float(cam_pos_match.group(2)), float(cam_pos_match.group(3)))

    primitives: list[Any] = []
    # Parse spheres
    for m in re.finditer(r"sphere\s*=\s*\{[^}]*x\s*=\s*([-\d.]+)[^}]*y\s*=\s*([-\d.]+)[^}]*z\s*=\s*([-\d.]+)[^}]*radius\s*=\s*([\d.]+)[^}]*color\s*=\s*\{[^}]*r\s*=\s*(\d+)[^}]*g\s*=\s*(\d+)[^}]*b\s*=\s*(\d+)", text, re.IGNORECASE):
        pos = Vec3(float(m.group(1)), float(m.group(2)), float(m.group(3)))
        radius = float(m.group(4))
        color = Vec3(int(m.group(5)) / 255.0, int(m.group(6)) / 255.0, int(m.group(7)) / 255.0)
        primitives.append(Sphere(pos, radius, color))

    # Parse planes
    for m in re.finditer(r"plane\s*=\s*\{[^}]*x\s*=\s*([-\d.]+)[^}]*y\s*=\s*([-\d.]+)[^}]*z\s*=\s*([-\d.]+)[^}]*normal_x\s*=\s*([-\d.]+)[^}]*normal_y\s*=\s*([-\d.]+)[^}]*normal_z\s*=\s*([-\d.]+)[^}]*color\s*=\s*\{[^}]*r\s*=\s*(\d+)[^}]*g\s*=\s*(\d+)[^}]*b\s*=\s*(\d+)", text, re.IGNORECASE):
        pos = Vec3(float(m.group(1)), float(m.group(2)), float(m.group(3)))
        norm = Vec3(float(m.group(4)), float(m.group(5)), float(m.group(6)))
        color = Vec3(int(m.group(7)) / 255.0, int(m.group(8)) / 255.0, int(m.group(9)) / 255.0)
        primitives.append(Plane(pos, norm, color))

    lights: list[Light] = []
    # Parse point lights
    for m in re.finditer(r"point\s*=\s*\{[^}]*x\s*=\s*([-\d.]+)[^}]*y\s*=\s*([-\d.]+)[^}]*z\s*=\s*([-\d.]+)[^}]*intensity\s*=\s*([\d.]+)", text, re.IGNORECASE):
        pos = Vec3(float(m.group(1)), float(m.group(2)), float(m.group(3)))
        intensity = float(m.group(4))
        lights.append(Light(pos, intensity))

    if not lights:
        lights.append(Light(Vec3(4, 0, 5), 450.0))

    return width, height, fov, cam_pos, primitives, lights


def render(
    scene_path: Path,
    output_path: Path,
    y_start: int | None,
    y_end: int | None,
    x_start: int | None,
    x_end: int | None,
) -> None:
    width, height, fov, cam_pos, primitives, lights = parse_cfg(scene_path)

    y0 = 0 if y_start is None else max(0, min(y_start, height))
    y1 = height if y_end is None else max(0, min(y_end, height))
    x0 = 0 if x_start is None else max(0, min(x_start, width))
    x1 = width if x_end is None else max(0, min(x_end, width))

    aspect_ratio = width / float(height)
    scale = math.tan(math.radians(fov * 0.5))

    pixels = bytearray()

    for y in range(y0, y1):
        for x in range(x0, x1):
            # Map pixel to camera space (looking along +X axis)
            px = (2.0 * (x + 0.5) / float(width) - 1.0) * aspect_ratio * scale
            py = (1.0 - 2.0 * (y + 0.5) / float(height)) * scale
            dir_vec = Vec3(1.0, -px, py).normalize()
            ray = Ray(cam_pos, dir_vec)

            closest_t = float("inf")
            hit_prim = None
            hit_normal = Vec3()

            for prim in primitives:
                res = prim.intersect(ray)
                if res is not None:
                    t, norm = res
                    if t < closest_t:
                        closest_t = t
                        hit_prim = prim
                        hit_normal = norm

            if hit_prim is None:
                # Sky background gradient
                t_sky = 0.5 * (dir_vec.z + 1.0)
                r_c = int((1.0 - t_sky) * 20 + t_sky * 100)
                g_c = int((1.0 - t_sky) * 30 + t_sky * 140)
                b_c = int((1.0 - t_sky) * 50 + t_sky * 220)
            else:
                hit_pt = ray.point_at(closest_t)
                ambient = 0.15
                diffuse = 0.0

                for light in lights:
                    light_dir = (light.pos - hit_pt).normalize()
                    dist_sq = (light.pos - hit_pt).length() ** 2
                    cos_theta = max(0.0, hit_normal.dot(light_dir))
                    attenuation = min(1.0, light.intensity / (dist_sq + 1.0))
                    diffuse += cos_theta * attenuation

                intensity_factor = min(1.0, ambient + diffuse)
                r_c = int(min(255, hit_prim.color.x * 255.0 * intensity_factor))
                g_c = int(min(255, hit_prim.color.y * 255.0 * intensity_factor))
                b_c = int(min(255, hit_prim.color.z * 255.0 * intensity_factor))

            pixels.extend([r_c, g_c, b_c])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"P6\n{x1 - x0} {y1 - y0}\n255\n".encode("ascii")
    output_path.write_bytes(header + bytes(pixels))

def main() -> None:
    parser = argparse.ArgumentParser(description="Silicium Raytracer")
    parser.add_argument("scene", type=Path, help="Scene configuration file (.cfg)")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output PPM file path")
    parser.add_argument("--y-start", type=int, default=None, help="Start Y coordinate")
    parser.add_argument("--y-end", type=int, default=None, help="End Y coordinate")
    parser.add_argument("--x-start", type=int, default=None, help="Start X coordinate")
    parser.add_argument("--x-end", type=int, default=None, help="End X coordinate")
    args, _ = parser.parse_known_args()

    render(args.scene, args.output, args.y_start, args.y_end, args.x_start, args.x_end)

if __name__ == "__main__":
    main()
