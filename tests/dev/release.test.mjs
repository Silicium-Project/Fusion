import test from 'node:test';
import assert from 'node:assert/strict';
import { assertDeliveryGate, releasePlan } from '../../tools/lib/release.mjs';

const sha = 'a'.repeat(40);

test('release plan never treats public Workbench CI as private qualification', () => {
  const plan = releasePlan({ channel: 'dev', version: '0.3.0-dev.1', sha });
  assert.equal(plan.schema_version, 2);
  assert.equal(plan.status, 'requires_public_ci');
  assert.equal(plan.private_integration_required, true);
  assert.equal(plan.qualification_scope, null);
});

test('deployment gate refuses when disabled or not bound to the private bridge', () => {
  assert.throws(
    () => assertDeliveryGate({ SILICIUM_DELIVERY_ENABLED: '0' }),
    /delivery is disabled; no deployment request was sent/,
  );
  assert.throws(
    () => assertDeliveryGate({ SILICIUM_DELIVERY_ENABLED: '1' }),
    /bridge is not qualified; no deployment request was sent/,
  );
  assert.throws(
    () =>
      assertDeliveryGate({
        SILICIUM_DELIVERY_ENABLED: '1',
        SILICIUM_DELIVERY_CONTRACT: 'workbench-public-ci',
      }),
    /bridge is not qualified; no deployment request was sent/,
  );
});

test('deployment gate accepts only the explicit qualified private bridge marker', () => {
  assert.equal(
    assertDeliveryGate({
      SILICIUM_DELIVERY_ENABLED: '1',
      SILICIUM_DELIVERY_CONTRACT: 'private-integration-v1',
    }),
    undefined,
  );
});
