import { describe, expect, it } from 'vitest';
import checkCases from './fixtures/check_cases.json';
import { readFileSync } from 'node:fs';
import parity from './fixtures/preview_parity.json';
import engineParity from './fixtures/engine_parity.json';
import { editorLimits, materialPreset, renderCost, renderSettings, sceneFileName, sceneFromText, sceneToCfg, type SceneMesh } from '../utils/scene';
import { parseRustFloat } from '../utils/sceneSyntax';
import { checkScene } from '../utils/sceneCheck';
import { buildScene, pickShape, renderText } from '../utils/engine';
import { builtinModel, BUILTIN_MODELS, fit, parseObj, yUpToZUp } from '../utils/engine/models';
import { runPreview, type PreviewReply } from '../utils/engine/progressive';
import { SCENE_TEMPLATES, SHOWCASE_TITLE, sceneTemplate } from '../utils/sceneTemplates';
import { translate } from '../utils/i18n';

/** Share of pixels that differ by more than `tolerance` between two RGBA images. */
function difference(a: Uint8ClampedArray, b: Uint8ClampedArray, tolerance = 8): number {
  let differ = 0;
  for (let i = 0; i < a.length; i += 4) {
    if (Math.max(Math.abs(a[i]! - b[i]!), Math.abs(a[i + 1]! - b[i + 1]!), Math.abs(a[i + 2]! - b[i + 2]!)) > tolerance) differ += 1;
  }
  return differ / (a.length / 4);
}

interface ExpectedIssue { code: string; line: number; key?: string; suggestion?: string }

describe('scene check (same cases as `silicium-raytracer check`)', () => {
  for (const testCase of checkCases.cases as { name: string; lines: string[]; expected: ExpectedIssue[] }[]) {
    it(testCase.name, () => {
      const report = checkScene(testCase.lines.join('\n'));
      expect(report.issues.map((issue) => `${issue.code}@${issue.line}`).sort()).toEqual(testCase.expected.map((item) => `${item.code}@${item.line}`).sort());
      for (const item of testCase.expected) {
        const found = report.issues.find((issue) => issue.code === item.code && issue.line === item.line && (!item.key || issue.key === item.key));
        expect(found, JSON.stringify(item)).toBeDefined();
        if (item.suggestion) expect(found?.suggestion).toBe(item.suggestion);
      }
      expect(report.valid).toBe(!report.issues.some((issue) => issue.severity === 'error'));
    });
  }

  it('has a message for every issue it reports', () => {
    const codes = new Set(checkCases.cases.flatMap((testCase) => checkScene(testCase.lines.join('\n')).issues.map((issue) => issue.code)));
    for (const code of ['misplaced', 'unexpected_token', 'resolution_large', 'syntax_error', 'invalid_value', 'unknown_material', 'engine_too_new', 'engine_error', 'bad_mesh', 'dark_scene']) codes.add(code);
    for (const code of codes) expect(translate(`sceneCheck.codes.${code}`, { key: 'x', min: 0, max: 1, value: 2 })).not.toContain('sceneCheck.');
  });

  it('accepts Windows line endings', () => {
    const report = checkScene(checkCases.cases[0]!.lines.join('\r\n'));
    expect(report.issues).toEqual([]);
  });
});

