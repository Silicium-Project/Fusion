// Checks a scene file before it is sent: the same rules as
// `silicium-raytracer check` (Network/crates/raytracer/src/engine/check.rs),
// run in the browser. `tests/fixtures/check_cases.json` is shared with the
// engine's tests (keep both copies identical).

import {
  all,
  block,
  entry,
  evaluate,
  items,
  keyframes,
  numbers as bareNumbers,
  number,
  parse,
  SyntaxError,
  word,
  type Entry,
  type Value,
} from './sceneSyntax';

export type IssueSeverity = 'error' | 'warning';

export interface SceneIssue {
  severity: IssueSeverity;
  /** Stable code, translated by `sceneCheck.codes.<code>`. */
  code: string;
  /** 1-based line, 0 for the whole scene. */
  line: number;
  key: string;
  suggestion?: string;
  /** Values for the message (`value`, `min`, `max`, `planned`, `actual`…). */
  params: Record<string, string | number>;
}

export interface SceneSummary {
  width: number;
  height: number;
  spheres: number;
  planes: number;
  /** Triangles and quads (boxes, meshes…). */
  triangles: number;
  lights: number;
  fieldOfView: number;
  samples: number;
  mode: 'whitted' | 'path';
}

export interface SceneReport {
  valid: boolean;
  errors: number;
  warnings: number;
  issues: SceneIssue[];
  scene: SceneSummary;
}

/** Version of the engine these rules follow (`ENGINE_VERSION`). */
export const ENGINE_VERSION = 2;
const EPSILON = 1e-4;
const LARGE_PIXELS = 7680 * 4320;

const ERRORS = new Set([
  'unbalanced_braces',
  'syntax_error',
  'not_a_number',
  'invalid_value',
  'unknown_material',
  'engine_too_new',
  'missing_resolution',
  'resolution_mismatch',
  'zero_normal',
  'bad_mesh',
  'engine_error',
]);

const UNSUPPORTED = new Set([
  'ambient',
  'antialiasing',
  'cone',
  'cube',
  'cylinder',
  'diffuse_light',
  'directional',
  'obj',
  'refraction',
  'shear',
  'spot',
  'texture',
  'torus',
  'transparency',
]);

type Kind =
  | {
      name:
        | 'root'
        | 'render'
        | 'camera'
        | 'resolution'
        | 'vector'
        | 'color'
        | 'materials'
        | 'material'
        | 'primitives'
        | 'lights'
        | 'animation'
        | 'list';
    }
  | { name: 'object'; shape: string }
  | { name: 'light'; shape: string };

