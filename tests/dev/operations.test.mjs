import test from 'node:test';
import assert from 'node:assert/strict';
import { diagnosticRequest } from '../../tools/lib/operations.mjs';
test('diagnostics prepare a fixed workflow without contacting the host or GitHub', () => {
  assert.deepEqual(diagnosticRequest('dev'), {
    schema_version: 1,
    operation: 'ops.diagnose',
    status: 'planned',
    workflow: 'diagnostics.yml',
    ref: 'main',
    environment: 'dev',
    effects: 'read-only host observations; creates a short-lived GitHub report',
  });
  assert.throws(() => diagnosticRequest('$(restart)'), /environment/);
});
