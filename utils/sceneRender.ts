// Live preview of a scene: a port of the engine's tracer
// (Network/crates/raytracer/src/{trace,scene,render}.rs). Same maths, run in
// the browser at a small size, so the preview looks like the final render.
// It is not used for results: the network renders with the engine.

import { EPSILON, type RenderPrimitive, type RenderScene } from './scene';

type Vec = [number, number, number];
interface Hit { distance: number; point: Vec; normal: Vec; primitive: number }

const MAX_DEPTH = 3;
const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const add = (a: Vec, b: Vec): Vec => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a: Vec, b: Vec): Vec => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const scale = (a: Vec, factor: number): Vec => [a[0] * factor, a[1] * factor, a[2] * factor];
const clamp01 = (a: Vec): Vec => [Math.min(1, Math.max(0, a[0])), Math.min(1, Math.max(0, a[1])), Math.min(1, Math.max(0, a[2]))];
function normalize(a: Vec): Vec {
  const length = Math.sqrt(dot(a, a));
  return length <= EPSILON ? [0, 0, 0] : scale(a, 1 / length);
}
const reflect = (a: Vec, normal: Vec): Vec => sub(a, scale(normal, 2 * dot(a, normal)));

function intersect(primitive: RenderPrimitive, origin: Vec, direction: Vec): { distance: number; point: Vec; normal: Vec } | undefined {
  if (primitive.kind === 'sphere') {
    const offset = sub(origin, primitive.center);
    const halfB = dot(offset, direction);
    const c = dot(offset, offset) - primitive.radius * primitive.radius;
    const discriminant = halfB * halfB - c;
    if (discriminant < 0) return undefined;
    const root = Math.sqrt(discriminant);
    const first = -halfB - root;
    const second = -halfB + root;
    const distance = first > EPSILON ? first : second > EPSILON ? second : undefined;
    if (distance === undefined) return undefined;
    const point = add(origin, scale(direction, distance));
    return { distance, point, normal: normalize(sub(point, primitive.center)) };
  }
  const denominator = dot(primitive.normal, direction);
  if (Math.abs(denominator) < EPSILON) return undefined;
  const distance = dot(sub(primitive.point, origin), primitive.normal) / denominator;
  if (distance <= EPSILON) return undefined;
  return { distance, point: add(origin, scale(direction, distance)), normal: denominator < 0 ? primitive.normal : scale(primitive.normal, -1) };
}

function nearestHit(scene: RenderScene, origin: Vec, direction: Vec): Hit | undefined {
  let best: Hit | undefined;
  scene.primitives.forEach((primitive, index) => {
    const hit = intersect(primitive, origin, direction);
    if (hit && (!best || hit.distance < best.distance)) best = { ...hit, primitive: index };
  });
  return best;
}

function background(direction: Vec): Vec {
  const amount = (direction[2] + 1) * 0.5;
  return add(scale([0.04, 0.07, 0.13], 1 - amount), scale([0.34, 0.55, 0.9], amount));
}

function trace(scene: RenderScene, origin: Vec, direction: Vec, depth: number): Vec {
  const hit = nearestHit(scene, origin, direction);
  if (!hit) return background(direction);
  const material = scene.primitives[hit.primitive]!.material;
  let diffuse: Vec = [0.09, 0.09, 0.11];
  let specular: Vec = [0, 0, 0];
  const view = scale(direction, -1);
  for (const light of scene.lights) {
    const displacement = sub(light.position, hit.point);
    const distanceSquared = Math.max(dot(displacement, displacement), 1);
    const distance = Math.sqrt(distanceSquared);
    const toLight = scale(displacement, 1 / distance);
    const shadow = nearestHit(scene, add(hit.point, scale(hit.normal, EPSILON * 4)), toLight);
    if (shadow && shadow.distance < distance - EPSILON) continue;
    const attenuation = Math.min(light.intensity / distanceSquared, 1.5);
    const lambert = Math.max(dot(hit.normal, toLight), 0);
    diffuse = add(diffuse, scale(light.color, lambert * attenuation));
    const reflectedLight = normalize(reflect(scale(toLight, -1), hit.normal));
    const highlight = Math.max(dot(reflectedLight, view), 0) ** material.shininess * material.specular * attenuation;
    specular = add(specular, scale(light.color, highlight));
  }
  const local = add([material.color[0] * diffuse[0], material.color[1] * diffuse[1], material.color[2] * diffuse[2]], specular);
  if (depth >= MAX_DEPTH || material.reflectivity <= 0) return clamp01(local);
  const reflected = trace(scene, add(hit.point, scale(hit.normal, EPSILON * 4)), normalize(reflect(direction, hit.normal)), depth + 1);
  return clamp01(add(scale(local, 1 - material.reflectivity), scale(reflected, material.reflectivity)));
}

/** Direction of the camera ray through pixel (x, y) of a `width`×`height` image. */
function primaryRay(scene: RenderScene, x: number, y: number, width: number, height: number): Vec {
  const aspect = scene.width / scene.height;
  const tangent = Math.tan(scene.fov * (Math.PI / 180) * 0.5);
  const px = (2 * (x + 0.5) / width - 1) * aspect * tangent;
  const py = (1 - 2 * (y + 0.5) / height) * tangent;
  return normalize([1, -px, py]);
}

/** Size of a preview at most `maxWidth` wide with the scene's aspect ratio. */
export function previewSize(scene: Pick<RenderScene, 'width' | 'height'>, maxWidth: number, maxHeight = maxWidth): { width: number; height: number } {
  const ratio = Math.min(maxWidth / scene.width, maxHeight / scene.height, 1);
  return { width: Math.max(1, Math.round(scene.width * ratio)), height: Math.max(1, Math.round(scene.height * ratio)) };
}

/**
 * RGB bytes of the scene rendered at `width`×`height` (the framing of the
 * full-size image, fewer pixels). At the scene's own size it matches the
 * engine's output, give or take one level on a few pixels.
 */
export function renderScene(scene: RenderScene, width = scene.width, height = scene.height): Uint8Array {
  const pixels = new Uint8Array(width * height * 3);
  let offset = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const color = trace(scene, scene.camera, primaryRay(scene, x, y, width, height), 0);
      for (const channel of color) pixels[offset++] = Math.min(255, Math.max(0, Math.round(Math.sqrt(channel) * 255)));
    }
  }
  return pixels;
}

/** RGBA copy of RGB bytes, for `ImageData`. */
export function toRgba(rgb: Uint8Array): Uint8ClampedArray<ArrayBuffer> {
  const rgba = new Uint8ClampedArray((rgb.length / 3) * 4);
  for (let source = 0, target = 0; source < rgb.length; source += 3, target += 4) {
    rgba[target] = rgb[source]!;
    rgba[target + 1] = rgb[source + 1]!;
    rgba[target + 2] = rgb[source + 2]!;
    rgba[target + 3] = 255;
  }
  return rgba;
}

/** Index of the primitive seen at a point of the image (`u`, `v` in 0–1), if any. */
export function pickPrimitive(scene: RenderScene, u: number, v: number): number | undefined {
  const width = 1000;
  const height = Math.max(1, Math.round((width * scene.height) / scene.width));
  return nearestHit(scene, scene.camera, primaryRay(scene, u * width - 0.5, v * height - 0.5, width, height))?.primitive;
}
