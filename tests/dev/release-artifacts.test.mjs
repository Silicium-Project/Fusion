import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  isQualifiedArtifactFromAttempt,
  qualifiedBuildArtifacts,
  releaseArtifactName,
} from '../../tools/lib/release-artifacts.mjs';

test('build outputs are unique to a validated workflow attempt', () => {
  assert.deepEqual(qualifiedBuildArtifacts(2), {
    api: 'api-binary-2',
    web: 'web-output-2',
    network: 'network-binaries-2',
    node: 'node-ui-output-2',
  });
  assert.notEqual(qualifiedBuildArtifacts(1).api, qualifiedBuildArtifacts(2).api);
});

test('temporary release artifact names include the current run attempt', () => {
  assert.equal(releaseArtifactName('candidate-input', '3'), 'candidate-input-3');
  assert.equal(isQualifiedArtifactFromAttempt('qualification-plan-3', 3), true);
  assert.equal(isQualifiedArtifactFromAttempt('report-solana-3', 3), true);
  assert.equal(isQualifiedArtifactFromAttempt('api-binary-3', 3), true);
  assert.equal(isQualifiedArtifactFromAttempt('api-binary-2', 3), false);
  assert.equal(isQualifiedArtifactFromAttempt('report-solana-2', 3), false);
});

test('artifact naming rejects invalid attempts and names', () => {
  for (const attempt of [0, -1, 'x', Number.MAX_SAFE_INTEGER + 1])
    assert.throws(() => qualifiedBuildArtifacts(attempt), /workflow attempt/);
  assert.throws(() => releaseArtifactName('../candidate', 1), /artifact name/);
});

test('the bridge pins receipt and private outputs to the producing Integration attempt', () => {
  const ci = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8');
  const release = readFileSync(
    new URL('../../.github/workflows/release.yml', import.meta.url),
    'utf8',
  );
  assert.match(ci, /name: qualification-plan-\$\{\{ github\.run_attempt \}\}/);
  assert.match(ci, /name: report-\$\{\{ matrix\.suite \}\}-\$\{\{ github\.run_attempt \}\}/);
  assert.match(ci, /pattern: report-\*-\$\{\{ github\.run_attempt \}\}/);
  for (const base of ['web-output', 'node-ui-output', 'api-binary', 'network-binaries'])
    assert.ok(
      ci.includes('name: ' + base + '-${{ github.run_attempt }}'),
      `${base} attempt suffix`,
    );
  assert.match(
    release,
    /name: private-integration-evidence-\$\{\{ inputs\.qualification_attempt \}\}/,
  );
  for (const base of ['delivery-api', 'delivery-web', 'delivery-network', 'delivery-node-ui'])
    assert.ok(
      release.includes('name: ' + base + '-${{ inputs.qualification_attempt }}'),
      `${base} attempt suffix`,
    );
  assert.equal((release.match(/digest-mismatch: error/g) ?? []).length, 5);
  assert.doesNotMatch(release, /actions\/upload-artifact@/);
});
