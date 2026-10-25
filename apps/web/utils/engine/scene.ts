// Scene of the preview engine, built from the syntax tree for one frame
// (port of the raytracer's `engine/scene.rs`; same defaults and same order
// of shapes, so a shape index means the same object as in the engine).

import {
  all,
  block,
  entry,
  evaluate,
  items,
  keyframes,
  numbers,
  number,
  parse,
  word,
  type Entry,
} from '../sceneSyntax';
import { Bvh, quad, Transform, triangle, type Shape } from './geometry';
import { EPSILON, Vec3 } from './math';

export const ENGINE_VERSION = 2;
/** Scale of light intensities in path mode (same as the engine). */
export const LIGHT_UNIT = 1 / 12;

export type Mode = 'whitted' | 'path';
export type Tonemap = 'clamp' | 'reinhard' | 'aces';
export type MaterialKind = 'phong' | 'diffuse' | 'metal' | 'glass' | 'emissive';

export interface Settings {
  samples: number;
  mode: Mode;
  bounces: number;
  exposure: number;
  tonemap: Tonemap;
  sky: number;
  seed: number;
  frame: number;
  clamp: number;
}

export interface Material {
  kind: MaterialKind;
  color: Vec3;
  reflectivity: number;
  specular: number;
  shininess: number;
  roughness: number;
  ior: number;
  emission: Vec3;
}

export interface PointLight {
  position: Vec3;
  intensity: number;
  color: Vec3;
}
export interface Emitter {
  shape: number;
  intensity?: number;
  color: Vec3;
}

export interface Camera {
  origin: Vec3;
  forward: Vec3;
  right: Vec3;
  up: Vec3;
  tanHalfFov: number;
  aperture: number;
  focusDistance: number;
}

export interface Scene {
  width: number;
  height: number;
  camera: Camera;
  settings: Settings;
  shapes: Shape[];
  shapeMaterial: number[];
  materials: Material[];
  planes: number[];
  bvh: Bvh;
  points: PointLight[];
  emitters: Emitter[];
  /** For each shape, the index of the entry it comes from (primitives first, then lights). */
  shapeSource: number[];
}

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

function vec3(entries: Entry[] | undefined, fallback: Vec3, frame: number): Vec3 {
  if (!entries) return fallback;
  const bare = numbers(entries);
  if (bare.length === 3) return new Vec3(bare[0], bare[1], bare[2]);
  return new Vec3(
    number(entries, 'x', fallback.x, frame),
    number(entries, 'y', fallback.y, frame),
    number(entries, 'z', fallback.z, frame),
  );
}

function color(entries: Entry[], fallback: number, frame: number): Vec3 {
  const inner = block(entries, 'color');
  const source = inner ?? entries;
  const bare = inner ? numbers(inner) : [];
  if (bare.length === 3) return new Vec3(bare[0], bare[1], bare[2]).div(255);
  return new Vec3(
    number(source, 'r', number(entries, 'r', fallback, frame), frame),
    number(source, 'g', number(entries, 'g', fallback, frame), frame),
    number(source, 'b', number(entries, 'b', fallback, frame), frame),
  ).div(255);
}

function transform(entries: Entry[], frame: number): Transform {
  const found = entry(entries, 'scale');
  let scale = new Vec3(1, 1, 1);
  if (found?.value.kind === 'block' && !keyframes(found.value.entries))
    scale = vec3(found.value.entries, new Vec3(1, 1, 1), frame);
  else if (found) {
    const s = evaluate(found.value, frame) ?? 1;
    scale = new Vec3(s, s, s);
  }
  return new Transform(
    scale,
    vec3(block(entries, 'rotate'), new Vec3(), frame),
    vec3(block(entries, 'translate'), new Vec3(), frame),
  );
}

const KINDS: MaterialKind[] = ['phong', 'diffuse', 'metal', 'glass', 'emissive'];

