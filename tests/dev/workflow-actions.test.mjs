import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../..');
const workflows = readdirSync(resolve(root, '.github/workflows'))
  .filter((name) => name.endsWith('.yml'))
  .map((name) => [name, readFileSync(resolve(root, '.github/workflows', name), 'utf8')]);

test('workflow actions stay pinned to immutable commit SHAs', () => {
  for (const [name, workflow] of workflows) {
    for (const line of workflow.split('\n')) {
      const match = line.match(/^\s*uses:\s*([^\s]+)$/);
      if (!match || match[1].startsWith('./')) continue;
      assert.match(match[1], /@[a-f0-9]{40}$/, `${name} uses a mutable action reference`);
    }
  }
});

test('setup-node never enables an implicit dependency cache', () => {
  for (const [name, workflow] of workflows) {
    const lines = workflow.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (!/uses:\s*actions\/setup-node@[a-f0-9]{40}/.test(lines[i])) continue;
      const setup = lines.slice(i + 1).find((line) => line.trimStart().startsWith('node-version:'));
      assert.ok(setup, `${name} setup-node step is missing its Node.js version`);
      const versionIndex = lines.indexOf(setup, i + 1);
      assert.match(
        lines[versionIndex + 1] ?? '',
        /^\s*package-manager-cache:\s*false\s*$/,
        `${name} setup-node step must opt out of its implicit package cache`,
      );
    }
  }
});
