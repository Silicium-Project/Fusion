import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { root, readJson } from '../../tools/lib/process.mjs';
import { workspaceConfig } from '../../tools/lib/workspace.mjs';
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
