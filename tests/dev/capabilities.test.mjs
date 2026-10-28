import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { run, readJson, root } from '../../tools/lib/process.mjs';
import { publicMetadata } from '../../tools/lib/github.mjs';
import { workspaceConfig } from '../../tools/lib/workspace.mjs';
test('capabilities lists actual commands, suites and unimplemented runtime delivery', () => {
  const result = JSON.parse(run(['node', 'tools/dev.mjs', 'capabilities', '--json']).stdout);
  assert.equal(result.schema_version, 1);
  assert.equal(result.features.worker_rolling_update, 'planned');
  assert.equal(result.features.project_automation, 'available');
  assert.equal(
    result.commands.find((command) => command.command === 'issue start').availability,
    'configuration_required',
  );
  for (const name of [
    'doctor',
    'ci plan',
    'ci policy',
    'ci public-evidence',
    'test',
    'issue start',
    'issue accept',
    'deploy request',
  ])
    assert.ok(result.commands.some((c) => c.command === name));
  assert.ok(!result.commands.some((c) => c.command === 'ci authorize-private'));
  assert.deepEqual(result.suites, Object.keys(readJson(root + '/tools/config/lanes.json').suites));
});
test('contract catalog refers to real definitions and registered suites', () => {
  const catalog = readJson(root + '/contracts/catalog.json'),
    lanes = readJson(root + '/tools/config/lanes.json');
  for (const c of catalog.contracts) {
    assert.ok(
      existsSync(root + '/' + c.definition) ||
        Object.values(workspaceConfig().components).some((component) =>
          c.definition.startsWith(component.path + '/'),
        ),
      c.id,
    );
    for (const s of c.validation_suites) assert.ok(lanes.suites[s], s);
  }
});
test('diagnostic metadata cannot persist temporary GitHub clone credentials', () => {
  const safe = publicMetadata({
    repo: { temp_clone_token: 'fixture', name: 'Fusion' },
    access_token: 'fixture',
    jobs: [],
  });
  assert.deepEqual(safe, { repo: { name: 'Fusion' }, jobs: [] });
});
