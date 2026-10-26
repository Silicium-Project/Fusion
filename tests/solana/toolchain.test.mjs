import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { root, readJson, git } from '../../tools/lib/process.mjs';
test('Anchor program, SDK, tests and CLI keep the reviewed version and a tracked Rust lock', () => {
  const version = readJson(resolve(root, 'tools/config/toolchains.json')).anchor;
  const cli = readJson(resolve(root, 'tools/config/anchor-tools.json'));
  assert.equal(cli.version, version);
  assert.equal(cli.source_commit, readJson(resolve(root, 'tools/config/upstreams.json')).anchor);
  assert.match(cli.sha256, /^[a-f0-9]{64}$/);
  assert.equal(
    git('-C', 'chain', 'ls-files', '--error-unmatch', 'solana/Cargo.lock'),
    'solana/Cargo.lock',
  );
  const lock = readFileSync(resolve(root, 'chain/solana/Cargo.lock'), 'utf8');
  for (const name of ['anchor-lang', 'anchor-spl'])
    assert.equal(lock.match(new RegExp(`name = "${name}"\\nversion = "([^"]+)"`))?.[1], version);
  assert.equal(
    readJson(resolve(root, 'chain/sdk/package.json')).dependencies['@coral-xyz/anchor'],
    version,
  );
  const tests = readJson(resolve(root, 'chain/solana/package.json'));
  assert.equal(tests.devDependencies['@coral-xyz/anchor'].replace(/^\^/, ''), version);
});