describe('scene editor model', () => {
  it('writes templates the engine reads without any warning', () => {
    for (const name of SCENE_TEMPLATES) {
      const text = sceneToCfg(sceneTemplate(name), `Modèle ${name}`);
      expect(checkScene(text).issues, name).toEqual([]);
    }
  });

  it('reads back what it writes', () => {
    for (const name of SCENE_TEMPLATES) {
      const text = sceneToCfg(sceneTemplate(name));
      expect(sceneToCfg(sceneFromText(text))).toBe(text);
    }
  });

  it('keeps titles on one comment line outside the blocks', () => {
    const text = sceneToCfg(sceneTemplate('blank'), 'Rendu\nwidth = 5');
    expect(text.split('\n')[0]).toBe('# Rendu width = 5');
    expect(buildScene(text).width).toBe(1280);
  });

  it('opens a hand-written file with what the engine reads from it', () => {
    const scene = sceneFromText('camera : { resolution = { width = 64 height = 32 } };\nprimitives : { sphere = { x = 5 radius = 2 reflection = 3 } };');
    expect(scene.objects).toHaveLength(1);
    expect(scene.objects[0]).toMatchObject({ kind: 'sphere', x: 5, radius: 2, material: { reflection: 0.95 } });
    expect(scene.lights).toEqual([expect.objectContaining({ x: 4, y: 0, z: 5, intensity: 450 })]);
  });

  it('parses numbers like Rust', () => {
    expect(parseRustFloat('1.5')).toBe(1.5);
    expect(parseRustFloat('-2')).toBe(-2);
    expect(parseRustFloat('.5')).toBe(0.5);
    expect(parseRustFloat('3.')).toBe(3);
    expect(parseRustFloat('1e3')).toBe(1000);
    expect(parseRustFloat('0x10')).toBeUndefined();
    expect(parseRustFloat('big')).toBeUndefined();
    expect(parseRustFloat('')).toBeUndefined();
  });

  it('writes a render block only for the finer qualities', () => {
    const draft = sceneToCfg(sceneTemplate('mirrors'));
    expect(draft).not.toContain('render :');
    expect(renderSettings(draft)).toEqual({ samples: 1, mode: 'whitted' });
    for (const quality of ['smooth', 'photo'] as const) {
      const text = sceneToCfg({ ...sceneTemplate('mirrors'), quality });
      expect(renderSettings(text)).toEqual(quality === 'photo' ? { samples: 256, mode: 'path' } : { samples: 16, mode: 'whitted' });
      const report = checkScene(text);
      expect(report.issues).toEqual([]);
      expect(report.scene).toMatchObject({ width: 1280, height: 720, spheres: 4, planes: 1, samples: quality === 'photo' ? 256 : 16 });
      expect(sceneToCfg(sceneFromText(text))).toBe(text);
    }
    const photo = sceneToCfg({ ...sceneTemplate('mirrors'), quality: 'photo' });
    expect(photo).toContain('type = metal roughness = 0');
    expect(renderCost({ width: 100, height: 100, quality: 'photo' })).toBe(100 * 100 * 256 * 4);
  });

  it('tells what the editor cannot show', () => {
    const base = 'camera : { resolution = { width = 8 height = 8 } }\n';
    for (const name of SCENE_TEMPLATES) expect(editorLimits(sceneToCfg(sceneTemplate(name))), name).toEqual([]);
    expect(editorLimits(`${base}primitives : { box = { } sphere = { x = { 0 = 1 9 = 2 } } }`)).toEqual(['animation']);
    expect(editorLimits('camera : { resolution = { width = 8 height = 8 } look_at = { x = 1 } }\nlights : { area = { } }')).toEqual([]);
    expect(editorLimits(`${base}materials : { material = { name = v type = glass } }\nprimitives : { sphere = { material = v } }`)).toEqual([]);
    expect(editorLimits('camera : { resolution = { width = 8 height = 8 } up = { x = 1 z = 0 } }')).toEqual(['camera']);
    expect(checkScene('render : { }\ncamera : {\n resolution = { width = 8 height = 8 }\n').issues[0]).toMatchObject({ code: 'unbalanced_braces', line: 2 });
  });

  it('opens libconfig lists and named materials', () => {
    const scene = sceneFromText('camera : { resolution = { width = 64; height = 32; }; position = { x = 1; y = 0; z = 0; }; };\n'
      + 'materials : { material = { name = rouge type = diffuse color = { r = 255 g = 0 b = 0 } } }\n'
      + 'primitives : { sphere = ( { x = 5; radius = 1; material = rouge; }, { x = 6; y = 2; } ); };\n'
      + 'lights : { point = ( { x = 2; y = -2; z = 4; } ); };');
    expect(scene.camera.x).toBe(1);
    expect(scene.objects).toHaveLength(2);
    expect(scene.objects[0]).toMatchObject({ material: { type: 'diffuse', color: [255, 0, 0] } });
    expect(materialPreset(scene.objects[0]!.material)).toBe('matte');
    expect(scene.lights).toEqual([expect.objectContaining({ x: 2, y: -2, z: 4 })]);
  });

  it('opens every shape, material, light and camera of the engine and renders them the same', () => {
    const text = [
      'render : { exposure = 1.2 sky = 0.7 }',
      'camera : { resolution = { width = 96 height = 60 } position = { x = -1 y = 1 z = 1.5 } look_at = { x = 5 y = 0 z = 0 } fieldOfView = 50 }',
      'materials : { material = { name = verre type = glass ior = 1.4 color = { r = 230 g = 245 b = 255 } } }',
      'primitives : {',
      '  plane = { normal = { x = 0 y = 0 z = 1 } z = -1 type = diffuse }',
      '  sphere = { x = 5 radius = 0.9 material = verre }',
      '  sphere = { radius = 0.5 translate = { x = 6 y = 2 } scale = 1.5 type = metal roughness = 0 }',
      '  box = { min = { x = 0 y = 0 z = -1 } max = { x = 1 y = 2 z = 0 } translate = { x = 6 y = -2.5 } rotate = { z = 30 } color = { r = 200 g = 80 b = 80 } }',
      '  quad = { translate = { x = 9 z = 1 } scale = { y = 3 z = 2 } rotate = { z = 15 } type = emissive strength = 2 }',
      '  quad = { corner = { x = 8 y = 3 z = -1 } u = { x = 0 y = 1 z = 0 } v = { x = 0 y = 0 z = 1.5 } }',
      '  triangle = { a = { x = 4 y = 1.5 z = -1 } b = { x = 4 y = 2.5 z = -1 } c = { x = 4 y = 2 z = 0 } }',
      '  mesh = { vertices = { 0 0 0  1 0 0  0 1 0  0 0 1 } faces = { 0 2 1  0 1 3  1 2 3  0 3 2 } translate = { x = 3.5 y = -0.8 z = -1 } scale = { x = 0.6 y = 0.6 z = 1.2 } rotate = { z = 45 } }',
      '}',
      'lights : { point = { x = 2 y = 3 z = 5 } area = { x = 2 y = -3 z = 4 radius = 0.4 intensity = 250 } }',
    ].join('\n');
    const scene = sceneFromText(text);
    expect(scene.objects.map((item) => item.kind)).toEqual(['plane', 'sphere', 'sphere', 'box', 'panel', 'mesh', 'mesh', 'mesh']);
    expect(scene.objects[1]).toMatchObject({ material: { type: 'glass', ior: 1.4 } });
    expect(scene.objects[3]).toMatchObject({ kind: 'box', size: [1, 2, 1], rotation: [0, 0, 30] });
    expect(scene.objects[4]).toMatchObject({ kind: 'panel', width: 3, height: 2, x: 9, z: 1, material: { type: 'emissive', strength: 2 } });
    expect(scene.lights.map((light) => light.kind)).toEqual(['point', 'area']);
    expect(scene.camera.pitch).toBeLessThan(0);
    expect(scene).toMatchObject({ sky: 0.7, exposure: 1.2 });
    const written = sceneToCfg(scene);
    expect(checkScene(written).issues).toEqual([]);
    expect(sceneToCfg(sceneFromText(written))).toBe(written);
    // Same picture (up to the rounding of the written numbers).
    expect(difference(renderText(text, 96, 60), renderText(written, 96, 60))).toBeLessThan(0.01);
  });

  it('turns the camera like the engine', () => {
    for (const [yaw, pitch] of [[30, 0], [-45, 20], [10, -35]] as const) {
      const scene = { ...sceneTemplate('blank'), width: 64, height: 40 };
      scene.camera = { ...scene.camera, yaw, pitch };
      const text = sceneToCfg(scene);
      expect(sceneFromText(text).camera).toMatchObject({ yaw, pitch });
      const forward = buildScene(text).camera.forward;
      const radians = Math.PI / 180;
      expect(forward.z).toBeCloseTo(Math.sin(pitch * radians), 6);
      // Turning right goes towards -y.
      expect(Math.sign(forward.y)).toBe(Math.sign(-yaw));
    }
  });

  it('names the file after the project', () => {
    expect(sceneFileName('Rendu intérieur — v4')).toBe('rendu-interieur-v4.cfg');
    expect(sceneFileName('')).toBe('scene.cfg');
  });
});

