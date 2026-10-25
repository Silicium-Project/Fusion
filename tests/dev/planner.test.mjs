import test from 'node:test';
import assert from 'node:assert/strict';
import { parseChanges, route, registry, combinePlans } from '../../tools/lib/planner.mjs';

test('rename and copy include old and new paths, with spaces preserved', () => {
  assert.deepEqual(parseChanges('R100\0apps/web/old name.ts\0contracts/new name.ts\0D\0network/old.rs\0'), ['apps/web/old name.ts','contracts/new name.ts','network/old.rs']);
});
test('truncated change output fails closed', () => assert.throws(() => parseChanges('R100\0one\0')));
test('documentation does not compile applications', () => assert.deepEqual(route(['docs/ai/README.md']).suites, ['docs','security','tooling']));
test('unknown paths require the entire registered matrix', () => assert.equal(route(['unexpected.file']).suites.length, Object.keys(registry().suites).length));
test('network changes qualify API, web and desktop consumers', () => {
  const p = route(['network/crates/node-core/src/lib.rs']);
  for (const c of ['network','api','web','node','infra']) assert.ok(p.components.includes(c));
});
test('contract, policy and lockfile changes cannot avoid their consumers', () => {
  for (const path of ['contracts/http/api.openapi.yaml','tools/config/lanes.json','.github/workflows/ci.yml']) assert.equal(route([path]).full, true);
  assert.ok(route(['apps/web/package-lock.json']).suites.includes('web'));
});
test('removed obligations remain mandatory until separately migrated', () => assert.throws(() => combinePlans({ suites: ['docs'] }, { suites: ['deleted-lane'] })));
test('deleted and renamed shared contracts trigger all suites', () => assert.equal(route(parseChanges('R100\0contracts/schema.json\0docs/archive/schema.json\0')).full, true));
