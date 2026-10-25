// Raytracer scenes on the site: the model edited by the scene editor, the
// `.cfg` text it writes, and reading a `.cfg` back (`./sceneSyntax`, the
// engine's syntax). The preview renders the written text with the port of
// the engine (`./engine`).
//
// Coordinates are the engine's: by default the camera looks along +x, +z is
// up and +y is on the LEFT of the image (the editor shows `-y` as "left ↔ right").

import { Transform } from './engine/geometry';
import { Vec3 } from './engine/math';
import * as syntax from './sceneSyntax';

export type Rgb = [number, number, number];
export type Xyz = [number, number, number];

export const MATERIAL_TYPES = ['phong', 'diffuse', 'metal', 'glass', 'emissive'] as const;
export type MaterialType = (typeof MATERIAL_TYPES)[number];

export interface SceneMaterial {
  /** How the surface treats light (see the engine's README). */
  type: MaterialType;
  /** 0–255 per channel. */
  color: Rgb;
  /** Share of reflected light, 0–0.95 (phong). */
  reflection: number;
  /** Strength of the highlight, 0–2 (phong). */
  specular: number;
  /** Size of the highlight, 1 (wide) – 512 (pin-point) (phong). */
  shininess: number;
  /** Blur of reflections, 0 (sharp) – 1 (phong, metal). */
  roughness: number;
  /** Index of refraction, 1–3 (glass: 1.33 water, 1.5 glass, 2.4 diamond). */
  ior: number;
  /** Light given off (emissive). */
  strength: number;
}

interface Placed {
  id: number;
  x: number;
  y: number;
  z: number;
  material: SceneMaterial;
}
export interface SceneSphere extends Placed {
  kind: 'sphere';
  radius: number;
}
export interface ScenePlane extends Placed {
  kind: 'plane';
  normal: Xyz;
}
/** A box centred on (x, y, z). */
export interface SceneBox extends Placed {
  kind: 'box';
  size: Xyz;
  rotation: Xyz;
}
/** A flat rectangle centred on (x, y, z), facing the camera before rotation. */
export interface ScenePanel extends Placed {
  kind: 'panel';
  width: number;
  height: number;
  rotation: Xyz;
}
/** A triangle model; its points are scaled by `size`, turned by `rotation`, then moved to (x, y, z). */
export interface SceneMesh extends Placed {
  kind: 'mesh';
  vertices: number[];
  faces: number[];
  size: number;
  rotation: Xyz;
}
export type SceneObject = SceneSphere | ScenePlane | SceneBox | ScenePanel | SceneMesh;
export type ObjectKind = SceneObject['kind'];

export interface SceneLight {
  id: number;
  /** `point`: a dot of light (sharp shadows); `area`: a glowing ball (soft shadows). */
  kind: 'point' | 'area';
  x: number;
  y: number;
  z: number;
  intensity: number;
  color: Rgb;
  /** Size of an `area` light. */
  radius: number;
}

export interface SceneCamera {
  x: number;
  y: number;
  z: number;
  /** Turn to the right, in degrees. */
  yaw: number;
  /** Look up, in degrees. */
  pitch: number;
  /** Lens opening: 0 = everything sharp; more = blur away from `focus`. */
  aperture: number;
  /** Distance of the sharp plane (with `aperture`). */
  focus: number;
}

export interface SceneModel {
  width: number;
  height: number;
  /** Vertical field of view, 1–179 degrees. */
  fov: number;
  camera: SceneCamera;
  objects: SceneObject[];
  lights: SceneLight[];
  /** Quality of the final render (absent = `draft`). */
  quality?: RenderQuality;
  /** Brightness of the sky (0 = black background, no light from the sky). */
  sky?: number;
  /** Overall brightness of the image. */
  exposure?: number;
}

export type RenderQuality = 'draft' | 'smooth' | 'photo';

/** Engine settings of each quality (`render` block). */
export const RENDER_QUALITIES: Record<
  RenderQuality,
  { samples: number; mode: 'whitted' | 'path'; bounces?: number }
