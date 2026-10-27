import test from 'node:test';
import assert from 'node:assert/strict';
import { validateManifest, packageVersions, compareVersions } from '../../tools/lib/manifest.mjs';
const sha = 'a'.repeat(40);
const candidate = () => ({
  schema_version: 1,
  source_sha: sha,
  channel: 'dev',
  version: '0.3.0-dev.1',
  release_id: `dev-0.3.0-dev.1-${sha.slice(0, 12)}`,
  qualification: {
    repository: 'Silicium-Project/Integration',
    workflow: '.github/workflows/qualification.yml',
    source_sha: sha,
    workbench_sha: sha,
    status: 'success',
    run_id: 123,
    run_attempt: 1,
    run_number: 31,
    integration_sha: 'b'.repeat(40),
    policy_workflow_sha: 'c'.repeat(40),
    policy_digest: 'd'.repeat(64),
    component_pins: Object.fromEntries(
      Object.entries({
        api: 'Silicium-Project/BackEnd',
        web: 'Silicium-Project/FrontEnd',
        node: 'Silicium-Project/DesktopApp',
        network: 'Silicium-Project/Network',
        solana: 'Silicium-Project/Solana',
      }).map(([name, repository]) => [name, { repository, commit: 'e'.repeat(40) }]),
    ),
  },
  policy_digest: 'd'.repeat(64),
  components: {
    ...Object.fromEntries(
      ['api', 'web', 'network'].map((name) => [
        name,
        { source_sha: sha, image: `ghcr.io/silicium-project/${name}@sha256:${'b'.repeat(64)}` },
      ]),
    ),
    node: { source_sha: sha, version: '0.3.0-dev.1', channel: 'dev' },
  },
  assets: ['packages.tar.gz', 'deployment.tar.gz', 'qualification.json'].map((name) => ({
    name,
    sha256: 'c'.repeat(64),
    size: 12,
  })),
});
test('release ordering reserves the final Windows field for stable and compares counters numerically', () => {
  assert.equal(compareVersions('0.3.0-dev.10', '0.3.0-dev.2'), 1);
  assert.equal(compareVersions('0.3.0', '0.3.0-dev.65534'), 1);
  assert.equal(compareVersions('0.4.0-dev.1', '0.3.0'), 1);
  assert.equal(compareVersions('0.3.0', '0.3.0'), 0);
  assert.throws(() => packageVersions('0.3.0-dev.65535'));
});
test('complete immutable identity validates', () =>
  assert.deepEqual(validateManifest(candidate()), []));
test('mutable images, stale qualification and prod prereleases fail', () => {
  for (const edit of [
    (m) => (m.components.api.image = 'api:latest'),
    (m) => (m.qualification.source_sha = 'b'.repeat(40)),
    (m) => (m.channel = 'prod'),
  ]) {
    const m = candidate();
    edit(m);
    assert.ok(validateManifest(m).length);
  }
});
test('component pins and duplicated policy digest must remain exact', () => {
  const wrongPin = candidate();
  wrongPin.qualification.component_pins.node.repository = 'Silicium-Project/Network';
  assert.ok(validateManifest(wrongPin).length);
  const wrongPolicy = candidate();
  wrongPolicy.policy_digest = 'f'.repeat(64);
  assert.ok(validateManifest(wrongPolicy).length);
});
test('asset names cannot escape the snapshot', () => {
  const m = candidate();
  m.assets = [{ name: '../wallet', sha256: 'a'.repeat(64), size: 1 }];
  assert.ok(validateManifest(m).length);
});
test('versions retain prerelease ordering and unique Windows sequence', () => {
  assert.deepEqual(packageVersions('0.3.0-dev.12'), {
    semver: '0.3.0-dev.12',
    deb: '0.3.0~dev.12',
    rpm: '0.3.0~dev.12',
    rpm_release: '1',
    windows: '0.3.0.12',
  });
  assert.equal(packageVersions('0.3.0').windows, '0.3.0.65535');
  for (const v of ['0.3.0+hidden', '0.3.0-dev.0', '0.3.0-dev.65535', '0.3.0-dev.65536', '$(id)'])
    assert.throws(() => packageVersions(v));
});
