/** Reconcile trusted GitHub metadata; never check out or execute PR content. */
import { api, pages, repository } from '../lib/github.mjs';
import {
  projectState,
  fieldValues,
  nextStatus,
  projectBlockage,
  setField,
  dependencyAccepted,
  projectSyncFailureOutput,
  projectSyncOutput,
} from '../lib/project.mjs';
import { inspectEvidence } from '../lib/evidence.mjs';
import { referencesIssue } from '../lib/issue-links.mjs';

const apply = process.argv.includes('--apply');
const summaries = [];
let statusUpdates = 0;
let blockageUpdates = 0;
try {
  const project = projectState();
  const items = new Map(project.items.filter((x) => x.content?.url).map((x) => [x.content.id, x]));
  const prs = pages(`repos/${repository}/pulls?state=all`);
  for (const item of items.values()) {
    const issue = item.content,
      f = fieldValues(item);
    const hold =
      issue.repository.nameWithOwner.endsWith('/planning-private') ||
      f.Phase === 'HOLD' ||
      f.Status === 'Arbitrage';
    if (hold) continue;
    const linked = prs.filter((p) => referencesIssue(p.body, issue.url));
    const active = [];
    for (const p of linked.filter((x) => !x.merged_at && x.state === 'open')) {
      if (p.head.repo?.full_name !== repository) continue;
      const checks = api(
        `repos/${repository}/commits/${p.head.sha}/check-runs?filter=latest&per_page=100`,
      ).check_runs;
      const required = checks.filter(
        (c) => c.name === 'ci/required' && c.app?.slug === 'github-actions',
      );
      const reviews = pages(`repos/${repository}/pulls/${p.number}/reviews`);
      const latest = new Map();
      for (const r of reviews) if (r.user?.login) latest.set(r.user.login, r);
      active.push({
        url: p.html_url,
        draft: p.draft,
        closed: false,
        ci: required.length === 1 ? required[0].conclusion : 'pending',
        check_url: required[0]?.html_url,
        changes_requested: [...latest.values()].some((r) => r.state === 'CHANGES_REQUESTED'),
        merged: false,
      });
    }
    const completed = (child) => dependencyAccepted(child, items);
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
      dependencies: issue.blockedBy.nodes.map((child) => ({
        url: child.url,
        accepted: completed(child),
      })),
      children: issue.subIssues.nodes.map((child) => ({
        url: child.url,
        accepted: completed(child),
      })),
      owner: issue.assignees.nodes[0]?.login,
      size: f.Size,
      started: f.Status === 'En cours',
      merged: linked.length > 0 && linked.every((p) => Boolean(p.merged_at)),
      pull_requests: active,
      linked_pull_requests: linked.map((p) => ({
        url: p.html_url,
        merged: Boolean(p.merged_at),
        closed: p.state === 'closed',
      })),
      acceptance,
      children_complete: issue.subIssues.nodes.every(completed),
      required_prs_complete: linked.length > 0 && linked.every((p) => Boolean(p.merged_at)),
      target_verified: Boolean(acceptance?.verified),
      closedCompleted: issue.state === 'CLOSED' && issue.stateReason === 'COMPLETED',
      abandoned: issue.state === 'CLOSED' && issue.stateReason === 'NOT_PLANNED',
    };
    const next = nextStatus(model);
    const block = projectBlockage({ ...model, manual_blockage: f.Blocage }, issue.url, next);
    if (apply && next !== f.Status) {
      setField(project, item.id, 'Status', next);
      statusUpdates++;
    }
    if (apply && block !== (f.Blocage ?? '')) {
      setField(project, item.id, 'Blocage', block);
      blockageUpdates++;
    }
    summaries.push({
      issue: issue.url,
      before: f.Status,
      after: next,
      blockage: block,
      status_changed: next !== f.Status,
      blockage_changed: block !== (f.Blocage ?? ''),
      applied: apply && next !== f.Status,
    });
  }
  console.log(
    JSON.stringify(
      projectSyncOutput({ apply, items: summaries, statusUpdates, blockageUpdates }),
      null,
      2,
    ),
  );
} catch (error) {
  if (apply || process.env.GITHUB_ACTIONS === 'true') {
    console.error(
      JSON.stringify(
        projectSyncFailureOutput({
          apply,
          error,
          processedItems: summaries.length,
          statusUpdates,
          blockageUpdates,
        }),
        null,
        2,
      ),
    );
  } else {
    console.error(error?.stack ?? String(error));
  }
  process.exitCode = Number.isInteger(error?.exitCode) ? error.exitCode : 1;
}
