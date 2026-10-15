// Raytracer scenes on the site: the model edited by the scene editor, the
// `.cfg` text it writes, and a faithful port of the engine's parser
// (Network/crates/raytracer/src/parser.rs) used by the preview and the checks.
//
// Coordinates are the engine's: the camera looks along +x, +z is up and +y is
// on the LEFT of the image (the editor shows `-y` as "left ↔ right").

export type Rgb = [number, number, number];

export interface SceneMaterial {
  /** 0–255 per channel. */
  color: Rgb;
  /** Share of reflected light, 0–0.95. */
  reflection: number;
  /** Strength of the highlight, 0–2. */
  specular: number;
  /** Size of the highlight (1 = wide, 512 = pin-point). */
  shininess: number;
}

export interface SceneSphere { id: number; kind: 'sphere'; x: number; y: number; z: number; radius: number; material: SceneMaterial }
export interface ScenePlane { id: number; kind: 'plane'; x: number; y: number; z: number; normal: [number, number, number]; material: SceneMaterial }
export type SceneObject = SceneSphere | ScenePlane;
export interface SceneLight { id: number; x: number; y: number; z: number; intensity: number; color: Rgb }

export interface SceneModel {
  width: number;
  height: number;
  /** Horizontal field of view, 1–179 degrees. */
  fov: number;
  camera: { x: number; y: number; z: number };
  objects: SceneObject[];
  lights: SceneLight[];
}

/** Ready-made looks for a material. */
export const MATERIAL_PRESETS = {
  matte: { reflection: 0.04, specular: 0.15, shininess: 12 },
  glossy: { reflection: 0.25, specular: 0.8, shininess: 96 },
  mirror: { reflection: 0.85, specular: 1, shininess: 256 },
  metal: { reflection: 0.55, specular: 1.4, shininess: 48 },
} as const;
export type MaterialPreset = keyof typeof MATERIAL_PRESETS;

/** The preset a material matches, or `custom`. */
export function materialPreset(material: SceneMaterial): MaterialPreset | 'custom' {
  const found = (Object.keys(MATERIAL_PRESETS) as MaterialPreset[]).find((name) => {
    const preset = MATERIAL_PRESETS[name];
    return preset.reflection === material.reflection && preset.specular === material.specular && preset.shininess === material.shininess;
  });
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
} as const satisfies Record<string, [number, number, number]>;
export type PlaneOrientation = keyof typeof PLANE_ORIENTATIONS;

export function planeOrientation(plane: ScenePlane): PlaneOrientation | 'custom' {
  const found = (Object.keys(PLANE_ORIENTATIONS) as PlaneOrientation[]).find((name) => PLANE_ORIENTATIONS[name].every((value, index) => value === plane.normal[index]));
  return found || 'custom';
}

let nextId = 1;
/** A fresh id for a new object or light. */
export const newId = (): number => nextId++;

export const newSphere = (patch: Partial<Omit<SceneSphere, 'id' | 'kind'>> = {}): SceneSphere => ({
  id: newId(), kind: 'sphere', x: 5, y: 0, z: 0, radius: 0.8,
  material: { color: [70, 160, 255], ...MATERIAL_PRESETS.glossy }, ...patch,
});

export const newPlane = (patch: Partial<Omit<ScenePlane, 'id' | 'kind'>> = {}): ScenePlane => ({
  id: newId(), kind: 'plane', x: 0, y: 0, z: -1, normal: [0, 0, 1],
  material: { color: [225, 232, 240], reflection: 0.15, specular: 0.4, shininess: 48 }, ...patch,
});

export const newLight = (patch: Partial<Omit<SceneLight, 'id'>> = {}): SceneLight => ({
  id: newId(), x: 3, y: 0, z: 5, intensity: 400, color: [255, 255, 255], ...patch,
});

/** Deep copy (the editor never shares arrays between scenes). */
export const cloneScene = (scene: SceneModel): SceneModel => JSON.parse(JSON.stringify(scene)) as SceneModel;

// ---------------------------------------------------------------- writing

