import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { root, readJson } from '../../tools/lib/process.mjs';
import { workspaceStatus } from '../../tools/lib/workspace.mjs';

test('materialized component pins and all contract source definitions exist', () => {
  assert.equal(workspaceStatus({ materialized: true }).status, 'success');
  for (const contract of readJson(resolve(root, 'contracts/catalog.json')).contracts)
    for (const path of [contract.owner, ...(contract.co_owners ?? []), contract.definition])
      assert.ok(existsSync(resolve(root, path)), `${contract.id}: ${path}`);
});
