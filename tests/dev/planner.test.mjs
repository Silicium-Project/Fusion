import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parseChanges,
  route,
  registry,
  combinePlans,
  splitMatrix,
} from '../../tools/lib/planner.mjs';

test('rename and copy include old and new paths, with spaces preserved', () => {
  assert.deepEqual(
    parseChanges('R100\0apps/web/old name.ts\0contracts/new name.ts\0D\0network/old.rs\0'),
    ['apps/web/old name.ts', 'contracts/new name.ts', 'network/old.rs'],
  );
});
test('truncated change output fails closed', () =>
  assert.throws(() => parseChanges('R100\0one\0')));
test('documentation does not compile applications', () =>
  assert.deepEqual(route(['docs/ai/README.md']).suites, [
    'docs',
    'powershell',
    'security',
    'tooling',
  ]));
test('unknown paths require the entire registered matrix', () =>
  assert.equal(
    route(['unexpected.file']).suites.length,
    Object.values(registry().suites).filter((suite) => suite.tier === 'pr').length,
  ));
test('network changes qualify API, web and desktop consumers', () => {
  const p = route(['network/crates/node-core/src/lib.rs']);
  for (const c of ['network', 'api', 'web', 'node', 'infra']) assert.ok(p.components.includes(c));
});
test('contract, policy and lockfile changes cannot avoid their consumers', () => {
  for (const path of [
    'contracts/http/api.openapi.yaml',
    'tools/config/lanes.json',
    '.github/workflows/ci.yml',
  ])
    assert.equal(route([path]).full, true);
  assert.ok(route(['apps/web/package-lock.json']).suites.includes('web'));
});
test('removed obligations remain mandatory until separately migrated', () =>
  assert.throws(() => combinePlans({ suites: ['docs'] }, { suites: ['deleted-lane'] })));
test('deleted and renamed shared contracts trigger all suites', () =>
  assert.equal(
    route(parseChanges('R100\0contracts/schema.json\0docs/archive/schema.json\0')).full,
    true,
  ));

test('quick feedback uses separate lanes and docs needs no integration build', () => {
  const config = registry(),
    suites = route(['docs/ai/README.md']).suites;
  const phases = splitMatrix({
    matrix: { include: suites.map((suite) => ({ suite, runner: config.suites[suite].runner })) },
  });
  assert.equal(phases.integration_count, 0);
  assert.equal(phases.quick.include.length, suites.length);
});

test('a PR cannot silently remove the test command from an unchanged suite', () => {
  const step = { command: ['node', 'unit'], cwd: '.', kind: 'test', env: {} };
  assert.throws(
    () =>
      combinePlans(
        { suites: ['tooling'], requirements: { tooling: [] }, head_sha: 'a'.repeat(40) },
        { suites: ['tooling'], requirements: { tooling: [step] } },
      ),
    /obligations/,
  );
});

test('Solana program and SDK changes qualify the runtime payment consumers', () => {
  for (const path of ['chain/solana/programs/solana-layer/src/lib.rs', 'chain/sdk/src/index.ts']) {
    const plan = route([path]);
    for (const suite of [
      'network',
      'network-integration',
      'api',
      'web',
      'node-native',
      'node-windows',
    ])
      assert.ok(plan.suites.includes(suite), `${path}: ${suite}`);
  }
});