describe('scene preview (browser engine)', () => {
  const rgb = (rgba: Uint8ClampedArray) => Uint8Array.from(rgba.filter((_, index) => index % 4 !== 3));

  it('renders the same bytes as the network engine', () => {
    for (const testCase of [{ name: 'demo', ...parity }, ...engineParity.cases]) {
      const expected = Uint8Array.from(atob(testCase.rgb_base64), (character) => character.charCodeAt(0));
      expect(rgb(renderText(testCase.scene, testCase.width, testCase.height)), testCase.name).toEqual(expected);
    }
  });

  it('finds the object (or light) under the cursor', () => {
    const scene = buildScene(sceneToCfg(sceneTemplate('studio')));
    expect(scene.shapeSource[pickShape(scene, 0.5, 0.5)!]).toBe(0);
    expect(scene.shapeSource[pickShape(scene, 0.5, 0.97)!]).toBe(1);
    const showcase = sceneTemplate('showcase');
    const built = buildScene(sceneToCfg({ ...showcase, lights: [{ ...showcase.lights[0]!, kind: 'area', x: 5, y: 0, z: 0.9, radius: 0.3 }] }));
    // Objects come first, then the lights.
    expect(built.shapeSource[pickShape(built, 0.5, 0.42)!]).toBe(showcase.objects.length);
  });

  it('refines the image pass after pass, after a quick small one', async () => {
    const replies: PreviewReply[] = [];
    await runPreview({ id: 1, text: sceneToCfg(sceneTemplate('cornell')), width: 150, height: 150, target: 3, quick: true }, (reply) => replies.push(reply), () => true);
    expect(replies.map((reply) => reply.kind === 'image' && [reply.width, reply.samples, reply.quick])).toEqual([[50, 1, true], [150, 1, false], [150, 2, false], [150, 3, false]]);
    const errors: PreviewReply[] = [];
    await runPreview({ id: 2, text: 'render : { mode = magic }', width: 10, height: 10, target: 1 }, (reply) => errors.push(reply), () => true);
    expect(errors[0]).toMatchObject({ kind: 'error' });
  });

  it('path traces the same picture as the network (on average)', () => {
    // Brightness of a small Cornell box at 32 rays per pixel, against the engine's.
    const text = sceneToCfg({ ...sceneTemplate('cornell'), width: 24, height: 24 }).replace('samples = 256', 'samples = 32');
    const mean = (pixels: ArrayLike<number>, step: number) => {
      let sum = 0;
      for (let i = 0; i < pixels.length; i += step) sum += pixels[i]! + pixels[i + 1]! + pixels[i + 2]!;
      return sum / (pixels.length / step) / 3;
    };
    expect(Math.abs(mean(renderText(text, 24, 24, 32), 4) - CORNELL_MEAN)).toBeLessThan(3);
  });
});

