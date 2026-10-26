/** Acceptance requires a human maintainer's merge and qualification evidence, not a URL-shaped string. */
import { api, repository, canonicalRepository, issueRef } from './github.mjs';
import { Failure } from './process.mjs';
import { referencesIssue } from './issue-links.mjs';
export function acceptanceChecklistComplete(body) {
  const heading = /^#{2,3}\s+(?:Conditions|Critères) d[’']acceptation\s*$/im.exec(body ?? '');
  if (!heading) return false;
  const section = body.slice(heading.index + heading[0].length).split(/\n#{1,6}\s/)[0];
  return Boolean(section && /- \[[xX]\]/.test(section) && !/- \[ \]/.test(section));
}
export function inspectEvidence(url, target, issueUrl, { request = api } = {}) {
  if (!['Documentation', 'CI', 'Dev', 'Prod'].includes(target))
    throw new Failure('Set an explicit validation target', 3);
  const parsed = new URL(url),
    match = parsed.pathname.match(
      /^\/Silicium-Project\/(?:Workbench|Fusion)\/actions\/runs\/([1-9][0-9]*)$/,
    );
  if (
    parsed.protocol !== 'https:' ||
    parsed.host !== 'github.com' ||
    !match ||
    parsed.search ||
    parsed.hash
  )
    throw new Failure('Evidence must be a permanent Workbench Actions run URL', 2);
  const run = request(`repos/${repository}/actions/runs/${match[1]}`);
  const expected = ['Dev', 'Prod'].includes(target)
    ? '.github/workflows/deploy.yml'
    : '.github/workflows/ci.yml';
  if (
    run.conclusion !== 'success' ||
    run.head_branch !== 'main' ||
    canonicalRepository(run.head_repository?.full_name) !== repository ||
    run.path?.split('@')[0] !== expected
  )
    throw new Failure(
      'Evidence is not a successful trusted main execution of the target workflow',
      3,
    );
  if (expected.endsWith('/ci.yml') && run.event !== 'push')
    throw new Failure('A PR or partial manual CI is not acceptance evidence', 3);
  const jobs = request(`repos/${repository}/actions/runs/${run.id}/jobs?per_page=100`).jobs;
  if (
    expected.endsWith('/ci.yml') &&
    !jobs.some(
      (j) => j.name === 'ci/required' && j.conclusion === 'success' && j.status === 'completed',
    )
  )
    throw new Failure('Required CI gate did not execute', 3);
  let sourceSha = run.head_sha;
  let deployment = null;
  if (['Dev', 'Prod'].includes(target)) {
    const environment = target === 'Dev' ? 'development' : 'production';
    const deployments = request(
      `repos/${repository}/deployments?environment=${environment}&per_page=100`,
    );
    deployment = deployments.find((d) => String(d.payload?.run_id) === String(run.id));
    if (!deployment || !deployment.payload?.manifest_digest || !deployment.payload?.release_id)
      throw new Failure('Missing deployment identity and manifest digest', 3);
    const statuses = request(
      `repos/${repository}/deployments/${deployment.id}/statuses?per_page=100`,
    );
    if (statuses[0]?.state !== 'success')
      throw new Failure('Deployment is not currently successful', 3);
    sourceSha = deployment.sha;
  }
  const canonical = issueRef(issueUrl).url;
  const aliases = canonical.includes('/Workbench/')
    ? [canonical, canonical.replace('/Workbench/', '/Fusion/')]
    : [canonical];
  const items = new Map();
  for (const alias of aliases) {
    const query = `repo:${repository} is:pr in:body "${alias}"`;
    const search = request(`search/issues?q=${encodeURIComponent(query)}&per_page=100`);
    if (search.incomplete_results || search.total_count > 100)
      throw new Failure('Contributing PR search is incomplete; acceptance remains blocked', 3);
    for (const item of search.items) items.set(item.number, item);
  }
  if (!items.size) throw new Failure('Link all contributing PRs to the issue by canonical URL', 3);
  const prs = [];
  const merges = [];
  for (const item of items.values()) {
    const pr = request(`repos/${repository}/pulls/${item.number}`);
    if (!referencesIssue(pr.body, issueUrl)) continue;
    if (!pr.merged_at || pr.base.ref !== 'main')
      throw new Failure('A contributing PR remains unmerged', 3);
    if (pr.merged_by?.type !== 'User' || !pr.merged_by.login)
      throw new Failure('A contributing PR was not merged by a human maintainer', 3);
    const permission = request(
      `repos/${repository}/collaborators/${encodeURIComponent(pr.merged_by.login)}/permission`,
    ).permission;
    if (!['admin', 'maintain', 'write'].includes(permission))
      throw new Failure('The contributing PR merger lacks maintainer write permission', 3);
    const compare = request(`repos/${repository}/compare/${pr.merge_commit_sha}...${sourceSha}`);
    if (!['ahead', 'identical'].includes(compare.status))
      throw new Failure('Evidence does not contain every contributing change', 3);
    prs.push(pr.html_url);
    merges.push({
      pr_url: pr.html_url,
      head_sha: pr.head.sha,
      merge_sha: pr.merge_commit_sha,
      actor: pr.merged_by.login,
    });
  }
  if (!prs.length)
    throw new Failure('No contributing PR has an exact canonical Refs: line for this issue', 3);
  return {
    schema_version: 1,
    verified: true,
    source_sha: sourceSha,
    run_id: run.id,
    target,
    evidence_url: parsed.href,
    issue_url: issueUrl,
    pr_urls: prs,
    contribution_mode: 'sole-maintainer',
    pr_merges: merges,
    deployment_id: deployment?.id ?? null,
  };
}
