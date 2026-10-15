// Checks a raytracer `.cfg` before it is sent: the same rules as
// `silicium-raytracer check` (Network/crates/raytracer/src/check.rs), run in
// the browser. `tests/fixtures/check_cases.json` is shared with the engine's
// tests (keep both copies identical).

import { EPSILON, engineTokens, parseRustFloat, parseSceneText } from './scene';

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

export interface SceneReport {
  valid: boolean;
  errors: number;
  warnings: number;
  issues: SceneIssue[];
  scene: { width: number; height: number; spheres: number; planes: number; lights: number; fieldOfView: number };
}

const ERRORS = new Set(['missing_resolution', 'resolution_mismatch', 'not_a_number', 'unbalanced_braces', 'zero_normal', 'use_equals']);

const UNSUPPORTED = new Set(['ambient', 'antialiasing', 'box', 'cone', 'cube', 'cylinder', 'diffuse', 'directional', 'mesh', 'obj', 'refraction', 'scale', 'shear', 'spot', 'texture', 'torus', 'translation', 'transparency', 'triangle']);

const LARGE_PIXELS = 7680 * 4320;

type Kind = 'root' | 'camera' | 'resolution' | 'position' | 'orientation' | 'primitives' | 'sphere' | 'plane' | 'color' | 'lights' | 'point' | 'skipped';

const MATERIAL = ['reflection', 'reflectivity', 'specular', 'shininess', 'r', 'g', 'b'];
const VALUES: Partial<Record<Kind, string[]>> = {
  camera: ['fieldOfView'],
  resolution: ['width', 'height'],
  position: ['x', 'y', 'z'],
  orientation: ['x', 'y', 'z'],
  sphere: ['x', 'y', 'z', 'radius', ...MATERIAL],
  plane: ['x', 'y', 'z', 'normal_x', 'normal_y', 'normal_z', ...MATERIAL],
  color: ['r', 'g', 'b'],
  point: ['x', 'y', 'z', 'intensity', 'r', 'g', 'b'],
};
const BLOCKS: Partial<Record<Kind, string[]>> = {
  root: ['camera', 'primitives', 'lights', 'effects'],
  camera: ['resolution', 'position', 'rotation', 'direction'],
  primitives: ['sphere', 'plane'],
  sphere: ['color'],
  plane: ['color'],
  point: ['color'],
  lights: ['point'],
};
const BLOCK_KIND: Record<string, Kind> = {
  camera: 'camera', resolution: 'resolution', position: 'position', rotation: 'orientation', direction: 'orientation',
  primitives: 'primitives', sphere: 'sphere', plane: 'plane', color: 'color', lights: 'lights', point: 'point', effects: 'skipped',
};

function rangeOf(kind: Kind, key: string): [number, number] | undefined {
  if (key === 'reflection' || key === 'reflectivity') return [0, 0.95];
  if (key === 'specular') return [0, 2];
  if (key === 'shininess') return [1, 512];
  if (key === 'r' || key === 'g' || key === 'b') return [0, 255];
  if (kind === 'camera' && key === 'fieldOfView') return [1, 179];
  if (kind === 'resolution' && (key === 'width' || key === 'height')) return [1, Infinity];
  if (kind === 'point' && key === 'intensity') return [0, Infinity];
  if (kind === 'sphere' && key === 'radius') return [EPSILON, Infinity];
  return undefined;
}

interface Token { text: string; line: number }

