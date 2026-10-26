import test from 'node:test';
import assert from 'node:assert/strict';
import { referencedIssues, referencesIssue } from '../../tools/lib/issue-links.mjs';
const root = 'https://github.com/Silicium-Project/Fusion/issues/';
test('only exact explicit canonical issue references contribute to delivery', () => {
  const body = `Discussion: ${root}21\nRefs: ${root}210\nRefs: ${root}210\r\nRefs: ${root}211?token=x\nRefs: ${root}212#anchor\n`;
  assert.deepEqual(referencedIssues(body), [
    'https://github.com/Silicium-Project/Workbench/issues/210',
  ]);
  assert.equal(referencesIssue(body, `${root}21`), false);
  assert.equal(referencesIssue(body, `${root}210`), true);
  assert.deepEqual(referencedIssues(null), []);
});
test('several PRs can declare the same issue without automatic closure keywords', () => {
  for (const body of [`Refs: ${root}210`, `Refs: ${root}210\nRefs: ${root}211`])
    assert.equal(referencesIssue(body, `${root}210`), true);
});

test('Fusion history and Workbench references identify the same issue without duplicates', () => {
  const canonical = 'https://github.com/Silicium-Project/Workbench/issues/210';
  assert.deepEqual(referencedIssues(`Refs: ${root}210\nRefs: ${canonical}`), [canonical]);
  assert.equal(referencesIssue(`Refs: ${root}210`, canonical), true);
  assert.equal(referencesIssue(`Refs: ${canonical}`, `${root}210`), true);
});