/** Mean byte of the 24 × 24 Cornell box (32 rays per pixel) rendered by `silicium-raytracer`. */
const CORNELL_MEAN = 122.96;

describe('3D models', () => {
  it('reads OBJ files like the engine', () => {
    const model = parseObj('# cube face\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1/1/1 2/2/2 3/3/3 4/4/4\nf -4 -3 -2\n');
    expect(model.vertices).toHaveLength(12);
    expect(model.faces).toEqual([0, 1, 2, 0, 2, 3, 0, 1, 2]);
    expect(() => parseObj('v 0 0 0\nf 1 2 3\n')).toThrow();
    expect(fit(parseObj('v 0 0 0\nv 4 0 0\nv 0 2 1\nf 1 2 3\n'), 2).vertices.slice(3, 6)).toEqual([1, -0.5, 0]);
    expect(yUpToZUp({ vertices: [1, 2, 3], faces: [] }).vertices).toEqual([1, -3, 2]);
  });

  it('builds closed models resting on the floor', () => {
    for (const name of BUILTIN_MODELS) {
      const model = builtinModel(name);
      const z = model.vertices.filter((_, index) => index % 3 === 2);
      expect(Math.min(...z), name).toBeCloseTo(0, 5);
      expect(Math.max(...model.faces), name).toBeLessThan(model.vertices.length / 3);
      const mesh: Partial<SceneMesh> = model;
      expect(mesh.faces!.length % 3).toBe(0);
    }
  });
});

describe('job types page example', () => {
  it('is the showcase template, valid for the engine', () => {
    const example = readFileSync('public/examples/silicium-demo-scene.cfg', 'utf8');
    expect(example).toBe(sceneToCfg(sceneTemplate('showcase'), SHOWCASE_TITLE));
    const report = checkScene(example);
    expect(report.issues).toEqual([]);
    expect(report.scene).toMatchObject({ width: 1280, height: 720, mode: 'path', samples: 256 });
  });
});