/** `word = number` (a word starting with a letter) in a comment. */
function hasAssignment(text: string): boolean {
  return /(^|[^A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*\s*=\s*[-+.0-9]/.test(text);
}

function tokenize(text: string): { tokens: Token[]; commented: number[] } {
  const tokens: Token[] = [];
  const commented: number[] = [];
  const lines = text.split('\n');
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  lines.forEach((raw, index) => {
    const rawLine = raw.endsWith('\r') ? raw.slice(0, -1) : raw;
    const line = index + 1;
    const cuts = [rawLine.indexOf('#'), rawLine.indexOf('//')].filter((position) => position >= 0);
    const cut = cuts.length ? Math.min(...cuts) : -1;
    const code = cut >= 0 ? rawLine.slice(0, cut) : rawLine;
    if (cut >= 0 && hasAssignment(rawLine.slice(cut))) commented.push(line);
    for (const word of engineTokens(code)) tokens.push({ text: word, line });
  });
  return { tokens, commented };
}

function distance(left: string, right: string): number {
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let i = 0; i < left.length; i += 1) {
    const row = [i + 1];
    for (let j = 0; j < right.length; j += 1) {
      row.push(Math.min(previous[j]! + (left[i] === right[j] ? 0 : 1), previous[j + 1]! + 1, row[j]! + 1));
    }
    previous = row;
  }
  return previous[right.length]!;
}

/** Closest known word (case-insensitive edit distance at most 2). */
function suggest(word: string, candidates: string[]): string | undefined {
  let best: { score: number; candidate: string } | undefined;
  for (const candidate of candidates) {
    const score = distance(word.toLowerCase(), candidate.toLowerCase());
    if (score <= 2 && score < candidate.length && (!best || score < best.score)) best = { score, candidate };
  }
  return best?.candidate;
}

interface Frame { kind: Kind; name: string; line: number; values: Map<string, number>; firstCoordinate?: { kind: Kind; line: number } }
const isPunctuation = (text: string) => text === '{' || text === '}' || text === '=' || text === ':' || text === ';';

/** The tile planner's reading of the resolution (`tiles::scene_resolution`). */
export function plannedResolution(text: string): { width: number; height: number } {
  const match = /resolution\s*=\s*\{[^}]*width\s*=\s*(\d+)[^}]*height\s*=\s*(\d+)/i.exec(text);
  if (!match) return { width: 1920, height: 1080 };
  return { width: Math.max(1, Number(match[1])), height: Math.max(1, Number(match[2])) };
}