const K = (name: Exclude<Kind['name'], 'object' | 'light'>): Kind => ({ name }) as Kind;
const MATERIAL_VALUES = [
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
const TYPES = ['phong', 'diffuse', 'metal', 'glass', 'emissive'];

function values(kind: Kind): string[] {
  switch (kind.name) {
    case 'root':
      return ['frame'];
    case 'render':
      return ['engine', 'samples', 'bounces', 'exposure', 'sky', 'seed', 'frame', 'clamp'];
    case 'camera':
      return ['fieldOfView', 'aperture', 'focus_distance', 'x', 'y', 'z'];
    case 'resolution':
      return ['width', 'height'];
    case 'vector':
      return ['x', 'y', 'z'];
    case 'color':
      return ['r', 'g', 'b'];
    case 'material':
      return MATERIAL_VALUES;
    case 'object': {
      const own =
        kind.shape === 'sphere'
          ? ['x', 'y', 'z', 'radius']
          : kind.shape === 'plane'
            ? ['x', 'y', 'z', 'normal_x', 'normal_y', 'normal_z']
            : [];
      return [...own, ...MATERIAL_VALUES, 'scale'];
    }
    case 'light':
      return kind.shape === 'area'
        ? ['x', 'y', 'z', 'intensity', 'r', 'g', 'b', 'radius']
        : ['x', 'y', 'z', 'intensity', 'r', 'g', 'b'];
    case 'animation':
      return ['frames', 'fps'];
    default:
      return [];
  }
}

function words(kind: Kind): [string, string[]][] {
  if (kind.name === 'render')
    return [
      ['mode', ['whitted', 'path']],
      ['tonemap', ['clamp', 'reinhard', 'aces']],
    ];
  if (kind.name === 'material')
    return [
      ['name', []],
      ['type', TYPES],
    ];
  if (kind.name === 'object')
    return [
      ['material', []],
      ['type', TYPES],
    ];
  return [];
}

function blocks(kind: Kind): [string, Kind][] {
  const transforms: [string, Kind][] = [
    ['translate', K('vector')],
    ['rotate', K('vector')],
    ['scale', K('vector')],
    ['color', K('color')],
  ];
  switch (kind.name) {
    case 'root':
      return [
        ['render', K('render')],
        ['camera', K('camera')],
        ['materials', K('materials')],
        ['primitives', K('primitives')],
        ['lights', K('lights')],
        ['animation', K('animation')],
        ['effects', K('list')],
      ];
    case 'camera':
      return [
        ['resolution', K('resolution')],
        ['position', K('vector')],
        ['look_at', K('vector')],
        ['direction', K('vector')],
        ['rotation', K('vector')],
        ['up', K('vector')],
      ];
    case 'materials':
      return [['material', K('material')]];
    case 'material':
      return [['color', K('color')]];
    case 'primitives':
      return ['sphere', 'plane', 'box', 'triangle', 'quad', 'mesh'].map((shape) => [
        shape,
        { name: 'object', shape },
      ]);
    case 'object': {
      const own: [string, Kind][] =
        kind.shape === 'plane'
          ? [['normal', K('vector')]]
          : kind.shape === 'box'
            ? [
                ['min', K('vector')],
                ['max', K('vector')],
              ]
            : kind.shape === 'triangle'
              ? [
                  ['a', K('vector')],
                  ['b', K('vector')],
                  ['c', K('vector')],
                ]
              : kind.shape === 'quad'
                ? [
                    ['corner', K('vector')],
                    ['u', K('vector')],
                    ['v', K('vector')],
                  ]
                : kind.shape === 'mesh'
                  ? [
                      ['vertices', K('list')],
                      ['faces', K('list')],
                    ]
                  : [];
      return [...own, ...transforms];
    }
    case 'lights':
      return [
        ['point', { name: 'light', shape: 'point' }],
        ['area', { name: 'light', shape: 'area' }],
      ];
    case 'light':
      return [['color', K('color')]];
    default:
      return [];
  }
}

function range(kind: Kind, key: string): [number, number] | undefined {
  const n = kind.name;
  if (n === 'render' && key === 'samples') return [1, 65_536];
  if (n === 'render' && key === 'bounces') return [0, 64];
  if (n === 'render' && ['exposure', 'sky', 'seed', 'clamp'].includes(key)) return [0, Infinity];
  if (n === 'render' && key === 'engine') return [1, ENGINE_VERSION];
  if (n === 'camera' && key === 'fieldOfView') return [1, 179];
  if (n === 'camera' && key === 'aperture') return [0, Infinity];
  if (n === 'resolution') return [1, Infinity];
  if (n === 'color' || key === 'r' || key === 'g' || key === 'b') return [0, 255];
  if (key === 'reflection' || key === 'reflectivity') return [0, 0.95];
  if (key === 'specular') return [0, 2];
  if (key === 'shininess') return [1, 512];
  if (key === 'roughness') return [0, 1];
  if (key === 'ior') return [1, 3];
  if (key === 'strength' || key === 'intensity') return [0, Infinity];
  if (key === 'radius') return [1e-4, Infinity];
  return undefined;
}

function misplaced(key: string): string | undefined {
  if (['sphere', 'plane', 'box', 'triangle', 'quad', 'mesh'].includes(key)) return 'primitives';
  if (key === 'point' || key === 'area') return 'lights';
  if (key === 'material') return 'materials';
  return undefined;
}

function distance(left: string, right: string): number {
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let i = 0; i < left.length; i += 1) {
    const row = [i + 1];
    for (let j = 0; j < right.length; j += 1)
      row.push(
        Math.min(previous[j]! + (left[i] === right[j] ? 0 : 1), previous[j + 1]! + 1, row[j]! + 1),
      );
    previous = row;
  }
  return previous[right.length]!;
}

