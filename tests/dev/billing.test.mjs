import test from 'node:test';
import assert from 'node:assert/strict';
import {
  requireZeroActionsBudget,
  privateQualificationWindow,
  validatePrivateWindow,
} from '../../tools/lib/billing.mjs';
test('private CI requires an organization Actions zero budget with a hard stop', () => {
  const budget = {
    budget_scope: 'organization',
    budget_product_sku: 'actions',
    budget_amount: 0,
    prevent_further_usage: true,
  };
  assert.equal(requireZeroActionsBudget([budget]).amount, 0);
  for (const values of [
    [],
    [{ ...budget, budget_amount: 1 }],
    [{ ...budget, prevent_further_usage: false }],
    [{ ...budget, budget_scope: 'repository' }],
  ])
    assert.throws(() => requireZeroActionsBudget(values));
});
test('a private CI window cannot be replayed on another commit or kept open indefinitely', () => {
  const sha = 'a'.repeat(40),
    now = Date.now(),
    window = privateQualificationWindow(sha, 10, now);
  assert.equal(validatePrivateWindow(window, sha, now + 1000), true);
  assert.throws(() => validatePrivateWindow(window, 'b'.repeat(40), now));
  assert.throws(() => validatePrivateWindow(window, sha, now + 600_000));
  assert.throws(() => privateQualificationWindow(sha, 241, now));
  assert.throws(() => validatePrivateWindow({ ...window, actions_budget: 1 }, sha, now));
});
