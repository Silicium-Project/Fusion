import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
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

test('public Workbench verifies private evidence without receiving private build artifacts', () => {
  const ci = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8');
  const evidence = readFileSync(
    new URL('../../.github/workflows/private-integration-evidence.yml', import.meta.url),
    'utf8',
  );
  assert.match(ci, /name: qualification-plan-\$\{\{ github\.run_attempt \}\}/);
  assert.match(ci, /name: report-\$\{\{ matrix\.suite \}\}-\$\{\{ github\.run_attempt \}\}/);
  assert.match(ci, /pattern: report-\*-\$\{\{ github\.run_attempt \}\}/);
  assert.match(evidence, /workflow_call:/);
  assert.match(evidence, /integration\/evidence/);
  assert.match(evidence, /private-integration-evidence-\$\{\{ github\.run_attempt \}\}/);
  assert.equal((evidence.match(/actions\/download-artifact@/g) ?? []).length, 2);
  assert.equal((evidence.match(/digest-mismatch: error/g) ?? []).length, 2);
  assert.doesNotMatch(evidence, /delivery-(?:api|web|network|node-ui)-/);
  assert.equal(existsSync(new URL('../../.github/workflows/release.yml', import.meta.url)), false);
  assert.equal(
    existsSync(
      new URL('../../tools/config/integration-artifact-reader-app-manifest.json', import.meta.url),
    ),
    false,
  );
});
