import { describe, expect, it } from 'vitest';
import checkCases from './fixtures/check_cases.json';
import parity from './fixtures/preview_parity.json';
import { editorLimits, parseRustFloat, parseSceneText, renderCost, renderSettings, sceneFileName, sceneFromText, sceneToCfg } from '../utils/scene';
import { checkScene } from '../utils/sceneCheck';
import { pickPrimitive, renderScene } from '../utils/sceneRender';
import { SCENE_TEMPLATES, sceneTemplate } from '../utils/sceneTemplates';
import { translate } from '../utils/i18n';

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
    expect(parseSceneText(text).width).toBe(1280);
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
    expect(editorLimits(sceneToCfg(sceneTemplate('demo')))).toEqual([]);
    expect(editorLimits(`${base}primitives : { box = { } sphere = { x = { 0 = 1 9 = 2 } } }`).sort()).toEqual(['animation', 'shapes']);
    expect(editorLimits('camera : { resolution = { width = 8 height = 8 } look_at = { x = 1 } }\nlights : { area = { } }').sort()).toEqual(['camera', 'lights']);
    expect(editorLimits(`${base}materials : { material = { name = v type = glass } }\nprimitives : { sphere = { material = v } }`)).toEqual(['materials']);
    expect(checkScene('render : { }\ncamera : {\n resolution = { width = 8 height = 8 }\n').issues[0]).toMatchObject({ code: 'unbalanced_braces', line: 2 });
  });

  it('opens libconfig lists and named materials', () => {
    const scene = sceneFromText('camera : { resolution = { width = 64; height = 32; }; position = { x = 1; y = 0; z = 0; }; };\n'
      + 'materials : { material = { name = rouge type = diffuse color = { r = 255 g = 0 b = 0 } } }\n'
      + 'primitives : { sphere = ( { x = 5; radius = 1; material = rouge; }, { x = 6; y = 2; } ); };\n'
      + 'lights : { point = ( { x = 2; y = -2; z = 4; } ); };');
    expect(scene.camera.x).toBe(1);
    expect(scene.objects).toHaveLength(2);
    expect(scene.objects[0]).toMatchObject({ material: { color: [255, 0, 0], reflection: 0.04 } });
    expect(scene.lights).toEqual([expect.objectContaining({ x: 2, y: -2, z: 4 })]);
  });

  it('names the file after the project', () => {
    expect(sceneFileName('Rendu intérieur — v4')).toBe('rendu-interieur-v4.cfg');
    expect(sceneFileName('')).toBe('scene.cfg');
  });
});

describe('scene preview', () => {
  it('renders the same bytes as the engine', () => {
    const scene = parseSceneText(parity.scene);
    const expected = Uint8Array.from(atob(parity.rgb_base64), (character) => character.charCodeAt(0));
    expect(renderScene(scene, parity.width, parity.height)).toEqual(expected);
  });

  it('finds the object under the cursor', () => {
    const scene = parseSceneText(sceneToCfg(sceneTemplate('studio')));
    expect(scene.primitives[pickPrimitive(scene, 0.5, 0.5)!]?.kind).toBe('sphere');
    expect(scene.primitives[pickPrimitive(scene, 0.5, 0.97)!]?.kind).toBe('plane');
  });
});
