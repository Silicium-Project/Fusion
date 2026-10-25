/** Reconcile trusted GitHub metadata; never check out or execute PR content. */
import { api, pages, repository } from '../lib/github.mjs';
import { projectState, fieldValues, nextStatus, setField } from '../lib/project.mjs';
import { inspectEvidence } from '../lib/evidence.mjs';

const apply = process.argv.includes('--apply');
const project = projectState();
const items = new Map(project.items.filter((x) => x.content?.url).map((x) => [x.content.id, x]));
const prs = pages(`repos/${repository}/pulls?state=all`);
const summaries = [];
for (const item of items.values()) {
  const issue = item.content,
    f = fieldValues(item);
  const hold =
    issue.repository.nameWithOwner.endsWith('/planning-private') ||
    f.Phase === 'HOLD' ||
    f.Status === 'Arbitrage';
  if (hold) continue;
  const linked = prs.filter((p) => (p.body ?? '').includes(issue.url));
  const active = [];
  for (const p of linked.filter((x) => !x.merged_at && x.state === 'open')) {
    if (p.head.repo?.full_name !== repository) continue;
    const checks = api(
      `repos/${repository}/commits/${p.head.sha}/check-runs?filter=latest&per_page=100`,
    ).check_runs;
    const required = checks.filter(
      (c) => c.name === 'ci/required' && c.app?.slug === 'github-actions',
    );
    const reviews = api(`repos/${repository}/pulls/${p.number}/reviews?per_page=100`);
    const latest = new Map();
    for (const r of reviews) if (r.user?.login) latest.set(r.user.login, r);
    active.push({
      draft: p.draft,
      closed: false,
      ci: required.length === 1 ? required[0].conclusion : 'pending',
      changes_requested: [...latest.values()].some((r) => r.state === 'CHANGES_REQUESTED'),
    });
  }
  const completed = (child) => {
    const childItem = items.get(child.id);
    return (
      child.state === 'CLOSED' &&
      child.stateReason === 'COMPLETED' &&
      (!childItem || fieldValues(childItem).Status === 'Terminé')
    );
  };
  let acceptance = null;
  if (issue.state === 'CLOSED' && issue.stateReason === 'COMPLETED') {
    for (const c of pages(
      `repos/${issue.repository.nameWithOwner}/issues/${issue.number}/comments`,
    ).reverse()) {
      const match = c.body?.match(/<!-- silicium-acceptance:v1 (\{[^]*?\}) -->/);
      if (!match || c.user?.type !== 'User') continue;
      const permission = api(
        `repos/${repository}/collaborators/${encodeURIComponent(c.user.login)}/permission`,
      );
      if (!['admin', 'maintain', 'write'].includes(permission.permission)) continue;
      try {
        const v = JSON.parse(match[1]);
        acceptance = inspectEvidence(v.evidence_url, f['Validation cible'], issue.url);
      } catch {
        acceptance = null;
      }
      break;
    }
  }
  const model = {
    status: f.Status,
    preparation: f['Préparation'],
    validation_target: f['Validation cible'],
    dependencies_complete: issue.blockedBy.nodes.every(completed),
    owner: issue.assignees.nodes[0]?.login,
    size: f.Size,
    started: f.Status === 'En cours',
    merged: linked.length > 0 && linked.every((p) => Boolean(p.merged_at)),
    pull_requests: active,
    acceptance,
    children_complete: issue.subIssues.nodes.every(completed),
    required_prs_complete: linked.length > 0 && linked.every((p) => Boolean(p.merged_at)),
    target_verified: Boolean(acceptance?.verified),
    abandoned: issue.state === 'CLOSED' && issue.stateReason === 'NOT_PLANNED',
  };
  let next = nextStatus(model),
    block = '';
  if (!model.dependencies_complete) block = 'Dépendances non acceptées';
  else if (active.some((p) => p.ci !== 'success')) block = 'CI requise en attente ou en échec';
  else if (issue.state === 'CLOSED' && issue.stateReason === 'COMPLETED' && !acceptance) {
    next = 'Validation';
    block = 'Clôture sans preuve d’acceptation vérifiée';
  }
  if (apply && next !== f.Status) setField(project, item.id, 'Status', next);
  if (apply && block !== (f.Blocage ?? '')) setField(project, item.id, 'Blocage', block);
  summaries.push({
    issue: issue.url,
    before: f.Status,
    after: next,
    blockage: block,
    applied: apply && next !== f.Status,
  });
}
console.log(JSON.stringify({ schema_version: 1, apply, items: summaries }, null, 2));
