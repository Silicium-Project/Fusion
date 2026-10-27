import test from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdtempSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  privateDeliveryStagePaths,
  stagePrivateDelivery,
} from '../../tools/lib/private-delivery-stage.mjs';

const suites = Object.keys(privateDeliveryStagePaths);
const artifacts = suites.map((suite, index) => ({
  suite,
  id: index + 1,
  digest: `sha256:${String(index + 1).repeat(64)}`,
  size_bytes: 1,
}));

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'silicium-private-delivery-'));
  const workspace = join(root, 'workspace');
  mkdirSync(workspace);
  const artifactRoot = join(workspace, '.artifacts', 'private-integration');
  mkdirSync(artifactRoot, { recursive: true });
  for (const suite of suites) {
    const path = join(artifactRoot, suite === 'node_ui' ? 'node-ui' : suite);
    mkdirSync(path);
    writeFileSync(join(path, `${suite}.bin`), `${suite}-qualified`);
  }
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return { artifactRoot, workspace };
}

test('staging copies only the four verified suites to fixed build paths', (t) => {
  const { artifactRoot, workspace } = fixture(t);
  const staged = stagePrivateDelivery({ artifactRoot, workspace, artifacts });
  assert.deepEqual(staged.map((row) => row.suite).sort(), [...suites].sort());
  for (const suite of suites) {
    const target = join(workspace, privateDeliveryStagePaths[suite], `${suite}.bin`);
    assert.equal(readFileSync(target, 'utf8'), `${suite}-qualified`);
  }
});

test('staging refuses a missing identity or an incomplete artifact tree before copying', (t) => {
  const first = fixture(t);
  assert.throws(
    () => stagePrivateDelivery({ ...first, artifacts: artifacts.slice(1) }),
    /exactly one verified artifact/,
  );

  const second = fixture(t);
  rmSync(join(second.artifactRoot, 'web'), { recursive: true, force: true });
  assert.throws(() => stagePrivateDelivery({ ...second, artifacts }), /web source artifact/);
  assert.equal(existsSync(join(second.workspace, privateDeliveryStagePaths.api)), false);
});

test('staging refuses overwrite and does not follow symlink inputs', (t) => {
  const { artifactRoot, workspace } = fixture(t);
  const apiTarget = join(workspace, privateDeliveryStagePaths.api);
  mkdirSync(apiTarget, { recursive: true });
  assert.throws(() => stagePrivateDelivery({ artifactRoot, workspace, artifacts }), /overwrite/);
  if (process.platform !== 'win32') {
    const { artifactRoot: symlinkRoot, workspace: symlinkWorkspace } = fixture(t);
    const path = join(symlinkRoot, 'api');
    rmSync(path, { recursive: true, force: true });
    symlinkSync(join(symlinkRoot, 'web'), path, 'dir');
    assert.throws(
      () =>
        stagePrivateDelivery({ artifactRoot: symlinkRoot, workspace: symlinkWorkspace, artifacts }),
      /source artifact/,
    );
  }
});
