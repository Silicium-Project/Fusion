// Colour of a pixel in the preview engine (port of the raytracer's
// `engine/integrator.rs`: Whitted and path tracing, tone mapping, gamma).

import { area, intersect, type Shape } from './geometry';
import { EPSILON, Rng, Vec3 } from './math';
import { LIGHT_UNIT, type Material, type Scene, type Tonemap } from './scene';

interface Hit { distance: number; point: Vec3; normal: Vec3; frontFace: boolean; shape: number }

const ONE = new Vec3(1, 1, 1);
const ZERO = new Vec3();
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

function nearest(scene: Scene, origin: Vec3, direction: Vec3, limit: number): Hit | undefined {
  let best = scene.bvh.intersect(origin, direction, limit);
  for (const plane of scene.planes) {
    const hit = intersect(scene.shapes[plane]!, origin, direction);
    if (hit && hit[0] < (best ? best[0] : limit)) best = [hit[0], hit[1], plane];
  }
  if (!best) return undefined;
  const [distance, outward, shape] = best;
  const frontFace = outward.dot(direction) < 0;
  return { distance, point: origin.add(direction.mul(distance)), normal: frontFace ? outward : outward.neg(), frontFace, shape };
}

/** Index of the shape seen through a camera ray, if any. */
export function firstShape(scene: Scene, origin: Vec3, direction: Vec3): number | undefined {
  return nearest(scene, origin, direction, Infinity)?.shape;
}

const materialOf = (scene: Scene, hit: Hit): Material => scene.materials[scene.shapeMaterial[hit.shape]!]!;

function transmittance(scene: Scene, origin: Vec3, direction: Vec3, distance: number, light?: number): Vec3 {
  let through = ONE;
  for (let i = 0; i < 8; i += 1) {
    const hit = nearest(scene, origin, direction, distance - EPSILON);
    if (!hit || hit.shape === light) return through;
    const material = materialOf(scene, hit);
    if (material.kind !== 'glass') return ZERO;
    through = through.hadamard(material.color).mul(0.92);
    origin = hit.point.add(direction.mul(EPSILON * 4));
    distance -= hit.distance;
  }
  return ZERO;
}

function background(scene: Scene, direction: Vec3): Vec3 {
  const amount = (direction.z + 1) * 0.5;
  return new Vec3(0.04, 0.07, 0.13).mul(1 - amount).add(new Vec3(0.34, 0.55, 0.9).mul(amount)).mul(scene.settings.sky);
}

function refract(direction: Vec3, normal: Vec3, eta: number): Vec3 | undefined {
  const cosI = Math.min(1, direction.neg().dot(normal));
  const k = 1 - eta * eta * (1 - cosI * cosI);
  return k >= 0 ? direction.mul(eta).add(normal.mul(eta * cosI - Math.sqrt(k))).normalized() : undefined;
}

function fresnel(cosI: number, eta: number): number {
  const ratio = (1 - eta) / (1 + eta);
  const r0 = ratio * ratio;
  const m = 1 - cosI;
  return r0 + (1 - r0) * m * m * m * m * m;
}

const glossy = (reflected: Vec3, roughness: number, rng: Rng) => (roughness <= 0 ? reflected : reflected.add(rng.inSphere().mul(roughness)).normalized());

type LightSample = [Vec3, number, number, Vec3, number | undefined];

function whittedLights(scene: Scene, point: Vec3, rng: Rng): LightSample[] {
  const lights: LightSample[] = scene.points.map((light) => {
    const displacement = light.position.sub(point);
    return [displacement, displacement.dot(displacement), light.intensity, light.color, undefined];
  });
  for (const emitter of scene.emitters) {
    const shape = scene.shapes[emitter.shape]!;
    if (emitter.intensity === undefined || shape.kind !== 'sphere') continue;
    let offset = rng.onSphere();
    if (offset.dot(point.sub(shape.center)) < 0) offset = offset.neg();
    const toCentre = shape.center.sub(point);
    lights.push([shape.center.add(offset.mul(shape.radius)).sub(point), toCentre.dot(toCentre), emitter.intensity, emitter.color, emitter.shape]);
  }
  return lights;
}

