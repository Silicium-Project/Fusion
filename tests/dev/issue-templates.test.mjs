import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { root } from '../../tools/lib/process.mjs';

const templates = `${root}/.github/ISSUE_TEMPLATE`;

test('issue forms use supported types, the shared Project and unique field IDs', () => {
  const forms = readdirSync(templates).filter(
    (name) => name.endsWith('.yml') && name !== 'config.yml',
  );
  assert.ok(forms.includes('01-bug.yml'));
  assert.ok(forms.includes('02-feature.yml'));
  assert.ok(forms.includes('03-investigation.yml'));
  assert.ok(forms.includes('04-decision.yml'));
  assert.ok(forms.includes('task.yml'));

  for (const name of forms) {
    const source = readFileSync(`${templates}/${name}`, 'utf8');
    assert.match(source, /^type: (Bug|Feature|Task)$/m, name);
    assert.match(source, /^projects:\r?\n\s*- Silicium-Project\/12$/m, name);
    const ids = [...source.matchAll(/^\s+id:\s*([A-Za-z0-9_-]+)\s*$/gm)].map((match) => match[1]);
    assert.ok(ids.length > 0, `${name} must define fields`);
    assert.equal(new Set(ids).size, ids.length, `${name} field IDs must be unique`);
  }
});

test('public intake keeps HOLD details private and uses current Workbench links', () => {
  const decision = readFileSync(`${templates}/04-decision.yml`, 'utf8');
  const config = readFileSync(`${templates}/config.yml`, 'utf8');
  const pullRequest = readFileSync(`${root}/.github/pull_request_template.md`, 'utf8');

  assert.match(decision, /planning-private/);
  assert.match(config, /orgs\/Silicium-Project\/projects\/12/);
  assert.match(config, /CONTRIBUTING\.md/);
  assert.match(pullRequest, /Silicium-Project\/Workbench\/issues\/NUMERO/);
  assert.match(pullRequest, /Silicium-Project\/Workbench\/issues\/208/);
  assert.doesNotMatch(pullRequest, /github\.com\/Silicium-Project\/Fusion/);
});