/** Problems of a scene file, with their lines. */
export function checkScene(text: string): SceneReport {
  const issues: SceneIssue[] = [];
  const push = (code: string, line: number, key = '', params: Record<string, string | number> = {}, suggestion?: string) => {
    issues.push({ severity: ERRORS.has(code) ? 'error' : 'warning', code, line, key, params: { key, ...params }, ...(suggestion ? { suggestion } : {}) });
  };
  const { tokens, commented } = tokenize(text);
  const stack: Frame[] = [{ kind: 'root', name: '', line: 0, values: new Map() }];
  const spans: [number, number][] = [];
  const spheres: { front: number; line: number }[] = [];
  let resolutionLine: number | undefined;
  let cameraLine: number | undefined;
  let lights = 0;
  const value = (frame: Frame, key: string, fallback: number) => frame.values.get(key) ?? fallback;

  const close = (frame: Frame, lastLine: number) => {
    spans.push([frame.line, lastLine]);
    if (frame.kind === 'plane') {
      const normal = [value(frame, 'normal_x', 0), value(frame, 'normal_y', 0), value(frame, 'normal_z', 1)];
      if (Math.sqrt(normal.reduce((sum, item) => sum + item * item, 0)) <= EPSILON) push('zero_normal', frame.line);
    } else if (frame.kind === 'sphere') {
      spheres.push({ front: value(frame, 'x', 0) + value(frame, 'radius', 1), line: frame.line });
    } else if (frame.kind === 'orientation') {
      const [x, y, z] = [value(frame, 'x', 0), value(frame, 'y', 0), value(frame, 'z', 0)];
      const ignored = frame.name === 'rotation' ? x !== 0 || y !== 0 || z !== 0 : y !== 0 || z !== 0 || x <= 0;
      if (ignored) push('camera_orientation_ignored', frame.line, frame.name);
    } else if (frame.kind === 'camera') {
      if (frame.firstCoordinate?.kind === 'orientation') push('camera_position_shadowed', frame.firstCoordinate.line, 'position');
    } else if (frame.kind === 'resolution') {
      const [width, height] = [value(frame, 'width', 0), value(frame, 'height', 0)];
      if (width >= 1 && height >= 1 && width * height > LARGE_PIXELS) push('resolution_large', frame.line, 'resolution');
    }
  };

  const assign = (key: string, raw: string, line: number) => {
    const frame = stack[stack.length - 1]!;
    const kind = frame.kind;
    if (kind === 'skipped') return;
    const known = VALUES[kind] || [];
    if (!known.includes(key)) {
      if (UNSUPPORTED.has(key)) push('unsupported', line, key);
      else push('unknown_key', line, key, {}, suggest(key, [...known, ...(BLOCKS[kind] || [])]));
      return;
    }
    const number = parseRustFloat(raw);
    if (number === undefined) { push('not_a_number', line, key, { value: raw }); return; }
    if ((kind === 'sphere' || kind === 'plane') && ((key === 'reflection' && frame.values.has('reflectivity')) || (key === 'reflectivity' && frame.values.has('reflection')))) {
      push('duplicate_reflection', line, key);
    }
    if (frame.values.has(key)) { push('duplicate_key', line, key); return; }
    frame.values.set(key, number);
    const range = rangeOf(kind, key);
    if (range && !(number >= range[0] && number <= range[1])) push('out_of_range', line, key, { value: number, min: range[0], max: range[1] === Infinity ? '' : range[1] });
    if (key === 'x' || key === 'y' || key === 'z') {
      const camera = [...stack].reverse().find((item) => item.kind === 'camera');
      if (camera && !camera.firstCoordinate) camera.firstCoordinate = { kind, line };
    }
  };

  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index]!;
    const next = tokens[index + 1]?.text;
    const after = tokens[index + 2];
    if (token.text === '}') {
      if (stack.length === 1) push('unbalanced_braces', token.line, '', { extra: 1 });
      else close(stack.pop()!, token.line);
      index += 1;
      continue;
    }
    if (isPunctuation(token.text)) { index += 1; continue; }
    const parent = stack[stack.length - 1]!.kind;
    if ((next === '=' || next === ':') && after?.text === '{') {
      const name = token.text;
      let kind: Kind;
      if (parent === 'skipped') kind = 'skipped';
      else if ((BLOCKS[parent] || []).includes(name)) kind = BLOCK_KIND[name] || 'skipped';
      else if (UNSUPPORTED.has(name)) { push('unsupported', token.line, name); kind = 'skipped'; }
      else if (name === 'sphere' || name === 'plane' || name === 'point') { push('misplaced', token.line, name, { parent: name === 'point' ? 'lights' : 'primitives' }); kind = name; }
      else { push('unknown_block', token.line, name, {}, suggest(name, BLOCKS[parent] || [])); kind = 'skipped'; }
      if (kind === 'resolution') resolutionLine ??= token.line;
      if (kind === 'camera') cameraLine ??= token.line;
      if (kind === 'point') lights += 1;
      stack.push({ kind, name, line: token.line, values: new Map() });
      index += 3;
      continue;
    }
    if ((next === '=' || next === ':') && after && !isPunctuation(after.text)) {
      if (next === ':') { if (parent !== 'skipped') push('use_equals', token.line, token.text, { value: after.text }); }
      else assign(token.text, after.text, token.line);
      index += 3;
      continue;
    }
    if (parent !== 'skipped' && parseRustFloat(token.text) === undefined) push('unexpected_token', token.line, token.text);
    index += 1;
  }
  while (stack.length > 1) {
    const frame = stack.pop()!;
    push('unbalanced_braces', frame.line, frame.name);
    close(frame, Number.MAX_SAFE_INTEGER);
  }
  for (const line of commented) {
    if (spans.some(([first, last]) => line >= first && line <= last)) push('comment_assignment', line);
  }

  const scene = parseSceneText(text);
  const planned = plannedResolution(text);
  if (resolutionLine === undefined) push('missing_resolution', cameraLine ?? 0, 'resolution');
  else if (planned.width !== scene.width || planned.height !== scene.height) {
    push('resolution_mismatch', resolutionLine, 'resolution', { planned: `${planned.width}×${planned.height}`, actual: `${scene.width}×${scene.height}` });
  }
  if (!scene.primitives.length) push('empty_scene', 0);
  if (!lights) push('no_light', 0);
  for (const sphere of spheres) if (sphere.front <= scene.camera[0]) push('behind_camera', sphere.line, 'x');

  issues.sort((a, b) => Number(a.line === 0) - Number(b.line === 0) || a.line - b.line);
  const errors = issues.filter((issue) => issue.severity === 'error').length;
  const sphereCount = scene.primitives.filter((primitive) => primitive.kind === 'sphere').length;
  return {
    valid: errors === 0,
    errors,
    warnings: issues.length - errors,
    issues,
    scene: { width: scene.width, height: scene.height, spheres: sphereCount, planes: scene.primitives.length - sphereCount, lights: scene.lights.length, fieldOfView: scene.fov },
  };
}
