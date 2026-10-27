import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const manifestPath = new URL(
  '../../tools/config/delivery-publisher-app-manifest.json',
  import.meta.url,
);
const manifest = JSON.parse(readFileSync(fileURLToPath(manifestPath), 'utf8'));

test('delivery publisher is separate, private, webhook-free, and narrowly permissioned', () => {
  assert.equal(manifest.name, 'Silicium Delivery Publisher');
  assert.equal(manifest.url, 'https://github.com/Silicium-Project/Workbench');
  assert.equal(manifest.public, false);
  assert.deepEqual(manifest.default_events, []);
  assert.deepEqual(manifest.default_permissions, {
    actions: 'write',
    contents: 'write',
    packages: 'write',
  });
});

test('Integration artifact reader is private, webhook-free, and read-only for Actions', () => {
  const app = JSON.parse(
    readFileSync(
      new URL('../../tools/config/integration-artifact-reader-app-manifest.json', import.meta.url),
      'utf8',
    ),
  );
  assert.equal(app.name, 'Silicium Integration Artifact Reader');
  assert.equal(app.public, false);
  assert.deepEqual(app.default_permissions, { actions: 'read' });
  assert.deepEqual(app.default_events, []);
});
