import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { readJson, root } from '../../tools/lib/process.mjs';

test('Rust toolchain pins stay aligned across the registry, rustup and workflows', () => {
  const versions = readJson(resolve(root, 'tools/config/toolchains.json'));
  const rootToolchain = readFileSync(resolve(root, 'rust-toolchain.toml'), 'utf8');
  assert.ok(rootToolchain.includes(`channel = "${versions.rust}"`));

  const expression = `RUSTUP_TOOLCHAIN: \${{ matrix.suite == 'solana' && '${versions.rust_solana}' || '${versions.rust}' }}`;
  for (const workflow of ['ci.yml', 'component-ci.yml', 'campaigns.yml']) {
    const contents = readFileSync(resolve(root, `.github/workflows/${workflow}`), 'utf8');
    assert.ok(contents.includes(expression), `${workflow} must use the registered Rust versions`);
  }
});
