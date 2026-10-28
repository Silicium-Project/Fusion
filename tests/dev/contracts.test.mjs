import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { root, readJson } from '../../tools/lib/process.mjs';
import { validateWorkspace, workspaceConfig, workspaceLock } from '../../tools/lib/workspace.mjs';

const require = createRequire(resolve(root, 'tools/quality/package.json'));
const Ajv = require('ajv');

test('the repository registry and component pins declare versioned schema contracts', () => {
  const registry = workspaceConfig();
  const pins = workspaceLock();
  const registrySchema = readJson(resolve(root, 'contracts/workspace/registry-v1.schema.json'));
  const pinsSchema = readJson(resolve(root, 'contracts/workspace/pins-v1.schema.json'));
  const reportSchema = readJson(
    resolve(root, 'contracts/ci/repository-policy-report-v1.schema.json'),
  );
  const ajv = new Ajv({ allErrors: true });
  const validateRegistry = ajv.compile(registrySchema);
  const validatePins = ajv.compile(pinsSchema);

  assert.equal(registry.$schema, registrySchema.$id);
  assert.equal(pins.$schema, pinsSchema.$id);
  assert.equal(registrySchema.properties.schema_version.const, registry.schema_version);
  assert.equal(pinsSchema.properties.schema_version.const, pins.schema_version);
  assert.ok(registrySchema.required.includes('components'));
  assert.ok(pinsSchema.required.includes('components'));
  assert.equal(
    reportSchema.$id,
    'https://silicium.network/contracts/ci/repository-policy-report/v1',
  );
  assert.ok(reportSchema.properties.api_observations.items.oneOf.length >= 2);
  assert.equal(validateWorkspace(registry, pins), pins);
  assert.equal(validateRegistry(registry), true, ajv.errorsText(validateRegistry.errors));
  assert.equal(validatePins(pins), true, ajv.errorsText(validatePins.errors));

  const invalidRegistry = structuredClone(registry);
  delete invalidRegistry.public_suites;
  assert.equal(validateRegistry(invalidRegistry), false);
  assert.ok(validateRegistry.errors.some((error) => error.keyword === 'required'));
  assert.doesNotThrow(() => ajv.compile(reportSchema));
});

test('the contract catalog names real owners, definitions and registered validation suites', () => {
  const contracts = readJson(resolve(root, 'contracts/catalog.json')).contracts;
  const suites = readJson(resolve(root, 'tools/config/lanes.json')).suites;
  assert.equal(new Set(contracts.map((c) => c.id)).size, contracts.length);
  for (const contract of contracts) {
    for (const file of [contract.owner, ...(contract.co_owners ?? []), contract.definition])
      assert.ok(
        existsSync(resolve(root, file)) ||
          Object.values(workspaceConfig().components).some(
            (c) => file === c.path || file.startsWith(c.path + '/'),
          ),
        `${contract.id}: ${file}`,
      );
    assert.ok(String(contract.version).length);
    for (const suite of contract.validation_suites)
      assert.ok(suites[suite], `${contract.id}: ${suite}`);
  }
  const http = contracts.find((c) => c.id === 'http-api');
  const spec = readFileSync(resolve(root, http.definition), 'utf8');
  assert.equal(http.version, spec.match(/^  version:\s*(\S+)/m)?.[1]);
});
