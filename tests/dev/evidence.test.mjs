import test from 'node:test';
import assert from 'node:assert/strict';
import { acceptanceChecklistComplete, inspectEvidence } from '../../tools/lib/evidence.mjs';
const sha = 'a'.repeat(40),
  issue = 'https://github.com/Silicium-Project/Fusion/issues/1';
const pr = {
  body: `Refs: ${issue}`,
  merged_at: '2026-01-01',
  user: { login: 'author' },
  merged_by: { login: 'author', type: 'User' },
  head: { sha },
  base: { ref: 'main' },
  merge_commit_sha: sha,
  html_url: 'https://github.com/Silicium-Project/Fusion/pull/2',
};
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
test('sole-maintainer acceptance records the human merge and exact contributing commit', () => {
  const evidence = inspectEvidence(
    'https://github.com/Silicium-Project/Fusion/actions/runs/1',
    'CI',
    issue,
    { request },
  );
  assert.equal(evidence.contribution_mode, 'sole-maintainer');
  assert.deepEqual(evidence.pr_merges, [
    { pr_url: pr.html_url, head_sha: sha, merge_sha: sha, actor: 'author' },
  ]);
});
test('acceptance verifies all changes, a maintainer merge and main CI', () =>
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
    (p) => (p.includes('/permission') ? { permission: 'read' } : request(p)),
    (p) =>
      p.includes('/pulls/') && !p.includes('reviews') ? { ...pr, merged_at: null } : request(p),
  ])
    assert.throws(() =>
      inspectEvidence('https://github.com/Silicium-Project/Fusion/actions/runs/1', 'CI', issue, {
        request: override,
      }),
    );
});

test('missing or automated merge identities cannot replace a human decision', () => {
  for (const merged_by of [null, { login: 'bot', type: 'Bot' }, { type: 'User' }])
    assert.throws(
      () =>
        inspectEvidence('https://github.com/Silicium-Project/Fusion/actions/runs/1', 'CI', issue, {
          request: (p) => (p.includes('/pulls/') ? { ...pr, merged_by } : request(p)),
        }),
      /human maintainer/,
    );
});

test('a human merge cannot excuse a failed gate or exclude a contributing change', () => {
  for (const override of [
    (p) => (p.includes('/jobs?') ? { jobs: [] } : request(p)),
    (p) => (p.includes('/compare/') ? { status: 'behind' } : request(p)),
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