function phongLight(scene: Scene, hit: Hit, view: Vec3, shininess: number, specular: number, rng: Rng): [Vec3, Vec3] {
  let diffuse = new Vec3(0.09, 0.09, 0.11);
  let highlight = ZERO;
  for (const [displacement, centreSquared, intensity, tint, shape] of whittedLights(scene, hit.point, rng)) {
    const length = displacement.length();
    const direction = displacement.div(Math.max(length, EPSILON));
    const through = transmittance(scene, hit.point.add(hit.normal.mul(EPSILON * 4)), direction, length, shape);
    if (through.maxComponent() <= 0) continue;
    const attenuation = Math.min(1.5, intensity / Math.max(1, centreSquared));
    const lambert = Math.max(0, hit.normal.dot(direction));
    const lit = tint.hadamard(through);
    diffuse = diffuse.add(lit.mul(lambert * attenuation));
    const reflected = direction.neg().reflect(hit.normal).normalized();
    highlight = highlight.add(lit.mul(Math.max(0, reflected.dot(view)) ** shininess * specular * attenuation));
  }
  return [diffuse, highlight];
}

function whitted(scene: Scene, origin: Vec3, direction: Vec3, depth: number, rng: Rng): Vec3 {
  const hit = nearest(scene, origin, direction, Infinity);
  if (!hit) return background(scene, direction);
  const material = materialOf(scene, hit);
  const view = direction.neg();
  const outside = hit.point.add(hit.normal.mul(EPSILON * 4));
  const inside = hit.point.sub(hit.normal.mul(EPSILON * 4));
  const deeper = depth < scene.settings.bounces;
  switch (material.kind) {
    case 'emissive':
      return material.emission.clamp();
    case 'glass': {
      const eta = hit.frontFace ? 1 / material.ior : material.ior;
      const cosI = clamp(view.dot(hit.normal), 0, 1);
      const refracted = refract(direction, hit.normal, eta);
      const reflectance = refracted ? fresnel(cosI, eta) : 1;
      const [, highlight] = phongLight(scene, hit, view, 256, 1, rng);
      if (!deeper) return background(scene, direction).hadamard(material.color).add(highlight).clamp();
      const reflected = whitted(scene, outside, direction.reflect(hit.normal).normalized(), depth + 1, rng);
      const transmitted = refracted ? whitted(scene, inside, refracted, depth + 1, rng) : ZERO;
      return reflected.mul(reflectance).add(transmitted.hadamard(material.color).mul(1 - reflectance)).add(highlight).clamp();
    }
    case 'metal': {
      const shininess = 2 / Math.max(1e-4, material.roughness * material.roughness);
      const [, highlight] = phongLight(scene, hit, view, Math.min(512, shininess), 1, rng);
      let bounce = glossy(direction.reflect(hit.normal).normalized(), material.roughness, rng);
      if (bounce.dot(hit.normal) <= 0) bounce = direction.reflect(hit.normal).normalized();
      const reflected = deeper ? whitted(scene, outside, bounce, depth + 1, rng) : background(scene, bounce);
      return reflected.hadamard(material.color).add(highlight.hadamard(material.color)).clamp();
    }
    default: {
      const [diffuse, highlight] = phongLight(scene, hit, view, material.shininess, material.specular, rng);
      const local = material.color.hadamard(diffuse).add(highlight);
      if (!deeper || material.reflectivity <= 0) return local.clamp();
      const bounce = glossy(direction.reflect(hit.normal).normalized(), material.roughness, rng);
      const reflected = whitted(scene, outside, bounce, depth + 1, rng);
      return local.mul(1 - material.reflectivity).add(reflected.mul(material.reflectivity)).clamp();
    }
  }
}

function towards(point: Vec3, target: Vec3, lightNormal: Vec3): [Vec3, number, number] {
  const displacement = target.sub(point);
  const distance = Math.max(1e-9, displacement.length());
  const direction = displacement.div(distance);
  return [direction, distance, Math.abs(lightNormal.dot(direction))];
}

