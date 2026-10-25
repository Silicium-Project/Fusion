import test from 'node:test';
import assert from 'node:assert/strict';
import { allocationDiagnostic, inspectRun } from '../../tools/lib/ci-inspect.mjs';
test('a billing refusal before allocation is never reported as an executed test failure', () => {
  const job = { id: 1, name: 'budget', conclusion: 'failure', steps: [] };
  const message =
    'The job was not started because recent account payments have failed or your spending limit needs to be increased.';
  const result = allocationDiagnostic(job, [{ message }]);
  assert.equal(result.kind, 'infrastructure');
  assert.equal(result.code, 'billing_or_spending_limit');
  assert.equal(result.tests_executed, false);
  assert.equal(
    allocationDiagnostic({ ...job, steps: [{ name: 'Run test' }] }, [{ message }]),
    null,
  );
});
test('inspection reads allocation evidence without retrying jobs or modifying billing', () => {
  const called = [];
  const result = inspectRun(1, {
    request: (path) => {
      called.push(path);
      if (path.endsWith('/actions/runs/1'))
        return { head_sha: 'a'.repeat(40), temp_clone_token: 'fixture' };
      if (path.includes('/jobs?'))
        return { jobs: [{ id: 2, name: 'changes', conclusion: 'failure', steps: [] }] };
      if (path.includes('/annotations?')) return [{ message: 'No runner available' }];
      throw new Error(path);
    },
  });
  assert.equal(result.run.temp_clone_token, undefined);
  assert.equal(result.diagnostics[0].code, 'runner_not_started');
  assert.equal(called.length, 3);
  assert.throws(() => inspectRun('1/invalid'), /Provide --run/);
});