function material(entries: Entry[], defaultReflectivity: number, frame: number): Material {
  const type = word(entries, 'type') ?? 'phong';
  if (!KINDS.includes(type as MaterialKind)) throw new Error(`unknown material type \`${type}\``);
  const kind = type as MaterialKind;
  const tint = color(entries, 200, frame);
  const diffuse = kind === 'diffuse';
  const strength = Math.max(0, number(entries, 'strength', 1, frame));
  return {
    kind,
    color: tint,
    reflectivity: diffuse
      ? 0
      : clamp(
          number(
            entries,
            'reflectivity',
            number(entries, 'reflection', defaultReflectivity, frame),
            frame,
          ),
          0,
          0.95,
        ),
    specular: diffuse ? 0 : clamp(number(entries, 'specular', 0.65, frame), 0, 2),
    shininess: clamp(number(entries, 'shininess', 72, frame), 1, 512),
    roughness: clamp(number(entries, 'roughness', 0, frame), 0, 1),
    ior: clamp(number(entries, 'ior', 1.5, frame), 1, 3),
    emission: kind === 'emissive' ? tint.hadamard(tint).mul(strength) : new Vec3(),
  };
}

const MATERIAL_KEYS = [
  'type',
  'color',
  'r',
  'g',
  'b',
  'reflection',
  'reflectivity',
  'specular',
  'shininess',
  'roughness',
  'ior',
  'strength',
];

function camera(entries: Entry[], frame: number): Camera {
  const n = (key: string, fallback: number) => number(entries, key, fallback, frame);
  const positionBlock = block(entries, 'position');
  const position = positionBlock
    ? vec3(positionBlock, new Vec3(), frame)
    : new Vec3(n('x', 0), n('y', 0), n('z', 0));
  const lookAtBlock = block(entries, 'look_at');
  const lookAt = lookAtBlock ? vec3(lookAtBlock, new Vec3(1, 0, 0), frame) : undefined;
  let upHint = vec3(block(entries, 'up'), new Vec3(0, 0, 1), frame).normalized();
  if (upHint.length() <= EPSILON) upHint = new Vec3(0, 0, 1);
  const directionBlock = block(entries, 'direction');
  let forward = (
    lookAt
      ? lookAt.sub(position)
      : directionBlock
        ? vec3(directionBlock, new Vec3(1, 0, 0), frame)
        : new Vec3(1, 0, 0)
  ).normalized();
  if (forward.length() <= EPSILON) forward = new Vec3(1, 0, 0);
  const rotation = block(entries, 'rotation');
  if (!lookAt && rotation) {
    const turn = new Transform(new Vec3(1, 1, 1), vec3(rotation, new Vec3(), frame), new Vec3());
    forward = turn.vector(forward).normalized();
    upHint = turn.vector(upHint).normalized();
  }
  if (forward.cross(upHint).length() <= 1e-9)
    upHint = Math.abs(forward.z) > 0.9 ? new Vec3(1, 0, 0) : new Vec3(0, 0, 1);
  const right = forward.cross(upHint).normalized();
  const up = right.cross(forward).normalized();
  const fov = clamp(n('fieldOfView', 55), 1, 179);
  return {
    origin: position,
    forward,
    right,
    up,
    tanHalfFov: Math.tan((fov * Math.PI) / 180 / 2),
    aperture: Math.max(0, n('aperture', 0)),
    focusDistance: Math.max(
      EPSILON,
      n('focus_distance', lookAt ? lookAt.sub(position).length() : 5),
    ),
  };
}

function settings(root: Entry[], frameOverride?: number): Settings {
  const render = block(root, 'render') ?? [];
  const engine = number(render, 'engine', ENGINE_VERSION);
  if (engine > ENGINE_VERSION)
    throw new Error(`scene_requires_engine:${engine} (this engine is ${ENGINE_VERSION})`);
  const mode = word(render, 'mode') ?? 'whitted';
  if (mode !== 'whitted' && mode !== 'path') throw new Error(`unknown render mode \`${mode}\``);
  const tonemap = word(render, 'tonemap') ?? (mode === 'path' ? 'aces' : 'clamp');
  if (!['clamp', 'reinhard', 'aces'].includes(tonemap))
    throw new Error(`unknown tonemap \`${tonemap}\``);
  const lastFrame = [...root].reverse().find((item) => item.key === 'frame');
  const frame =
    frameOverride ?? (lastFrame && evaluate(lastFrame.value, 0)) ?? number(render, 'frame', 0);
  return {
    samples: Math.trunc(clamp(number(render, 'samples', 1, frame), 1, 65536)),
    mode,
    bounces: Math.trunc(clamp(number(render, 'bounces', mode === 'path' ? 8 : 3, frame), 0, 64)),
    exposure: Math.max(0, number(render, 'exposure', 1, frame)),
    tonemap: tonemap as Tonemap,
    sky: Math.max(0, number(render, 'sky', 1, frame)),
    seed: Math.trunc(Math.max(0, number(render, 'seed', 0, frame))),
    frame,
    clamp: Math.max(0, number(render, 'clamp', 2, frame)),
  };
}

