import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { countTests } from '../../tools/lib/runner.mjs';
import { parseArgs, inside, run, git } from '../../tools/lib/process.mjs';
for (const [format, output, count] of [
  ['node', '# tests 4', 4],
  ['vitest', 'Tests  12 passed (12)', 12],
  ['rust', 'test result: ok. 9 passed; 0 failed;\ntest result: ok. 3 passed;', 12],
  ['go', '{"Action":"pass","Test":"TestOne"}\n{"Action":"pass","Package":"api"}', 1],
  ['anchor', '53 passing (5m)', 53],
  ['pytest', '19 passed in 2.14s', 19],
  ['playwright', '  6 passed (1.2s)', 6],
])
  test(`${format} reports executed tests`, () => assert.equal(countTests(output, format), count));
test('unrecognized or empty output is never a test pass', () =>
  assert.equal(countTests('passed', 'node'), 0));
test('arguments remain data and duplicate options fail', () => {
  assert.deepEqual(parseArgs(['ci', 'plan', '--base', '$(id)', '--json']).options, {
    base: '$(id)',
    json: true,
  });
  assert.throws(() => parseArgs(['--base', 'a', '--base', 'b']));
});
test('file boundaries reject escaping paths', () => assert.throws(() => inside('../wallet')));
test('the actual dev entry point executes a suite and writes complete evidence', () => {
  const folder = mkdtempSync(resolve(tmpdir(), 'silicium-runner-smoke-'));
  try {
    const output = resolve(folder, 'docs.json');
    const result = run(
      [process.execPath, 'tools/dev.mjs', 'test', '--suite', 'docs', '--output', output],
      { allowFailure: true },
    );
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.match(result.stderr, /^\[ci\] docs 1\/1 check: .* — started /m);
    assert.match(result.stderr, /^\[ci\] docs 1\/1 check: .* — passed in \d+ ms$/m);
    const report = JSON.parse(readFileSync(output, 'utf8'));
    assert.equal(report.schema_version, 1);
    assert.equal(report.suite, 'docs');
    assert.equal(report.source_sha, git('rev-parse', 'HEAD'));
    assert.equal(report.status, 'success');
    assert.equal(report.steps.length, 1);
    assert.equal(report.steps[0].exit_code, 0);
    assert.ok(report.toolchain_policy.node);
    assert.equal(typeof report.dirty_after, 'boolean');
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
});