/** A number as the `.cfg` writes it: at most 3 decimals, no `-0`. */
export function formatNumber(value: number, decimals = 3): string {
  const rounded = Number(value.toFixed(decimals));
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

const clampNumber = (value: number, min: number, max: number) => Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
const point = (item: { x: number; y: number; z: number }) => `x = ${formatNumber(item.x)} y = ${formatNumber(item.y)} z = ${formatNumber(item.z)}`;
const color = (rgb: Rgb) => `color = { r = ${Math.round(clampNumber(rgb[0], 0, 255))} g = ${Math.round(clampNumber(rgb[1], 0, 255))} b = ${Math.round(clampNumber(rgb[2], 0, 255))} }`;
const material = (value: SceneMaterial) => `reflection = ${formatNumber(clampNumber(value.reflection, 0, 0.95))} specular = ${formatNumber(clampNumber(value.specular, 0, 2))} shininess = ${formatNumber(clampNumber(value.shininess, 1, 512), 1)} ${color(value.color)}`;

/**
 * The `.cfg` file of a scene, in the format of the engine's example scenes.
 * Comments are kept outside the blocks: the engine has no comment syntax and
 * would read a `key = value` written in one.
 */
export function sceneToCfg(scene: SceneModel, title = ''): string {
  const width = Math.round(clampNumber(scene.width, 1, 16384));
  const height = Math.round(clampNumber(scene.height, 1, 16384));
  const name = title.replace(/[\r\n]+/g, ' ').trim();
  const lines = [
    `# ${name || 'Silicium scene'}`,
    '# Written by the Silicium scene editor.',
    '',
    'camera :',
    '{',
    `\tresolution = { width = ${width} height = ${height} }`,
    `\tposition = { ${point(scene.camera)} }`,
    '\tdirection = { x = 1 y = 0 z = 0 }',
    `\tfieldOfView = ${formatNumber(clampNumber(scene.fov, 1, 179), 1)}`,
    '};',
    '',
    'primitives :',
    '{',
    ...scene.objects.map((item) => item.kind === 'sphere'
      ? `\tsphere = { ${point(item)} radius = ${formatNumber(Math.max(0.001, item.radius))} ${material(item.material)} }`
      : `\tplane = { ${point(item)} normal_x = ${formatNumber(item.normal[0])} normal_y = ${formatNumber(item.normal[1])} normal_z = ${formatNumber(item.normal[2])} ${material(item.material)} }`),
    '};',
    '',
    'lights :',
    '{',
    ...scene.lights.map((light) => `\tpoint = { ${point(light)} intensity = ${formatNumber(Math.max(0, light.intensity), 1)} r = ${Math.round(clampNumber(light.color[0], 0, 255))} g = ${Math.round(clampNumber(light.color[1], 0, 255))} b = ${Math.round(clampNumber(light.color[2], 0, 255))} }`),
    '};',
    '',
  ];
  return lines.join('\n');
}

// ---------------------------------------------------------------- parsing (port of parser.rs)

/** What the engine renders, as read by its parser (colours in 0–1). */
export interface RenderMaterial { color: [number, number, number]; reflectivity: number; specular: number; shininess: number }
export type RenderPrimitive =
  | { kind: 'sphere'; center: [number, number, number]; radius: number; material: RenderMaterial }
  | { kind: 'plane'; point: [number, number, number]; normal: [number, number, number]; material: RenderMaterial };
export interface RenderLight { position: [number, number, number]; intensity: number; color: [number, number, number] }
export interface RenderScene { width: number; height: number; fov: number; camera: [number, number, number]; primitives: RenderPrimitive[]; lights: RenderLight[] }

export const EPSILON = 1e-4;

/** Rust's `str::parse::<f64>()` (no hex, no empty string). */
export function parseRustFloat(text: string): number | undefined {
  if (/^[+-]?(inf|infinity)$/i.test(text)) return text.startsWith('-') ? -Infinity : Infinity;
  if (/^[+-]?nan$/i.test(text)) return Number.NaN;
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(text)) return undefined;
  return Number(text);
}

/** Same tokens as the engine: words, numbers and `{ } = : ;`. */
export function engineTokens(text: string): string[] {
  const result: string[] = [];
  let current = '';
  for (const character of text) {
    if (/[A-Za-z0-9_.]/.test(character) || ((character === '-' || character === '+') && current === '')) {
      current += character;
    } else {
      if (current) { result.push(current); current = ''; }
      if ('{}=:;'.includes(character)) result.push(character);
    }
  }
  if (current) result.push(current);
  return result;
}

function blocks(source: string[], name: string): string[][] {
  const result: string[][] = [];
  let index = 0;
  while (index + 2 < source.length) {
    if (source[index] !== name || !(source[index + 1] === '=' || source[index + 1] === ':') || source[index + 2] !== '{') {
      index += 1;
      continue;
    }
    let depth = 1;
    let cursor = index + 3;
    while (cursor < source.length && depth > 0) {
      if (source[cursor] === '{') depth += 1;
      else if (source[cursor] === '}') depth -= 1;
      cursor += 1;
    }
    if (depth !== 0) break;
    result.push(source.slice(index + 3, cursor - 1));
    index = cursor;
  }
  return result;
}

function scalar(source: string[], key: string, fallback: number): number {
  for (let index = 0; index + 2 < source.length; index += 1) {
    if (source[index] === key && source[index + 1] === '=') return parseRustFloat(source[index + 2]!) ?? fallback;
  }
  return fallback;
}

// Rust's f64::max/clamp: `max` ignores NaN, `clamp` keeps it.
const rustMax = (value: number, other: number) => (Number.isNaN(value) ? other : Math.max(value, other));
const rustClamp = (value: number, min: number, max: number) => (Number.isNaN(value) ? value : Math.min(max, Math.max(min, value)));

