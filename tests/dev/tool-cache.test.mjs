import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { verifyCachedTool } from '../../tools/lib/download.mjs';
test('a corrupted tool cache fails instead of reusing an unverified executable', () => {
  const directory = mkdtempSync(join(tmpdir(), 'silicium-cache-test-')),
    path = join(directory, 'tool');
  try {
    const content = Buffer.from('disposable fixture');
    writeFileSync(path, content);
    const expected = createHash('sha256').update(content).digest('hex');
    assert.doesNotThrow(() => verifyCachedTool(path, expected));
    writeFileSync(path, 'corrupted');
    assert.throws(() => verifyCachedTool(path, expected), /checksum mismatch/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