> = {
  draft: { samples: 1, mode: 'whitted' },
  smooth: { samples: 16, mode: 'whitted' },
  photo: { samples: 256, mode: 'path', bounces: 6 },
};

/** Rays traced for the final render (a rough cost: path tracing bounces more). */
export function renderCost(scene: Pick<SceneModel, 'width' | 'height' | 'quality'>): number {
  const quality = RENDER_QUALITIES[scene.quality || 'draft'];
  return scene.width * scene.height * quality.samples * (quality.mode === 'path' ? 4 : 1);
}

/** Ready-made materials: the type and the settings that define the look. */
export const MATERIAL_PRESETS = {
  matte: { type: 'diffuse' },
  glossy: { type: 'phong', reflection: 0.25, specular: 0.8, shininess: 96, roughness: 0 },
  satin: { type: 'phong', reflection: 0.3, specular: 0.5, shininess: 40, roughness: 0.2 },
  mirror: { type: 'metal', roughness: 0 },
  metal: { type: 'metal', roughness: 0.3 },
  glass: { type: 'glass', ior: 1.5 },
  diamond: { type: 'glass', ior: 2.4 },
  light: { type: 'emissive', strength: 4 },
} as const satisfies Record<string, Partial<SceneMaterial>>;
export type MaterialPreset = keyof typeof MATERIAL_PRESETS;

const BASE_MATERIAL: Omit<SceneMaterial, 'color'> = {
  type: 'phong',
  reflection: 0.25,
  specular: 0.8,
  shininess: 96,
  roughness: 0,
  ior: 1.5,
  strength: 4,
};

/** A material: a preset (or `phong` settings) in a colour. */
export function look(
  color: Rgb,
  preset: MaterialPreset | Partial<Omit<SceneMaterial, 'color'>> = 'glossy',
  patch: Partial<SceneMaterial> = {},
): SceneMaterial {
  const settings = typeof preset === 'string' ? MATERIAL_PRESETS[preset] : preset;
  return { ...BASE_MATERIAL, ...settings, ...patch, color: [...(patch.color || color)] as Rgb };
}

/** The preset a material matches, or `custom`. */
export function materialPreset(material: SceneMaterial): MaterialPreset | 'custom' {
  const found = (Object.keys(MATERIAL_PRESETS) as MaterialPreset[]).find((name) =>
    Object.entries(MATERIAL_PRESETS[name]).every(
      ([key, value]) => material[key as keyof SceneMaterial] === value,
    ),
  );
  return found || 'custom';
}

/** Image sizes offered by the editor. */
export const RESOLUTION_PRESETS = [
  { id: 'draft', width: 320, height: 200 },
  { id: 'hd', width: 1280, height: 720 },
  { id: 'fullHd', width: 1920, height: 1080 },
  { id: 'uhd', width: 3840, height: 2160 },
  { id: 'square', width: 1080, height: 1080 },
] as const;

/** Plane orientations offered by the editor (normal vectors). */
export const PLANE_ORIENTATIONS = {
  floor: [0, 0, 1],
  ceiling: [0, 0, -1],
  back: [-1, 0, 0],
  left: [0, -1, 0],
  right: [0, 1, 0],
} as const satisfies Record<string, Xyz>;
export type PlaneOrientation = keyof typeof PLANE_ORIENTATIONS;

export function planeOrientation(plane: ScenePlane): PlaneOrientation | 'custom' {
  const found = (Object.keys(PLANE_ORIENTATIONS) as PlaneOrientation[]).find((name) =>
    PLANE_ORIENTATIONS[name].every((value, index) => value === plane.normal[index]),
  );
  return found || 'custom';
}

let nextId = 1;
/** A fresh id for a new object or light. */
export const newId = (): number => nextId++;

type New<T> = Partial<Omit<T, 'id' | 'kind'>>;

