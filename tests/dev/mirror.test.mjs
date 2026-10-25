import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { run } from '../../tools/lib/process.mjs';
import { updateSnapshot } from '../../tools/ci/mirror.mjs';
test('mirror preserves external files, replaces only fusion, proves the exact tree and refuses a downgrade', () => {
  const temp = mkdtempSync(join(tmpdir(), 'silicium-mirror-test-'));
  const git = (cwd, ...args) => run(['git', ...args], { cwd }).stdout.trim();
  const commit = (cwd) =>
    git(
      cwd,
      '-c',
      'user.name=Fixture',
      '-c',
      'user.email=fixture@example.invalid',
      'commit',
      '-m',
      'fixture',
    );
  try {
    const source = join(temp, 'source'),
      target = join(temp, 'target');
    for (const folder of [source, target]) {
      mkdirSync(folder);
      git(folder, 'init', '--initial-branch=main');
    }
    writeFileSync(join(source, 'README.md'), 'first\n');
    git(source, 'add', '.');
    commit(source);
    const first = git(source, 'rev-parse', 'HEAD');
    writeFileSync(join(target, 'epitech.txt'), 'keep\n');
    git(target, 'add', '.');
    commit(target);
    assert.equal(updateSnapshot(source, target, first, 1).status, 'updated');
    assert.equal(readFileSync(join(target, 'epitech.txt'), 'utf8'), 'keep\n');
    assert.equal(readFileSync(join(target, 'fusion/README.md'), 'utf8'), 'first\n');
    assert.equal(updateSnapshot(source, target, first, 1).status, 'unchanged');
    writeFileSync(join(source, 'README.md'), 'second\n');
    git(source, 'add', '.');
    commit(source);
    const second = git(source, 'rev-parse', 'HEAD');
    assert.equal(updateSnapshot(source, target, second, 2).status, 'updated');
    assert.throws(() => updateSnapshot(source, target, first, 1), /backwards/);
    assert.equal(
      git(target, 'rev-parse', 'HEAD:fusion'),
      git(source, 'rev-parse', `${second}^{tree}`),
    );
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
