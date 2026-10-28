import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parseChanges,
  route,
  registry,
  combinePlans,
  splitMatrix,
  makePlan,
  scopeSelection,
} from '../../tools/lib/planner.mjs';
import { workspaceConfig } from '../../tools/lib/workspace.mjs';

test('rename and copy include old and new paths, with spaces preserved', () => {
  assert.deepEqual(
    parseChanges('R100\0apps/web/old name.ts\0contracts/new name.ts\0D\0network/old.rs\0'),
    ['apps/web/old name.ts', 'contracts/new name.ts', 'network/old.rs'],
  );
});
test('truncated change output fails closed', () =>
  assert.throws(() => parseChanges('R100\0one\0')));
test('documentation routes only the documentation suite', () =>
  assert.deepEqual(route(['docs/ai/README.md']).suites, ['docs']));
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

test('qualification plans carry each suite source list for least-privilege private fetches', () => {
  const plan = makePlan({ paths: [], scope: 'integration' });
  const suites = Object.fromEntries(plan.matrix.include.map((row) => [row.suite, row.sources]));
  assert.deepEqual(suites['workspace-sources'], ['api', 'web', 'node', 'network', 'solana']);
  assert.deepEqual(suites.network, ['network']);
  assert.deepEqual(suites['network-integration'], ['network']);
  assert.deepEqual(suites['network-contract'], ['network', 'solana']);
  assert.deepEqual(suites.infrastructure, ['network', 'solana']);
  assert.deepEqual(suites.tooling, []);
});

test('Network-to-Solana contracts run only in the cross-repository composition', () => {
  const localPytest = registry().suites['network-integration'].steps.find(
    (step) =>
      step.command[0] === 'python3' && step.command[1] === '-m' && step.command[2] === 'pytest',
  );
  assert.ok(localPytest.command.includes('--ignore=tests/test_solana_integration_contract.py'));
  const component = makePlan({ paths: [], scope: 'component:network' });
  assert.ok(!component.suites.includes('network-contract'));
  const integration = makePlan({ paths: [], scope: 'integration' });
  assert.ok(integration.suites.includes('network-contract'));
  const row = integration.matrix.include.find((entry) => entry.suite === 'network-contract');
  assert.deepEqual(row.sources, ['network', 'solana']);
  const publicPlan = makePlan({ paths: [], scope: 'public' });
  assert.ok(!publicPlan.suites.includes('network-contract'));
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

test('public plans target changed suites and expand conservatively for policy or unknown paths', () => {
  const config = registry();
  const workspace = workspaceConfig();
  const publicPlan = (paths) =>
    scopeSelection(route(paths, config), 'public', config, workspace).suites;
  assert.deepEqual(publicPlan(['docs/ai/README.md']), ['docs']);
  assert.deepEqual(publicPlan(['tools/config/lanes.json']), [...workspace.public_suites].sort());
  assert.deepEqual(publicPlan(['unexpected.file']), [...workspace.public_suites].sort());
  assert.deepEqual(publicPlan([]), [...workspace.public_suites].sort());
});

test('component plans run only their own suites and defer only other private components', () => {
  const plan = makePlan({ paths: ['tools/dev.mjs'], scope: 'component:api' });
  assert.deepEqual(plan.suites, ['api']);
  assert.ok(!plan.deferred_suites.some((entry) => ['docs', 'tooling'].includes(entry.suite)));
  assert.equal(
    plan.not_applicable.find((entry) => entry.suite === 'docs').reason,
    'public policy is checked at the exact pinned Workbench SHA',
  );
  assert.ok(plan.deferred_suites.some((entry) => entry.suite === 'web'));
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
      'infrastructure',
    ])
      assert.ok(plan.suites.includes(suite), `${path}: ${suite}`);
  }
});