export const newSphere = (patch: New<SceneSphere> = {}): SceneSphere => ({
  id: newId(),
  kind: 'sphere',
  x: 5,
  y: 0,
  z: 0,
  radius: 0.8,
  material: look([70, 160, 255]),
  ...patch,
});

export const newPlane = (patch: New<ScenePlane> = {}): ScenePlane => ({
  id: newId(),
  kind: 'plane',
  x: 0,
  y: 0,
  z: -1,
  normal: [0, 0, 1],
  material: look([225, 232, 240], { reflection: 0.15, specular: 0.4, shininess: 48 }),
  ...patch,
});

export const newBox = (patch: New<SceneBox> = {}): SceneBox => ({
  id: newId(),
  kind: 'box',
  x: 5,
  y: 0,
  z: -0.5,
  size: [1, 1, 1],
  rotation: [0, 0, 20],
  material: look([255, 200, 70], 'satin'),
  ...patch,
});

export const newPanel = (patch: New<ScenePanel> = {}): ScenePanel => ({
  id: newId(),
  kind: 'panel',
  x: 8,
  y: 0,
  z: 1,
  width: 3,
  height: 2,
  rotation: [0, 0, 0],
  material: look([255, 244, 230], 'light'),
  ...patch,
});

export const newMesh = (patch: New<SceneMesh> = {}): SceneMesh => ({
  id: newId(),
  kind: 'mesh',
  x: 5,
  y: 0,
  z: -1,
  vertices: [],
  faces: [],
  size: 1.5,
  rotation: [0, 0, 0],
  material: look([200, 120, 255], 'glossy'),
  ...patch,
});

export const newLight = (patch: Partial<Omit<SceneLight, 'id'>> = {}): SceneLight => ({
  id: newId(),
  kind: 'point',
  x: 3,
  y: 0,
  z: 5,
  intensity: 400,
  color: [255, 255, 255],
  radius: 0.5,
  ...patch,
});

export const newCamera = (patch: Partial<SceneCamera> = {}): SceneCamera => ({
  x: 0,
  y: 0,
  z: 0,
  yaw: 0,
  pitch: 0,
  aperture: 0,
  focus: 5,
  ...patch,
});

/** Deep copy (the editor never shares arrays between scenes). */
export const cloneScene = (scene: SceneModel): SceneModel =>
  JSON.parse(JSON.stringify(scene)) as SceneModel;

// ---------------------------------------------------------------- writing

