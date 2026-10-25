import test from 'node:test';
import assert from 'node:assert/strict';
import {
  acceptanceChecklistComplete,
  independentApproval,
  inspectEvidence,
} from '../../tools/lib/evidence.mjs';
const sha = 'a'.repeat(40),
  issue = 'https://github.com/Silicium-Project/Fusion/issues/1';
const pr = {
  body: `Refs: ${issue}`,
  merged_at: '2026-01-01',
  user: { login: 'author' },
  head: { sha },
  base: { ref: 'main' },
  merge_commit_sha: sha,
  html_url: 'https://github.com/Silicium-Project/Fusion/pull/2',
};
const reviews = [
  {
    user: { login: 'reviewer', type: 'User' },
    state: 'APPROVED',
    commit_id: sha,
    submitted_at: '2026-01-01',
  },
];
function request(path) {
  if (path.includes('/jobs?'))
    return { jobs: [{ name: 'ci/required', status: 'completed', conclusion: 'success' }] };
  if (path.includes('/permission')) return { permission: 'write' };
  if (path.includes('/actions/runs/'))
    return {
      id: 1,
      head_sha: sha,
      conclusion: 'success',
      head_branch: 'main',
      head_repository: { full_name: 'Silicium-Project/Fusion' },
      path: '.github/workflows/ci.yml',
      event: 'push',
    };
  if (path.startsWith('search/')) return { total_count: 1, items: [{ number: 2 }] };
  if (path.includes('/reviews')) return reviews;
  if (path.includes('/compare/')) return { status: 'identical' };
  if (path.includes('/pulls/')) return pr;
  throw new Error(path);
}
test('unchecked and absent acceptance criteria block closure', () => {
  assert.equal(
    acceptanceChecklistComplete('## Conditions d’acceptation\n- [x] done\n- [ ] pending'),
    false,
  );
  assert.equal(acceptanceChecklistComplete('no criteria'), false);
  assert.equal(
    acceptanceChecklistComplete('## Conditions d’acceptation\n- [x] done\n## Tests\n- [ ] later'),
    true,
  );
});
test('self approval, bot review and obsolete head are rejected', () => {
  assert.equal(independentApproval(pr, reviews), true);
  for (const r of [
    { ...reviews[0], user: { login: 'author', type: 'User' } },
    { ...reviews[0], commit_id: 'old' },
    { ...reviews[0], user: { login: 'bot', type: 'Bot' } },
  ])
    assert.equal(independentApproval(pr, [r]), false);
});
test('acceptance verifies all changes, review and main CI', () =>
  assert.equal(
    inspectEvidence('https://github.com/Silicium-Project/Fusion/actions/runs/1', 'CI', issue, {
      request,
    }).verified,
    true,
  ));
test('arbitrary links, manual CI, missing or pending PRs are rejected', () => {
  assert.throws(() => inspectEvidence('https://example.com/green', 'CI', issue, { request }));
  for (const override of [
    (p) =>
      p.includes('/actions/runs/') ? { ...request(p), event: 'workflow_dispatch' } : request(p),
    (p) => (p.startsWith('search/') ? { total_count: 0, items: [] } : request(p)),
    (p) => (p.includes('/reviews') ? [] : request(p)),
    (p) =>
      p.includes('/pulls/') && !p.includes('reviews') ? { ...pr, merged_at: null } : request(p),
  ])
    assert.throws(() =>
      inspectEvidence('https://github.com/Silicium-Project/Fusion/actions/runs/1', 'CI', issue, {
        request: override,
      }),
    );
});

test('GitHub issue-form headings delimit the acceptance checklist', () => {
  assert.equal(
    acceptanceChecklistComplete(
      '### Conditions d’acceptation\n\n- [x] verified\n\n### Other work\n- [ ] later',
    ),
    true,
  );
  assert.equal(acceptanceChecklistComplete('### Conditions d’acceptation\n- [ ] missing'), false);
});
test('incidental mentions and issue-number prefixes cannot qualify another issue', () => {
  for (const body of [`Discussion: ${issue}`, `Refs: ${issue}0`])
    assert.throws(
      () =>
        inspectEvidence('https://github.com/Silicium-Project/Fusion/actions/runs/1', 'CI', issue, {
          request: (p) =>
            p.includes('/pulls/') && !p.includes('reviews') ? { ...pr, body } : request(p),
        }),
      /No contributing PR/,
    );
});