function directLight(scene: Scene, point: Vec3, normal: Vec3, rng: Rng): Vec3 {
  const origin = point.add(normal.mul(EPSILON * 4));
  let irradiance = ZERO;
  for (const light of scene.points) {
    const displacement = light.position.sub(point);
    const distanceSquared = Math.max(1e-6, displacement.dot(displacement));
    const distance = Math.sqrt(distanceSquared);
    const direction = displacement.div(distance);
    const cosine = normal.dot(direction);
    if (cosine <= 0) continue;
    const through = transmittance(scene, origin, direction, distance);
    irradiance = irradiance.add(light.color.hadamard(through).mul((Math.PI * light.intensity * LIGHT_UNIT * cosine) / distanceSquared));
  }
  for (const emitter of scene.emitters) {
    const shape: Shape = scene.shapes[emitter.shape]!;
    const radiance = scene.materials[scene.shapeMaterial[emitter.shape]!]!.emission;
    let sample: [Vec3, number, number] | undefined;
    if (shape.kind === 'sphere') {
      const axis = shape.center.sub(point);
      const distanceSquared = axis.dot(axis);
      if (distanceSquared <= shape.radius * shape.radius) continue;
      const cosMax = Math.sqrt(Math.max(0, 1 - (shape.radius * shape.radius) / distanceSquared));
      const direction = rng.inCone(axis.normalized(), cosMax);
      const hit = intersect(shape, origin, direction);
      if (!hit) continue;
      sample = [direction, hit[0], 2 * Math.PI * (1 - cosMax)];
    } else if (shape.kind === 'quad' || shape.kind === 'triangle') {
      let target: Vec3;
      if (shape.kind === 'quad') {
        target = shape.corner.add(shape.u.mul(rng.uniform())).add(shape.v.mul(rng.uniform()));
      } else {
        let s = rng.uniform();
        let t = rng.uniform();
        if (s + t > 1) { s = 1 - s; t = 1 - t; }
        target = shape.a.add(shape.edge1.mul(s)).add(shape.edge2.mul(t));
      }
      const [direction, distance, cosLight] = towards(point, target, shape.normal);
      if (cosLight <= 1e-9) continue;
      sample = [direction, distance, (area(shape) * cosLight) / (distance * distance)];
    }
    if (!sample) continue;
    const [direction, distance, inversePdf] = sample;
    const cosine = normal.dot(direction);
    if (cosine <= 0) continue;
    const through = transmittance(scene, origin, direction, distance, emitter.shape);
    irradiance = irradiance.add(radiance.hadamard(through).mul(cosine * inversePdf));
  }
  return irradiance;
}

const linear = (c: Vec3) => c.hadamard(c);

function path(scene: Scene, origin: Vec3, direction: Vec3, rng: Rng): Vec3 {
  let throughput = ONE;
  let radiance = ZERO;
  let countEmission = true;
  let afterRough = false;
  const cap = scene.settings.clamp;
  for (let depth = 0; depth <= scene.settings.bounces; depth += 1) {
    const hit = nearest(scene, origin, direction, Infinity);
    if (!hit) { radiance = radiance.add(throughput.hadamard(background(scene, direction))); break; }
    const material = materialOf(scene, hit);
    if (material.kind === 'emissive') {
      if (countEmission) {
        let added = throughput.hadamard(material.emission);
        if (afterRough) added = new Vec3(Math.min(added.x, cap), Math.min(added.y, cap), Math.min(added.z, cap));
        radiance = radiance.add(added);
      }
      break;
    }
    if (depth === scene.settings.bounces) break;
    const outside = hit.point.add(hit.normal.mul(EPSILON * 4));
    const reflected = direction.reflect(hit.normal).normalized();
    let next: [Vec3, Vec3];
    if (material.kind === 'phong' || material.kind === 'diffuse') {
      const coat = material.kind === 'phong' ? clamp(material.reflectivity + 0.04 * material.specular, 0, 0.95) : 0;
      if (rng.uniform() < coat) {
        const roughness = Math.sqrt(2 / (material.shininess + 2)) * 0.5 + material.roughness;
        const bounce = glossy(reflected, Math.min(1, roughness), rng);
        if (bounce.dot(hit.normal) <= 0) break;
        countEmission = true;
        afterRough = true;
        next = [outside, bounce];
      } else {
        const albedo = linear(material.color);
        const light = directLight(scene, hit.point, hit.normal, rng);
        radiance = radiance.add(throughput.hadamard(albedo).hadamard(light).div(Math.PI));
        throughput = throughput.hadamard(albedo);
        countEmission = false;
        afterRough = true;
        next = [outside, rng.cosineHemisphere(hit.normal)];
      }
    } else if (material.kind === 'metal') {
      const bounce = glossy(reflected, material.roughness, rng);
      if (bounce.dot(hit.normal) <= 0) break;
      throughput = throughput.hadamard(linear(material.color));
      countEmission = true;
      afterRough ||= material.roughness > 0.05;
      next = [outside, bounce];
    } else {
      const eta = hit.frontFace ? 1 / material.ior : material.ior;
      const cosI = clamp(direction.neg().dot(hit.normal), 0, 1);
      throughput = throughput.hadamard(material.color);
      countEmission = true;
      const through = refract(direction, hit.normal, eta);
      next = through && rng.uniform() >= fresnel(cosI, eta) ? [hit.point.sub(hit.normal.mul(EPSILON * 4)), through] : [outside, reflected];
    }
    if (depth >= 3) {
      const survival = clamp(throughput.maxComponent(), 0.05, 1);
      if (rng.uniform() > survival) break;
      throughput = throughput.div(survival);
    }
    [origin, direction] = next;
  }
  return radiance;
}

