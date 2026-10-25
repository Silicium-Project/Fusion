import test from 'node:test';
import assert from 'node:assert/strict';
import { nextStatus } from '../../tools/lib/project.mjs';
const ready = {
  status: 'Backlog',
  validation_target: 'CI',
  preparation: 'Validée',
  dependencies_complete: true,
  owner: 'member',
  size: 'S',
};
test('readiness requires preparation and dependencies', () => {
  assert.equal(nextStatus(ready), 'Prêt');
  assert.equal(nextStatus({ ...ready, dependencies_complete: false }), 'Backlog');
  assert.equal(nextStatus({ ...ready, preparation: 'À compléter' }), 'Backlog');
});
test('merge never means accepted', () => assert.equal(nextStatus({ merged: true }), 'Validation'));
test('all active PRs must be ready and qualified for review', () => {
  const a = { draft: false, ci: 'success' };
  assert.equal(nextStatus({ pull_requests: [a] }), 'Revue');
  assert.equal(nextStatus({ pull_requests: [a, { draft: false, ci: 'failure' }] }), 'En cours');
});
test('HOLD survives CI, merges and closure', () =>
  assert.equal(
    nextStatus({ hold: true, merged: true, acceptance: { verified: true } }),
    'Arbitrage',
  ));
test('acceptance requires target, children and all changes', () => {
  const a = {
    acceptance: { verified: true },
    children_complete: true,
    required_prs_complete: true,
    target_verified: true,
  };
  assert.equal(nextStatus(a), 'Terminé');
  for (const k of ['children_complete', 'required_prs_complete', 'target_verified'])
    assert.notEqual(nextStatus({ ...a, [k]: false }), 'Terminé');
});
test('abandoned work is not counted as delivered', () =>
  assert.equal(nextStatus({ abandoned: true }), 'Abandonné'));
