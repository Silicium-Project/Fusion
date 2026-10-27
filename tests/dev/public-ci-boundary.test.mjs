import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { run, root } from '../../tools/lib/process.mjs';

test('public Workbench CI has no private-repository authorization branch', () => {
  const workflow = readFileSync(`${root}/.github/workflows/ci.yml`, 'utf8');
  const capabilities = JSON.parse(run(['node', 'tools/dev.mjs', 'capabilities', '--json']).stdout);

  assert.doesNotMatch(workflow, /SILICIUM_PRIVATE_CI_WINDOW|github\.event\.repository\.private/);
  assert.ok(!capabilities.commands.some((entry) => entry.command === 'ci authorize-private'));
  assert.equal(existsSync(`${root}/tools/admin/qualify-private.mjs`), false);
});

test('private source qualification remains isolated in the Integration workflow', () => {
  const guide = readFileSync(`${root}/docs/operations/multi-repo-ci.md`, 'utf8');
  const commands = readFileSync(`${root}/docs/development/commands.md`, 'utf8');

  assert.match(guide, /SILICIUM_INTEGRATION_ENABLED=1/);
  assert.match(commands, /Full private integration/);
  assert.match(commands, /github\.com\/Silicium-Project\/Integration/);
});