/** Closest known word (case-insensitive edit distance at most 2). */
function suggest(text: string, candidates: string[]): string | undefined {
  let best: { score: number; candidate: string } | undefined;
  for (const candidate of candidates) {
    const score = distance(text.toLowerCase(), candidate.toLowerCase());
    if (score <= 2 && score < candidate.length && (!best || score < best.score))
      best = { score, candidate };
  }
  return best?.candidate;
}

/** The tile planner's reading of the resolution (`tiles::scene_resolution`). */
export function plannedResolution(text: string): { width: number; height: number } {
  const match = /resolution\s*=\s*\{[^}]*width\s*=\s*(\d+)[^}]*height\s*=\s*(\d+)/i.exec(text);
  if (!match) return { width: 1920, height: 1080 };
  return { width: Math.max(1, Number(match[1])), height: Math.max(1, Number(match[2])) };
}

type Vec = [number, number, number];
const sub = (a: Vec, b: Vec): Vec => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
function normalize(a: Vec): Vec {
  const length = Math.sqrt(dot(a, a));
  return length <= EPSILON ? [0, 0, 0] : [a[0] / length, a[1] / length, a[2] / length];
}

function vector(entries: Entry[] | undefined, fallback: Vec, frame: number): Vec {
  if (!entries) return fallback;
  const bare = bareNumbers(entries);
  if (bare.length === 3) return bare as Vec;
  return [
    number(entries, 'x', fallback[0], frame),
    number(entries, 'y', fallback[1], frame),
    number(entries, 'z', fallback[2], frame),
  ];
}