function normalized(vector: [number, number, number]): [number, number, number] {
  const length = Math.sqrt(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2]);
  if (length <= EPSILON) return [0, 0, 0];
  const inverse = 1 / length;
  return [vector[0] * inverse, vector[1] * inverse, vector[2] * inverse];
}

function parseMaterial(source: string[], defaultReflectivity: number): RenderMaterial {
  return {
    color: [scalar(source, 'r', 200) / 255, scalar(source, 'g', 200) / 255, scalar(source, 'b', 200) / 255],
    reflectivity: rustClamp(scalar(source, 'reflectivity', scalar(source, 'reflection', defaultReflectivity)), 0, 0.95),
    specular: rustClamp(scalar(source, 'specular', 0.65), 0, 2),
    shininess: rustClamp(scalar(source, 'shininess', 72), 1, 512),
  };
}

/** The scene the engine would render from this text (missing keys take the engine's defaults). */
export function parseSceneText(text: string): RenderScene {
  const source = engineTokens(text);
  const camera = blocks(source, 'camera')[0] || [];
  const primitives: RenderPrimitive[] = [];
  for (const sphere of blocks(source, 'sphere')) {
    primitives.push({
      kind: 'sphere',
      center: [scalar(sphere, 'x', 0), scalar(sphere, 'y', 0), scalar(sphere, 'z', 0)],
      radius: rustMax(scalar(sphere, 'radius', 1), EPSILON),
      material: parseMaterial(sphere, 0.32),
    });
  }
  for (const plane of blocks(source, 'plane')) {
    primitives.push({
      kind: 'plane',
      point: [scalar(plane, 'x', 0), scalar(plane, 'y', 0), scalar(plane, 'z', 0)],
      normal: normalized([scalar(plane, 'normal_x', 0), scalar(plane, 'normal_y', 0), scalar(plane, 'normal_z', 1)]),
      material: parseMaterial(plane, 0.12),
    });
  }
  const lights: RenderLight[] = blocks(source, 'point').map((light) => ({
    position: [scalar(light, 'x', 4), scalar(light, 'y', 0), scalar(light, 'z', 5)],
    intensity: rustMax(scalar(light, 'intensity', 450), 0),
    color: [scalar(light, 'r', 255) / 255, scalar(light, 'g', 255) / 255, scalar(light, 'b', 255) / 255],
  }));
  if (!lights.length) lights.push({ position: [4, 0, 5], intensity: 450, color: [1, 1, 1] });
  return {
    width: Math.floor(rustMax(scalar(camera, 'width', 320), 1)),
    height: Math.floor(rustMax(scalar(camera, 'height', 200), 1)),
    fov: rustClamp(scalar(camera, 'fieldOfView', 55), 1, 179),
    camera: [scalar(camera, 'x', 0), scalar(camera, 'y', 0), scalar(camera, 'z', 0)],
    primitives,
    lights,
  };
}

const toRgb = (channels: [number, number, number]): Rgb => channels.map((value) => Math.round(rustClamp(value * 255, 0, 255))) as Rgb;
const round = (value: number) => Number(value.toFixed(3));

/**
 * An editable scene from a `.cfg` text: what the engine reads from it, so
 * opening a file in the editor also drops what the engine would ignore.
 */
export function sceneFromText(text: string): SceneModel {
  const parsed = parseSceneText(text);
  const declaresLight = blocks(engineTokens(text), 'point').length > 0;
  return {
    width: parsed.width,
    height: parsed.height,
    fov: parsed.fov,
    camera: { x: round(parsed.camera[0]), y: round(parsed.camera[1]), z: round(parsed.camera[2]) },
    objects: parsed.primitives.map((primitive): SceneObject => {
      const look: SceneMaterial = { color: toRgb(primitive.material.color), reflection: round(primitive.material.reflectivity), specular: round(primitive.material.specular), shininess: round(primitive.material.shininess) };
      return primitive.kind === 'sphere'
        ? { id: newId(), kind: 'sphere', x: round(primitive.center[0]), y: round(primitive.center[1]), z: round(primitive.center[2]), radius: round(primitive.radius), material: look }
        : { id: newId(), kind: 'plane', x: round(primitive.point[0]), y: round(primitive.point[1]), z: round(primitive.point[2]), normal: primitive.normal.map(round) as [number, number, number], material: look };
    }),
    // The engine adds a light when there is none; the editor shows it, so the
    // user sees (and can move) the light that will be used.
    lights: parsed.lights.map((light) => ({ id: newId(), x: round(light.position[0]), y: round(light.position[1]), z: round(light.position[2]), intensity: round(light.intensity), color: toRgb(light.color) }))
      .slice(0, declaresLight ? undefined : 1),
  };
}

/** The `.cfg` file name for a job title. */
export function sceneFileName(title: string): string {
  const slug = title.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48);
  return `${slug || 'scene'}.cfg`;
}
