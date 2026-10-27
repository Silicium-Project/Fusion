import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const registry = JSON.parse(readFileSync(resolve(root, 'tools/config/actions.json'), 'utf8'));
const actions = ['checkout', 'setup-node', 'upload-artifact', 'download-artifact'];

test('Node 24 action pins match the centralized registry in every workflow', () => {
  const expectedTags = {
    checkout: 'v5',
    'setup-node': 'v6',
    'upload-artifact': 'v7',
    'download-artifact': 'v8',
  };
  const workflowDir = resolve(root, '.github/workflows');
  const workflows = readdirSync(workflowDir).filter((file) => file.endsWith('.yml'));

  for (const action of actions) {
    assert.equal(registry[action]?.tag, expectedTags[action]);
    assert.match(registry[action]?.uses ?? '', new RegExp(`^actions/${action}@[a-f0-9]{40}$`));
  }

  for (const workflow of workflows) {
    const source = readFileSync(join(workflowDir, workflow), 'utf8');
    const uses = source.matchAll(
      /uses:\s*(actions\/(?:checkout|setup-node|upload-artifact|download-artifact)@[a-f0-9]{40})/g,
    );
    for (const [, pinned] of uses) {
      const action = pinned.match(/^actions\/([^@]+)@/)[1];
      assert.equal(pinned, registry[action].uses, `${workflow}: ${action}`);
    }
  }
});

test('setup-node never enables an implicit package cache', () => {
  const workflowDir = resolve(root, '.github/workflows');
  let occurrences = 0;
  for (const workflow of readdirSync(workflowDir).filter((file) => file.endsWith('.yml'))) {
    const lines = readFileSync(join(workflowDir, workflow), 'utf8').split('\n');
    for (let index = 0; index < lines.length; index += 1) {
      if (!lines[index].includes('uses: actions/setup-node@')) continue;
      occurrences += 1;
      assert.ok(
        lines
          .slice(index + 1, index + 7)
          .some((line) => /package-manager-cache:\s*false/.test(line)),
        `${workflow}:${index + 1}: setup-node package-manager-cache must be false`,
      );
    }
  }
  assert.ok(occurrences > 0, 'expected at least one setup-node use');
});