/** A number as the `.cfg` writes it: at most 3 decimals, no `-0`. */
export function formatNumber(value: number, decimals = 3): string {
  const rounded = Number((Number.isFinite(value) ? value : 0).toFixed(decimals));
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

const clampNumber = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
const point = (item: { x: number; y: number; z: number }) =>
  `x = ${formatNumber(item.x)} y = ${formatNumber(item.y)} z = ${formatNumber(item.z)}`;
const vector = (name: string, value: Xyz) =>
  `${name} = { x = ${formatNumber(value[0])} y = ${formatNumber(value[1])} z = ${formatNumber(value[2])} }`;
const turned = (rotation: Xyz) => rotation.some((angle) => formatNumber(angle) !== '0');
const channel = (value: number) => Math.round(clampNumber(value, 0, 255));
const color = (rgb: Rgb) =>
  `color = { r = ${channel(rgb[0])} g = ${channel(rgb[1])} b = ${channel(rgb[2])} }`;

/** The material keys of an object. */
function material(value: SceneMaterial): string {
  switch (value.type) {
    case 'diffuse':
      return `type = diffuse ${color(value.color)}`;
    case 'metal':
      return `type = metal roughness = ${formatNumber(clampNumber(value.roughness, 0, 1))} ${color(value.color)}`;
    case 'glass':
      return `type = glass ior = ${formatNumber(clampNumber(value.ior, 1, 3))} ${color(value.color)}`;
    case 'emissive':
      return `type = emissive strength = ${formatNumber(Math.max(0, value.strength))} ${color(value.color)}`;
    default: {
      const rough =
        value.roughness > 0
          ? ` roughness = ${formatNumber(clampNumber(value.roughness, 0, 1))}`
          : '';
      return `type = phong reflection = ${formatNumber(clampNumber(value.reflection, 0, 0.95))} specular = ${formatNumber(clampNumber(value.specular, 0, 2))} shininess = ${formatNumber(clampNumber(value.shininess, 1, 512), 1)}${rough} ${color(value.color)}`;
    }
  }
}

function primitive(item: SceneObject): string {
  const rotate = (rotation: Xyz) => (turned(rotation) ? `${vector('rotate', rotation)} ` : '');
  const translate = vector('translate', [item.x, item.y, item.z]);
  switch (item.kind) {
    case 'sphere':
      return `\tsphere = { ${point(item)} radius = ${formatNumber(Math.max(0.001, item.radius))} ${material(item.material)} }`;
    case 'plane':
      return `\tplane = { ${point(item)} normal_x = ${formatNumber(item.normal[0])} normal_y = ${formatNumber(item.normal[1])} normal_z = ${formatNumber(item.normal[2])} ${material(item.material)} }`;
    case 'box':
      return `\tbox = { ${translate} ${vector('scale', item.size.map((side) => Math.max(0.001, Math.abs(side))) as Xyz)} ${rotate(item.rotation)}${material(item.material)} }`;
    case 'panel':
      return `\tquad = { ${translate} scale = { x = 1 y = ${formatNumber(Math.max(0.001, item.width))} z = ${formatNumber(Math.max(0.001, item.height))} } ${rotate(item.rotation)}${material(item.material)} }`;
    case 'mesh': {
      const lines = [
        `\tmesh = { ${translate} scale = ${formatNumber(Math.max(0.001, item.size))} ${rotate(item.rotation)}${material(item.material)}`,
        '\t\tvertices = {',
      ];
      for (let i = 0; i + 2 < item.vertices.length; i += 3)
        lines.push(
          `\t\t\t${formatNumber(item.vertices[i]!, 5)} ${formatNumber(item.vertices[i + 1]!, 5)} ${formatNumber(item.vertices[i + 2]!, 5)}`,
        );
      lines.push('\t\t}', '\t\tfaces = {');
      for (let i = 0; i + 2 < item.faces.length; i += 3)
        lines.push(`\t\t\t${item.faces[i]} ${item.faces[i + 1]} ${item.faces[i + 2]}`);
      lines.push('\t\t}', '\t}');
      return lines.join('\n');
    }
  }
}

function light(item: SceneLight): string {
  const tint = `r = ${channel(item.color[0])} g = ${channel(item.color[1])} b = ${channel(item.color[2])}`;
  const intensity = `intensity = ${formatNumber(Math.max(0, item.intensity), 1)}`;
  return item.kind === 'area'
    ? `\tarea = { ${point(item)} radius = ${formatNumber(Math.max(0.01, item.radius))} ${intensity} ${tint} }`
    : `\tpoint = { ${point(item)} ${intensity} ${tint} }`;
}

/** The `.cfg` file of a scene (comments stay outside the blocks). */
export function sceneToCfg(scene: SceneModel, title = ''): string {
  const width = Math.round(clampNumber(scene.width, 1, 16384));
  const height = Math.round(clampNumber(scene.height, 1, 16384));
  const name = title.replace(/[\r\n]+/g, ' ').trim();
  const quality = scene.quality || 'draft';
  const settings = RENDER_QUALITIES[quality];
  const sky = scene.sky ?? 1;
  const exposure = scene.exposure ?? 1;
  const camera = scene.camera;
  const render = quality !== 'draft' || sky !== 1 || exposure !== 1;
  const lines = [
    `# ${name || 'Silicium scene'}`,
    '# Written by the Silicium scene editor.',
    '',
    ...(render
      ? [
          'render :',
          '{',
          '\tengine = 2',
          `\tmode = ${settings.mode}`,
          `\tsamples = ${settings.samples}`,
          ...(settings.bounces ? [`\tbounces = ${settings.bounces}`] : []),
          ...(sky !== 1 ? [`\tsky = ${formatNumber(Math.max(0, sky))}`] : []),
          ...(exposure !== 1 ? [`\texposure = ${formatNumber(Math.max(0, exposure))}`] : []),
          '};',
          '',
        ]
      : []),
    'camera :',
    '{',
    `\tresolution = { width = ${width} height = ${height} }`,
    `\tposition = { ${point(camera)} }`,
    '\tdirection = { x = 1 y = 0 z = 0 }',
    // Rz·Ry around the camera: z turns left, y looks down.
    ...(formatNumber(camera.yaw) !== '0' || formatNumber(camera.pitch) !== '0'
      ? [
          `\trotation = { x = 0 y = ${formatNumber(-camera.pitch)} z = ${formatNumber(-camera.yaw)} }`,
        ]
      : []),
    `\tfieldOfView = ${formatNumber(clampNumber(scene.fov, 1, 179), 1)}`,
    ...(camera.aperture > 0
      ? [
          `\taperture = ${formatNumber(camera.aperture)}`,
          `\tfocus_distance = ${formatNumber(Math.max(0.01, camera.focus))}`,
        ]
      : []),
    '};',
    '',
    'primitives :',
    '{',
    ...scene.objects.map(primitive),
    '};',
    '',
    'lights :',
    '{',
    ...scene.lights.map(light),
    '};',
    '',
  ];
  return lines.join('\n');
}

// ---------------------------------------------------------------- reading

const round = (value: number, decimals = 3) => Number(value.toFixed(decimals));
const xyz = (value: Vec3, decimals = 3): Xyz => [
  round(value.x, decimals),
  round(value.y, decimals),
  round(value.z, decimals),
];

/** Rays per pixel and lighting mode of a scene (its `render` block). */
export function renderSettings(text: string): { samples: number; mode: 'whitted' | 'path' } {
  try {
    const render = syntax.block(syntax.parse(text), 'render') || [];
    return {
      samples: Math.max(1, Math.floor(syntax.number(render, 'samples', 1))),
      mode: syntax.word(render, 'mode') === 'path' ? 'path' : 'whitted',
    };
  } catch {
    return { samples: 1, mode: 'whitted' };
  }
}

/** Material keys that can be written on an object itself. */
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

function namedMaterials(root: syntax.Entry[]): Map<string, syntax.Entry[]> {
  const named = new Map<string, syntax.Entry[]>();
  for (const item of syntax.all(syntax.block(root, 'materials') || [], 'material')) {
    for (const part of syntax.items(item.value)) named.set(syntax.word(part, 'name') || '', part);
  }
  return named;
}

/** The keys describing an object's material: its own, else its named material's (as the engine does). */
function materialSource(part: syntax.Entry[], named: Map<string, syntax.Entry[]>): syntax.Entry[] {
  const own = MATERIAL_KEYS.some((key) => syntax.entry(part, key));
  const name = syntax.word(part, 'material');
  return !own && name !== undefined ? named.get(name) || part : part;
}

function vec3(entries: syntax.Entry[] | undefined, fallback: Vec3): Vec3 {
  if (!entries) return fallback;
  const bare = syntax.numbers(entries);
  if (bare.length === 3) return new Vec3(bare[0], bare[1], bare[2]);
  return new Vec3(
    syntax.number(entries, 'x', fallback.x),
    syntax.number(entries, 'y', fallback.y),
    syntax.number(entries, 'z', fallback.z),
  );
}

/** Scale (a number or x/y/z), rotation and translation of a primitive. */
function placement(part: syntax.Entry[]): {
  scale: Vec3;
  rotation: Vec3;
  translation: Vec3;
  transform: Transform;
} {
  const found = syntax.entry(part, 'scale');
  let scale = new Vec3(1, 1, 1);
  if (found?.value.kind === 'block') scale = vec3(found.value.entries, scale);
  else if (found) {
    const s = syntax.evaluate(found.value, 0) ?? 1;
    scale = new Vec3(s, s, s);
  }
  const rotation = vec3(syntax.block(part, 'rotate'), new Vec3());
  const translation = vec3(syntax.block(part, 'translate'), new Vec3());
  return { scale, rotation, translation, transform: new Transform(scale, rotation, translation) };
}

/**
 * What a scene uses that the editor cannot show (and would drop when it
 * opens the file): `animation` (keyframes) and `camera` (a tilted horizon).
 * Empty when the editor can edit the whole scene.
 */
export function editorLimits(text: string): string[] {
  let root: syntax.Entry[];
  try {
    root = syntax.parse(text);
  } catch {
    return ['shapes'];
  }
  const limits = new Set<string>();
  const hasKeyframes = (entries: syntax.Entry[]): boolean =>
    entries.some(
      (item) =>
        item.value.kind === 'block' &&
        ((/^[-+]?[\d.]/.test(item.value.entries[0]?.key || '') &&
          syntax.keyframes(item.value.entries) !== undefined) ||
          hasKeyframes(item.value.entries)),
    );
  if (syntax.block(root, 'animation') || hasKeyframes(root)) limits.add('animation');
  const camera = syntax.block(root, 'camera') || [];
  const up = syntax.block(camera, 'up');
  const tiltedUp =
    up !== undefined &&
    (syntax.number(up, 'x', 0) !== 0 ||
      syntax.number(up, 'y', 0) !== 0 ||
      syntax.number(up, 'z', 1) <= 0);
  const rotation = syntax.block(camera, 'rotation');
  const rolled =
    rotation !== undefined &&
    !syntax.block(camera, 'look_at') &&
    syntax.number(rotation, 'x', 0) !== 0;
  if (tiltedUp || rolled) limits.add('camera');
  return [...limits];
}

/**
 * An editable scene from a `.cfg` text, read like the engine reads it.
 * Triangles and quads given point by point become 3D models; named
 * materials are copied onto each object. Throws a `SyntaxError` on a
 * broken file.
 */
export function sceneFromText(text: string): SceneModel {
  const root = syntax.parse(text);
  const camera = syntax.block(root, 'camera') || [];
  const resolution = syntax.block(camera, 'resolution') || [];
  const named = namedMaterials(root);
  const colorOf = (entries: syntax.Entry[], fallback: number): Rgb => {
    const block = syntax.block(entries, 'color');
    const bare = block ? syntax.numbers(block) : [];
    if (bare.length === 3) return bare.map((value) => channel(value)) as Rgb;
    return (['r', 'g', 'b'] as const).map((key) =>
      channel(syntax.number(block || entries, key, syntax.number(entries, key, fallback))),
    ) as Rgb;
  };
  const lookOf = (part: syntax.Entry[], defaultReflection: number): SceneMaterial => {
    const source = materialSource(part, named);
    const n = (key: string, fallback: number) => syntax.number(source, key, fallback);
    const type = syntax.word(source, 'type');
    return {
      type: (MATERIAL_TYPES as readonly string[]).includes(type || '')
        ? (type as MaterialType)
        : 'phong',
      color: colorOf(source, 200),
      reflection: round(
        clampNumber(n('reflectivity', n('reflection', defaultReflection)), 0, 0.95),
      ),
      specular: round(clampNumber(n('specular', 0.65), 0, 2)),
      shininess: round(clampNumber(n('shininess', 72), 1, 512)),
      roughness: round(clampNumber(n('roughness', 0), 0, 1)),
      ior: round(clampNumber(n('ior', 1.5), 1, 3)),
      strength: round(Math.max(0, n('strength', 1))),
    };
  };

  const objects: SceneObject[] = [];
  /** Triangles in world coordinates, as a model placed at the origin. */
  const worldMesh = (points: Vec3[], faces: number[], part: syntax.Entry[]): SceneMesh => ({
    id: newId(),
    kind: 'mesh',
    x: 0,
    y: 0,
    z: 0,
    size: 1,
    rotation: [0, 0, 0],
    vertices: points.flatMap((p) => xyz(p, 5)),
    faces,
    material: lookOf(part, 0.12),
  });
  for (const item of syntax.block(root, 'primitives') || []) {
    for (const part of syntax.items(item.value)) {
      const n = (key: string, fallback: number) => syntax.number(part, key, fallback);
      const { scale, rotation, transform } = placement(part);
      const angles = xyz(rotation);
      if (item.key === 'sphere') {
        const centre = transform.point(new Vec3(n('x', 0), n('y', 0), n('z', 0)));
        objects.push({
          id: newId(),
          kind: 'sphere',
          ...placed(centre),
          radius: round(Math.max(0.001, n('radius', 1) * transform.uniformScale())),
          material: lookOf(part, 0.32),
        });
      } else if (item.key === 'plane') {
        const block = syntax.block(part, 'normal');
        const raw = block
          ? vec3(block, new Vec3(0, 0, 1))
          : new Vec3(n('normal_x', 0), n('normal_y', 0), n('normal_z', 1));
        const normal = raw.length() > 0 ? transform.normal(raw.normalized()) : new Vec3(0, 0, 1);
        objects.push({
          id: newId(),
          kind: 'plane',
          ...placed(transform.point(new Vec3(n('x', 0), n('y', 0), n('z', 0)))),
          normal: xyz(normal),
          material: lookOf(part, 0.12),
        });
      } else if (item.key === 'box') {
        const low = vec3(syntax.block(part, 'min'), new Vec3(-0.5, -0.5, -0.5));
        const high = vec3(syntax.block(part, 'max'), new Vec3(0.5, 0.5, 0.5));
        const size = high.sub(low).hadamard(scale);
        objects.push({
          id: newId(),
          kind: 'box',
          ...placed(transform.point(low.add(high).mul(0.5))),
          size: xyz(new Vec3(Math.abs(size.x), Math.abs(size.y), Math.abs(size.z))),
          rotation: angles,
          material: lookOf(part, 0.12),
        });
      } else if (item.key === 'quad') {
        const corner = syntax.block(part, 'corner');
        const u = syntax.block(part, 'u');
        const v = syntax.block(part, 'v');
        if (!corner && !u && !v) {
          objects.push({
            id: newId(),
            kind: 'panel',
            ...placed(transform.point(new Vec3())),
            width: round(Math.abs(scale.y)),
            height: round(Math.abs(scale.z)),
            rotation: angles,
            material: lookOf(part, 0.12),
          });
        } else {
          const origin = transform.point(vec3(corner, new Vec3(0, -0.5, -0.5)));
          const side1 = transform.vector(vec3(u, new Vec3(0, 1, 0)));
          const side2 = transform.vector(vec3(v, new Vec3(0, 0, 1)));
          objects.push(
            worldMesh(
              [origin, origin.add(side1), origin.add(side1).add(side2), origin.add(side2)],
              [0, 1, 2, 0, 2, 3],
              part,
            ),
          );
        }
      } else if (item.key === 'triangle') {
        const points = [
          vec3(syntax.block(part, 'a'), new Vec3()),
          vec3(syntax.block(part, 'b'), new Vec3(0, 1, 0)),
          vec3(syntax.block(part, 'c'), new Vec3(0, 0, 1)),
        ];
        objects.push(
          worldMesh(
            points.map((p) => transform.point(p)),
            [0, 1, 2],
            part,
          ),
        );
      } else if (item.key === 'mesh') {
        const raw = syntax.numbers(syntax.block(part, 'vertices') || []);
        const faces = syntax.numbers(syntax.block(part, 'faces') || []);
        const uniform = scale.x === scale.y && scale.y === scale.z;
        // A stretched model keeps its look: the stretch goes into its points.
        const vertices = uniform ? raw : raw.map((value, i) => round(value * scale.axis(i % 3), 5));
        objects.push({
          id: newId(),
          kind: 'mesh',
          ...placed(transform.point(new Vec3())),
          vertices,
          faces,
          size: uniform ? round(scale.x) : 1,
          rotation: angles,
          material: lookOf(part, 0.12),
        });
      }
    }
  }

  const lights: SceneLight[] = [];
  for (const item of syntax.block(root, 'lights') || []) {
    if (item.key !== 'point' && item.key !== 'area') continue;
    for (const part of syntax.items(item.value)) {
      const n = (key: string, fallback: number) => round(syntax.number(part, key, fallback));
      lights.push({
        id: newId(),
        kind: item.key,
        x: n('x', 4),
        y: n('y', 0),
        z: n('z', 5),
        intensity: Math.max(0, n('intensity', 450)),
        color: colorOf(part, 255),
        radius: Math.max(0.01, n('radius', 0.5)),
      });
    }
  }
  const settings = renderSettings(text);
  // The engine adds this light to a classic render without any: the editor
  // shows it, so the user sees (and can move) the light that will be used.
  if (!lights.length && settings.mode === 'whitted')
    lights.push(newLight({ x: 4, y: 0, z: 5, intensity: 450 }));

  const render = syntax.block(root, 'render') || [];
  const quality: RenderQuality =
    settings.mode === 'path' ? 'photo' : settings.samples > 1 ? 'smooth' : 'draft';
  const sky = round(Math.max(0, syntax.number(render, 'sky', 1)));
  const exposure = round(Math.max(0, syntax.number(render, 'exposure', 1)));
  return {
    width: Math.floor(Math.max(1, syntax.number(resolution, 'width', 320))),
    height: Math.floor(Math.max(1, syntax.number(resolution, 'height', 200))),
    fov: clampNumber(syntax.number(camera, 'fieldOfView', 55), 1, 179),
    camera: readCamera(camera),
    objects,
    lights,
    ...(quality === 'draft' ? {} : { quality }),
    ...(sky !== 1 ? { sky } : {}),
    ...(exposure !== 1 ? { exposure } : {}),
  };
}

const placed = (centre: Vec3) => ({ x: round(centre.x), y: round(centre.y), z: round(centre.z) });

/** Position, heading and lens of the `camera` block (`look_at`, `direction` and `rotation` become yaw and pitch). */
function readCamera(camera: syntax.Entry[]): SceneCamera {
  const position = syntax.block(camera, 'position')
    ? vec3(syntax.block(camera, 'position'), new Vec3())
    : new Vec3(
        syntax.number(camera, 'x', 0),
        syntax.number(camera, 'y', 0),
        syntax.number(camera, 'z', 0),
      );
  const target = syntax.block(camera, 'look_at')
    ? vec3(syntax.block(camera, 'look_at'), new Vec3(1, 0, 0))
    : undefined;
  let forward = (
    target ? target.sub(position) : vec3(syntax.block(camera, 'direction'), new Vec3(1, 0, 0))
  ).normalized();
  if (forward.length() === 0) forward = new Vec3(1, 0, 0);
  const rotation = syntax.block(camera, 'rotation');
  if (!target && rotation)
    forward = new Transform(new Vec3(1, 1, 1), vec3(rotation, new Vec3()), new Vec3())
      .vector(forward)
      .normalized();
  const degrees = (radians: number) => round((radians * 180) / Math.PI, 1);
  const aperture = round(Math.max(0, syntax.number(camera, 'aperture', 0)));
  return {
    ...placed(position),
    yaw: degrees(-Math.atan2(forward.y, forward.x)),
    pitch: degrees(Math.asin(clampNumber(forward.z, -1, 1))),
    aperture,
    focus: round(
      Math.max(
        0.01,
        syntax.number(camera, 'focus_distance', target ? target.sub(position).length() : 5),
      ),
    ),
  };
}

/** The `.cfg` file name for a job title. */
export function sceneFileName(title: string): string {
  const slug = title
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
  return `${slug || 'scene'}.cfg`;
}