/** Builds the scene of `text` at `frame` (the scene's own frame when absent); throws an `Error`. */
export function buildScene(text: string, frameOverride?: number): Scene {
  const root = parse(text);
  const config = settings(root, frameOverride);
  const frame = config.frame;
  const cameraBlock = block(root, 'camera') ?? [];
  const resolution = block(cameraBlock, 'resolution') ?? [];
  const width = Math.trunc(Math.max(1, number(resolution, 'width', 320)));
  const height = Math.trunc(Math.max(1, number(resolution, 'height', 200)));

  const shapes: Shape[] = [];
  const shapeMaterial: number[] = [];
  const shapeSource: number[] = [];
  const materials: Material[] = [];
  const named = new Map<string, number>();
  let source = 0;
  const add = (shape: Shape, index: number) => {
    shapes.push(shape);
    shapeMaterial.push(index);
    shapeSource.push(source);
  };

  for (const item of all(block(root, 'materials') ?? [], 'material')) {
    for (const entries of items(item.value)) {
      const name = word(entries, 'name');
      if (!name) throw new Error(`line ${item.line}: material without \`name\``);
      materials.push(material(entries, 0.32, frame));
      named.set(name, materials.length - 1);
    }
  }

  const objectMaterial = (entries: Entry[], defaultReflectivity: number): number => {
    const name = word(entries, 'material');
    if (name !== undefined) {
      const base = named.get(name);
      if (base === undefined)
        throw new Error(
          `line ${entry(entries, 'material')?.line ?? 0}: unknown material \`${name}\``,
        );
      if (!MATERIAL_KEYS.some((key) => entry(entries, key))) return base;
    }
    materials.push(material(entries, defaultReflectivity, frame));
    return materials.length - 1;
  };

  for (const item of block(root, 'primitives') ?? []) {
    if (!item.key) continue;
    for (const entries of items(item.value)) {
      const t = transform(entries, frame);
      const n = (key: string, fallback: number) => number(entries, key, fallback, frame);
      switch (item.key) {
        case 'sphere': {
          const index = objectMaterial(entries, 0.32);
          add(
            {
              kind: 'sphere',
              center: t.point(new Vec3(n('x', 0), n('y', 0), n('z', 0))),
              radius: Math.max(EPSILON, n('radius', 1) * t.uniformScale()),
            },
            index,
          );
          break;
        }
        case 'plane': {
          const index = objectMaterial(entries, 0.12);
          const inner = block(entries, 'normal');
          const normal = inner
            ? vec3(inner, new Vec3(0, 0, 1), frame)
            : new Vec3(n('normal_x', 0), n('normal_y', 0), n('normal_z', 1));
          if (normal.length() <= EPSILON)
            throw new Error(`line ${item.line}: plane normal is (0, 0, 0)`);
          add(
            {
              kind: 'plane',
              point: t.point(new Vec3(n('x', 0), n('y', 0), n('z', 0))),
              normal: t.normal(normal.normalized()),
            },
            index,
          );
          break;
        }
        case 'box': {
          const index = objectMaterial(entries, 0.12);
          const low = vec3(block(entries, 'min'), new Vec3(-0.5, -0.5, -0.5), frame);
          const high = vec3(block(entries, 'max'), new Vec3(0.5, 0.5, 0.5), frame);
          const corner = (i: number) =>
            t.point(
              new Vec3(i & 1 ? high.x : low.x, i & 2 ? high.y : low.y, i & 4 ? high.z : low.z),
            );
          for (const [a, b, c] of [
            [0, 2, 1],
            [4, 5, 6],
            [0, 1, 4],
            [2, 6, 3],
            [0, 4, 2],
            [1, 3, 5],
          ] as const) {
            const origin = corner(a);
            add(quad(origin, corner(b).sub(origin), corner(c).sub(origin)), index);
          }
          break;
        }
        case 'triangle': {
          const index = objectMaterial(entries, 0.12);
          add(
            triangle(
              t.point(vec3(block(entries, 'a'), new Vec3(), frame)),
              t.point(vec3(block(entries, 'b'), new Vec3(0, 1, 0), frame)),
              t.point(vec3(block(entries, 'c'), new Vec3(0, 0, 1), frame)),
            ),
            index,
          );
          break;
        }
        case 'quad': {
          const index = objectMaterial(entries, 0.12);
          add(
            quad(
              t.point(vec3(block(entries, 'corner'), new Vec3(0, -0.5, -0.5), frame)),
              t.vector(vec3(block(entries, 'u'), new Vec3(0, 1, 0), frame)),
              t.vector(vec3(block(entries, 'v'), new Vec3(0, 0, 1), frame)),
            ),
            index,
          );
          break;
        }
        case 'mesh': {
          const index = objectMaterial(entries, 0.12);
          const vertices = numbers(block(entries, 'vertices') ?? []);
          const faces = numbers(block(entries, 'faces') ?? []);
          if (vertices.length % 3 || faces.length % 3)
            throw new Error(
              `line ${item.line}: mesh vertices and faces must be groups of 3 numbers`,
            );
          const points: Vec3[] = [];
          for (let i = 0; i < vertices.length; i += 3)
            points.push(t.point(new Vec3(vertices[i], vertices[i + 1], vertices[i + 2])));
          const at = (value: number) => {
            if (value < 0 || !Number.isInteger(value) || value >= points.length)
              throw new Error(
                `line ${item.line}: mesh face uses vertex ${value}, the mesh has ${points.length}`,
              );
            return points[value]!;
          };
          for (let i = 0; i < faces.length; i += 3)
            add(triangle(at(faces[i]!), at(faces[i + 1]!), at(faces[i + 2]!)), index);
          break;
        }
        default:
          continue;
      }
      source += 1;
    }
  }

  const points: PointLight[] = [];
  const emitters: Emitter[] = [];
  for (const item of block(root, 'lights') ?? []) {
    for (const entries of items(item.value)) {
      if (!item.key) continue;
      const n = (key: string, fallback: number) => number(entries, key, fallback, frame);
      const position = new Vec3(n('x', 4), n('y', 0), n('z', 5));
      const intensity = Math.max(0, n('intensity', 450));
      const tint = color(entries, 255, frame);
      if (item.key === 'point') {
        points.push({ position, intensity, color: tint });
        source += 1;
      } else if (item.key === 'area') {
        const radius = Math.max(EPSILON, n('radius', 0.5));
        materials.push({
          kind: 'emissive',
          color: tint,
          reflectivity: 0,
          specular: 0,
          shininess: 1,
          roughness: 0,
          ior: 1,
          emission: tint.mul((intensity * LIGHT_UNIT) / (radius * radius)),
        });
        add({ kind: 'sphere', center: position, radius }, materials.length - 1);
        emitters.push({ shape: shapes.length - 1, intensity, color: tint });
        source += 1;
      }
    }
  }
  shapes.forEach((shape, index) => {
    const own = materials[shapeMaterial[index]!]!;
    if (
      own.kind === 'emissive' &&
      shape.kind !== 'plane' &&
      !emitters.some((e) => e.shape === index)
    ) {
      emitters.push({ shape: index, color: own.emission });
    }
  });
  if (
    config.mode === 'whitted' &&
    !points.length &&
    emitters.every((e) => e.intensity === undefined)
  ) {
    points.push({ position: new Vec3(4, 0, 5), intensity: 450, color: new Vec3(1, 1, 1) });
  }
  const planes = shapes.flatMap((shape, index) => (shape.kind === 'plane' ? [index] : []));
  const finite = shapes.flatMap((shape, index) => (shape.kind === 'plane' ? [] : [index]));
  return {
    width,
    height,
    camera: camera(cameraBlock, frame),
    settings: config,
    shapes,
    shapeMaterial,
    materials,
    planes,
    bvh: new Bvh(shapes, finite),
    points,
    emitters,
    shapeSource,
  };
}
