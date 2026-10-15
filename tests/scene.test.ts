import { describe, expect, it } from 'vitest';
import checkCases from './fixtures/check_cases.json';
import parity from './fixtures/preview_parity.json';
import { parseRustFloat, parseSceneText, sceneFileName, sceneFromText, sceneToCfg } from '../utils/scene';
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
    codes.add('misplaced').add('unexpected_token').add('resolution_large');
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
