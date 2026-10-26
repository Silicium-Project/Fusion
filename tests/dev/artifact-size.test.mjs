import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { treeSize } from '../../tools/ci/artifact-size.mjs';
test('internal runtime links are counted; escapes and cycles are rejected', () => {
  const temp = mkdtempSync(join(tmpdir(), 'silicium-size-'));
  try {
    const root = join(temp, 'artifact');
    mkdirSync(root);
    writeFileSync(join(root, 'module'), 'abc');
    symlinkSync('module', join(root, 'alias'));
    assert.equal(treeSize(root), 6);
    writeFileSync(join(temp, 'private'), 'not an artifact');
    symlinkSync('../private', join(root, 'escape'));
    assert.throws(() => treeSize(root), /escapes/);
    rmSync(join(root, 'escape'));
    symlinkSync('.', join(root, 'cycle'));
    assert.throws(() => treeSize(root), /cycle/);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
