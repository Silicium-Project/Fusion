import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { repinPolicy, repinWorkflow, workflowPath } from '../../tools/ci/repin-policy.mjs';
const old = 'a'.repeat(40);
const next = 'b'.repeat(40);
const workflow = (sha) => `jobs:
  qualify:
    uses: Silicium-Project/Workbench/.github/workflows/component-ci.yml@${sha}
    with:
      policy_sha: ${sha}
`;
test('repinning changes the policy SHA in both places and nothing else', () => {
  const result = repinWorkflow(workflow(old), next);
  assert.equal(result.old, old);
  assert.equal(result.changed, true);
  assert.equal(result.text, workflow(next));
  assert.equal(repinWorkflow(workflow(next), next).changed, false);
});
test('a workflow that does not name one SHA twice is refused', () => {
  for (const text of [
    workflow(old).replace(`policy_sha: ${old}`, `policy_sha: ${next}`),
    workflow(old).replace(`policy_sha: ${old}`, ''),
    `${workflow(old)}    extra: component-ci.yml@${old}\n`,
  ])
    assert.throws(() => repinWorkflow(text, next), { exitCode: 3 });
  for (const bad of ['short', undefined, 'B'.repeat(40)])
    assert.throws(() => repinWorkflow(workflow(old), bad), { exitCode: 2 });
});
test('a dry run reports the plan for all five components and executes nothing', () => {
  const content = Buffer.from(workflow(old)).toString('base64');
  const check = (path) => (path.includes('/compare/') ? { status: 'ahead' } : { content });
  let executed = 0;
  const report = repinPolicy({
    sha: next,
    check,
    proof: () => ({ expires_at: '2026-10-30T12:00:00.000Z' }),
    execute: () => {
      executed++;
    },
  });
  assert.equal(executed, 0);
  assert.equal(report.apply, false);
  assert.equal(report.components.length, 5);
  assert.ok(report.components.every((item) => item.changed && item.from === old));
});
test('a SHA outside Workbench main is refused before any component is read', () => {
  let reads = 0;
  assert.throws(
    () =>
      repinPolicy({
        sha: next,
        check: (path) => {
          reads++;
          return { status: 'diverged', path };
        },
        proof: () => ({}),
      }),
    { exitCode: 3 },
  );
  assert.equal(reads, 1);
});
test('apply clones, edits one file, pushes a branch and opens a pull request, never merges', () => {
  const content = Buffer.from(workflow(old)).toString('base64');
  const check = (path) => (path.includes('/compare/') ? { status: 'identical' } : { content });
  const calls = [];
  let written;
  const report = repinPolicy({
    sha: next,
    apply: true,
    check,
    proof: () => ({ expires_at: 'x' }),
    execute: (command, options = {}) => {
      calls.push(command.slice(0, 3).join(' '));
      if (command[1] === 'repo') {
        const directory = command[4];
        mkdirSync(resolve(directory, '.github/workflows'), { recursive: true });
        writeFileSync(resolve(directory, workflowPath), workflow(old));
        written = directory;
      }
      if (command[1] === 'pr') return { stdout: 'https://github.com/o/r/pull/1' };
      if (command[0] === 'git' && command[1] === 'add')
        assert.equal(readFileSync(resolve(options.cwd, workflowPath), 'utf8'), workflow(next));
      return { stdout: '' };
    },
  });
  assert.ok(written);
  assert.equal(report.components.length, 5);
  assert.ok(
    report.components.every((item) => item.pull_request === 'https://github.com/o/r/pull/1'),
  );
  assert.equal(calls.filter((call) => call.startsWith('git push')).length, 5);
  assert.ok(!calls.some((call) => /merge/.test(call)));
});