function tonemap(value: number, curve: Tonemap): number {
  const mapped = curve === 'reinhard' ? value / (1 + value) : curve === 'aces' ? (value * (2.51 * value + 0.03)) / (value * (2.43 * value + 0.59) + 0.14) : value;
  return clamp(mapped, 0, 1);
}

/** Camera ray through point (`px`, `py`) of the image, in pixels of a `width` × `height` image. */
export function cameraRay(scene: Scene, px: number, py: number, width: number, height: number): [Vec3, Vec3] {
  const camera = scene.camera;
  const aspect = width / height;
  const sx = (2 * px / width - 1) * aspect * camera.tanHalfFov;
  const sy = (1 - 2 * py / height) * camera.tanHalfFov;
  return [camera.origin, camera.forward.add(camera.right.mul(sx)).add(camera.up.mul(sy)).normalized()];
}

/**
 * Linear colour (before exposure and tone mapping) of one sample of pixel
 * (`x`, `y`) of a `width` × `height` image. `sample` < `samples`.
 */
export function sampleColor(scene: Scene, x: number, y: number, width: number, height: number, sample: number, samples: number): Vec3 {
  const settings = scene.settings;
  const rng = Rng.forSample(x, y, sample, Math.round(settings.frame), settings.seed);
  const grid = Math.floor(Math.sqrt(samples));
  let dx = 0.5;
  let dy = 0.5;
  if (samples > 1) {
    if (sample < grid * grid) {
      dx = ((sample % grid) + rng.uniform()) / grid;
      dy = (Math.floor(sample / grid) + rng.uniform()) / grid;
    } else {
      dx = rng.uniform();
      dy = rng.uniform();
    }
  }
  let [origin, direction] = cameraRay(scene, x + dx, y + dy, width, height);
  const camera = scene.camera;
  if (camera.aperture > 0) {
    const focus = origin.add(direction.mul(camera.focusDistance / direction.dot(camera.forward)));
    const [u, v] = rng.inDisk();
    origin = origin.add(camera.right.mul(u * camera.aperture)).add(camera.up.mul(v * camera.aperture));
    direction = focus.sub(origin).normalized();
  }
  const color = settings.mode === 'path' ? path(scene, origin, direction, rng) : whitted(scene, origin, direction, 0, rng);
  return Number.isFinite(color.x) && Number.isFinite(color.y) && Number.isFinite(color.z) ? color : ZERO;
}

/** Screen byte of a mean linear channel (exposure, tone mapping, gamma). */
export function toByte(scene: Scene, mean: number): number {
  const value = tonemap(Math.max(0, mean * scene.settings.exposure), scene.settings.tonemap);
  return clamp(Math.round(Math.sqrt(value) * 255), 0, 255);
}