/** Rows of Rz · Ry · Rx (degrees), as in `geometry::Transform`. */
function rotate(degrees: Vec, v: Vec): Vec {
  const [ax, ay, az] = degrees.map((d) => (d * Math.PI) / 180) as Vec;
  const [sx, cx, sy, cy, sz, cz] = [
    Math.sin(ax),
    Math.cos(ax),
    Math.sin(ay),
    Math.cos(ay),
    Math.sin(az),
    Math.cos(az),
  ];
  const rows: Vec[] = [
    [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
    [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
    [-sy, cy * sx, cy * cx],
  ];
  return [dot(rows[0]!, v), dot(rows[1]!, v), dot(rows[2]!, v)];
}

/** What the engine builds from the scene, as far as the checks need it. */
interface Built {
  width: number;
  height: number;
  origin: Vec;
  forward: Vec;
  mode: 'whitted' | 'path';
  sky: number;
  samples: number;
  shapes: number;
  areaLights: number;
  emitters: number;
  points: number;
  spheres: number;
  planes: number;
  triangles: number;
}

function build(root: Entry[]): Built | string {
  const render = block(root, 'render') || [];
  const lastFrame = [...root].reverse().find((item) => item.key === 'frame');
  const frame = (lastFrame && evaluate(lastFrame.value, 0)) ?? number(render, 'frame', 0);
  const mode = word(render, 'mode') === 'path' ? 'path' : 'whitted';
  const camera = block(root, 'camera') || [];
  const resolution = block(camera, 'resolution') || [];
  const origin = block(camera, 'position')
    ? vector(block(camera, 'position'), [0, 0, 0], frame)
    : ([
        number(camera, 'x', 0, frame),
        number(camera, 'y', 0, frame),
        number(camera, 'z', 0, frame),
      ] as Vec);
  const lookAt = block(camera, 'look_at')
    ? vector(block(camera, 'look_at'), [1, 0, 0], frame)
    : undefined;
  let forward = normalize(
    lookAt
      ? sub(lookAt, origin)
      : block(camera, 'direction')
        ? vector(block(camera, 'direction'), [1, 0, 0], frame)
        : [1, 0, 0],
  );
  if (!dot(forward, forward)) forward = [1, 0, 0];
  if (!lookAt && block(camera, 'rotation'))
    forward = normalize(rotate(vector(block(camera, 'rotation'), [0, 0, 0], frame), forward));

  const named = new Map<string, boolean>();
  for (const item of all(block(root, 'materials') || [], 'material')) {
    for (const part of items(item.value)) {
      const name = word(part, 'name');
      if (name === undefined) return `line ${item.line}: material without \`name\``;
      named.set(name, word(part, 'type') === 'emissive');
    }
  }
  const emissive = (part: Entry[]) => {
    const own = [
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
    ].some((key) => entry(part, key));
    const name = word(part, 'material');
    if (name !== undefined && !own) return named.get(name) ?? false;
    return word(part, 'type') === 'emissive';
  };
  const built: Built = {
    width: Math.floor(Math.max(1, number(resolution, 'width', 320))),
    height: Math.floor(Math.max(1, number(resolution, 'height', 200))),
    origin,
    forward,
    mode,
    sky: Math.max(0, number(render, 'sky', 1, frame)),
    samples: Math.floor(Math.min(65_536, Math.max(1, number(render, 'samples', 1, frame)))),
    shapes: 0,
    areaLights: 0,
    emitters: 0,
    points: 0,
    spheres: 0,
    planes: 0,
    triangles: 0,
  };
  for (const item of block(root, 'primitives') || []) {
    if (!item.key) continue;
    for (const part of items(item.value)) {
      const glowing = emissive(part);
      const add = (count: number, sampled: boolean) => {
        built.shapes += count;
        if (glowing && sampled) built.emitters += count;
      };
      if (item.key === 'sphere') {
        add(1, true);
        built.spheres += 1;
      } else if (item.key === 'plane') {
        add(1, false);
        built.planes += 1;
      } else if (item.key === 'box') {
        add(6, true);
        built.triangles += 6;
      } else if (item.key === 'triangle' || item.key === 'quad') {
        add(1, true);
        built.triangles += 1;
      } else if (item.key === 'mesh') {
        const faces = Math.floor(bareNumbers(block(part, 'faces') || []).length / 3);
        add(faces, true);
        built.triangles += faces;
      }
    }
  }
  for (const item of block(root, 'lights') || []) {
    for (const _part of items(item.value)) {
      if (item.key === 'point') built.points += 1;
      if (item.key === 'area') {
        built.areaLights += 1;
        built.shapes += 1;
        built.emitters += 1;
      }
    }
  }
  if (mode === 'whitted' && built.points === 0 && built.areaLights === 0) built.points = 1;
  return built;
}

/** Problems of a scene file, with their lines. */
export function checkScene(text: string): SceneReport {
  const issues: SceneIssue[] = [];
  const push = (
    code: string,
    line: number,
    key = '',
    params: Record<string, string | number> = {},
    suggestion?: string,
  ) => {
    issues.push({
      severity: ERRORS.has(code) ? 'error' : 'warning',
      code,
      line,
      key,
      params: { key, ...params },
      ...(suggestion ? { suggestion } : {}),
    });
  };
  const summary: SceneSummary = {
    width: 320,
    height: 200,
    spheres: 0,
    planes: 0,
    triangles: 0,
    lights: 0,
    fieldOfView: 55,
    samples: 1,
    mode: 'whitted',
  };
  const finish = (): SceneReport => {
    issues.sort((a, b) => Number(a.line === 0) - Number(b.line === 0) || a.line - b.line);
    const errors = issues.filter((issue) => issue.severity === 'error').length;
    return {
      valid: errors === 0,
      errors,
      warnings: issues.length - errors,
      issues,
      scene: summary,
    };
  };
  let root: Entry[];
  try {
    root = parse(text);
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    push(error.code, error.line, '', { extra: error.message.includes('closes nothing') ? 1 : 0 });
    return finish();
  }

  // Problems that make the engine refuse the scene (its summary then stays empty).
  let refused = false;
  const materialNames = new Set<string>();
  const materialUses: [string, number][] = [];
  const spheres: [Vec, number, number][] = [];
  let lights = 0;
  let resolutionLine: number | undefined;
  let cameraLine: number | undefined;

  const checkNumber = (kind: Kind, key: string, item: Entry) => {
    let ok = true;
    if (item.value.kind === 'number') {
      const bounds = range(kind, key);
      const value = item.value.value;
      if (bounds && !(value >= bounds[0] && value <= bounds[1]))
        push('out_of_range', item.line, key, {
          value,
          min: bounds[0],
          max: bounds[1] === Infinity ? '' : bounds[1],
        });
    } else ok = item.value.kind === 'block' && keyframes(item.value.entries) !== undefined;
    if (!ok)
      push('not_a_number', item.line, key, {
        value: item.value.kind === 'word' ? item.value.value : '{…}',
      });
  };

  const object = (shape: string, part: Entry[], line: number) => {
    const n = (key: string, fallback: number) => number(part, key, fallback);
    const translate = block(part, 'translate');
    const offset: Vec = translate
      ? [number(translate, 'x', 0), number(translate, 'y', 0), number(translate, 'z', 0)]
      : [0, 0, 0];
    const scaleValue = entry(part, 'scale')?.value;
    const scale =
      scaleValue?.kind === 'number'
        ? Math.abs(scaleValue.value)
        : scaleValue?.kind === 'block' && !keyframes(scaleValue.entries)
          ? Math.max(0, ...['x', 'y', 'z'].map((k) => Math.abs(number(scaleValue.entries, k, 1))))
          : 1;
    if (shape === 'sphere')
      spheres.push([
        [n('x', 0) + offset[0], n('y', 0) + offset[1], n('z', 0) + offset[2]],
        n('radius', 1) * scale,
        line,
      ]);
    if (shape === 'plane') {
      const normalBlock = block(part, 'normal');
      const normal: Vec = normalBlock
        ? [number(normalBlock, 'x', 0), number(normalBlock, 'y', 0), number(normalBlock, 'z', 1)]
        : [n('normal_x', 0), n('normal_y', 0), n('normal_z', 1)];
      if (Math.sqrt(dot(normal, normal)) <= EPSILON) {
        push('zero_normal', line);
        refused = true;
      }
    }
    if (shape !== 'mesh') return;
    const vertices = bareNumbers(block(part, 'vertices') || []);
    const faces = bareNumbers(block(part, 'faces') || []);
    const count = Math.floor(vertices.length / 3);
    let problem: Record<string, string | number> | undefined;
    if (vertices.length % 3) problem = { reason: 'vertices' };
    else if (faces.length % 3 || !faces.length) problem = { reason: 'faces' };
    else {
      const bad = faces.find((index) => index < 0 || !Number.isInteger(index) || index >= count);
      if (bad !== undefined) problem = { reason: 'index', index: bad, count };
    }
    if (problem) {
      push('bad_mesh', line, 'mesh', problem);
      refused = true;
    }
  };

  const walk = (kind: Kind, entries: Entry[]) => {
    const numbers = values(kind);
    const allowedWords = words(kind);
    const children = blocks(kind);
    const seen = new Set<string>();
    if (
      (kind.name === 'vector' || kind.name === 'color') &&
      entries.every((item) => item.key === undefined)
    ) {
      if (entries.length !== 3 || entries.some((item) => item.value.kind !== 'number'))
        push('not_a_number', entries[0]?.line ?? 0, '', { value: '{…}' });
      return;
    }
    if (kind.name === 'list') return;
    for (const item of entries) {
      const key = item.key;
      if (key === undefined) {
        if (kind.name !== 'root' || item.value.kind !== 'block')
          push('unexpected_token', item.line, '');
        continue;
      }
      const child = children.find(([name]) => name === key)?.[1];
      const repeatable =
        child !== undefined &&
        (child.name === 'object' || child.name === 'light' || child.name === 'material');
      if (!repeatable && seen.has(key)) {
        push('duplicate_key', item.line, key);
        continue;
      }
      seen.add(key);
      const value: Value = item.value;
      if (value.kind === 'block' && child && !(key === 'scale' && keyframes(value.entries))) {
        if (child.name === 'resolution') resolutionLine ??= item.line;
        if (child.name === 'camera') cameraLine ??= item.line;
        const parts = repeatable ? items(value) : [value.entries];
        for (const part of parts) {
          if (child.name === 'light') lights += 1;
          walk(child, part);
          if (child.name === 'object') object(child.shape, part, item.line);
          if (
            (child.name === 'object' || child.name === 'material') &&
            entry(part, 'reflection') &&
            entry(part, 'reflectivity')
          )
            push('duplicate_reflection', item.line, 'reflectivity');
        }
      } else if (numbers.includes(key)) {
        checkNumber(kind, key, item);
      } else if (allowedWords.some(([name]) => name === key)) {
        const allowed = allowedWords.find(([name]) => name === key)![1];
        if (value.kind === 'word') {
          if (allowed.length && !allowed.includes(value.value)) {
            push(
              'invalid_value',
              item.line,
              key,
              { value: value.value, allowed: allowed.join(', ') },
              suggest(value.value, allowed),
            );
            refused = true;
          }
          if (key === 'name' && kind.name === 'material') materialNames.add(value.value);
          if (key === 'material' && kind.name === 'object')
            materialUses.push([value.value, item.line]);
        } else
          push('invalid_value', item.line, key, {
            value: value.kind === 'number' ? value.value : '{…}',
            allowed: allowed.join(', '),
          });
      } else if (value.kind === 'block' || child) {
        const place = misplaced(key);
        if (UNSUPPORTED.has(key)) push('unsupported', item.line, key);
        else if (place) push('misplaced', item.line, key, { parent: place });
        else
          push(
            'unknown_block',
            item.line,
            key,
            {},
            suggest(
              key,
              children.map(([name]) => name),
            ),
          );
      } else if (UNSUPPORTED.has(key)) {
        push('unsupported', item.line, key);
      } else {
        push(
          'unknown_key',
          item.line,
          key,
          {},
          suggest(key, [
            ...numbers,
            ...allowedWords.map(([name]) => name),
            ...children.map(([name]) => name),
          ]),
        );
      }
    }
  };

  walk(K('root'), root);
  for (const [name, line] of materialUses) {
    if (!materialNames.has(name)) {
      push('unknown_material', line, name, {}, suggest(name, [...materialNames]));
      refused = true;
    }
  }
  const engineEntry = entry(block(root, 'render') || [], 'engine');
  const engine = engineEntry ? evaluate(engineEntry.value, 0) : undefined;
  if (engine !== undefined && engine > ENGINE_VERSION) {
    push('engine_too_new', engineEntry!.line, 'engine', { value: engine, max: ENGINE_VERSION });
    refused = true;
  }

  if (refused) return finish();
  const scene = build(root);
  if (typeof scene === 'string') {
    if (!issues.some((issue) => issue.severity === 'error'))
      push('engine_error', 0, '', { message: scene });
    return finish();
  }
  for (const [centre, radius, line] of spheres) {
    if (dot(sub(centre, scene.origin), scene.forward) + radius <= 0)
      push('behind_camera', line, 'x');
  }
  const planned = plannedResolution(text);
  if (resolutionLine === undefined) push('missing_resolution', cameraLine ?? 0, 'resolution');
  else if (planned.width !== scene.width || planned.height !== scene.height) {
    push('resolution_mismatch', resolutionLine, 'resolution', {
      planned: `${planned.width}×${planned.height}`,
      actual: `${scene.width}×${scene.height}`,
    });
  } else if (scene.width * scene.height > LARGE_PIXELS)
    push('resolution_large', resolutionLine, 'resolution');
  const lit = scene.points > 0 || scene.emitters > 0 || (scene.mode === 'path' && scene.sky > 0);
  if (scene.shapes === scene.areaLights) push('empty_scene', 0);
  if (lights === 0 && !lit) push('dark_scene', 0);
  else if (lights === 0 && scene.mode === 'whitted' && scene.emitters === 0) push('no_light', 0);

  Object.assign(summary, {
    width: scene.width,
    height: scene.height,
    spheres: scene.spheres,
    planes: scene.planes,
    triangles: scene.triangles,
    lights: scene.points + scene.emitters,
    samples: scene.samples,
    mode: scene.mode,
    fieldOfView: number(block(root, 'camera') || [], 'fieldOfView', 55),
  });
  return finish();
}
