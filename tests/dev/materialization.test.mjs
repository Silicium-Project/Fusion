import test from 'node:test';
import assert from 'node:assert/strict';
import { registry } from '../../tools/lib/planner.mjs';
import { workspaceConfig } from '../../tools/lib/workspace.mjs';
import { sourcesForSuite } from '../../tools/lib/materialization.mjs';

const config = workspaceConfig();
const suites = registry().suites;

test('release materialization includes every pinned private source exactly once', () => {
  const sources = sourcesForSuite('release', config, suites);
  assert.deepEqual([...sources].sort(), Object.keys(config.components).sort());
  assert.equal(new Set(sources).size, sources.length);
});

test('registered suites materialize only their declared component sources', () => {
  for (const [id, suite] of Object.entries(suites)) {
    if (!suite.sources?.length) continue;
    assert.deepEqual(sourcesForSuite(id, config, suites), [...new Set(suite.sources)]);
  }
});

test('unknown, source-free, or undeclared suites cannot materialize', () => {
  assert.throws(() => sourcesForSuite('missing', config, suites), /registered suite/);
  assert.throws(() => sourcesForSuite('docs', config, suites), /registered suite/);
  assert.throws(
    () => sourcesForSuite('api', config, { api: { sources: ['unlisted-component'] } }),
    /registered suite/,
  );
});
