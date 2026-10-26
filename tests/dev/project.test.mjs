import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  nextStatus,
  projectBlockage,
  dependencyAccepted,
  assertCompleteRelations,
  projectSyncFailureOutput,
  projectSyncOutput,
} from '../../tools/lib/project.mjs';
const ready = {
  status: 'Backlog',
  validation_target: 'CI',
  preparation: 'Validée',
  dependencies_complete: true,
  owner: 'member',
  size: 'S',
};
test('readiness requires preparation and dependencies', () => {
  assert.equal(nextStatus(ready), 'Prêt');
  assert.equal(nextStatus({ ...ready, dependencies_complete: false }), 'Backlog');
  assert.equal(nextStatus({ ...ready, preparation: 'À compléter' }), 'Backlog');
});
test('merge never means accepted', () => assert.equal(nextStatus({ merged: true }), 'Validation'));
test('all active PRs must be ready and qualified for review', () => {
  const a = { draft: false, ci: 'success' };
  assert.equal(nextStatus({ pull_requests: [a] }), 'Revue');
  assert.equal(nextStatus({ pull_requests: [a, { draft: false, ci: 'failure' }] }), 'En cours');
});
test('HOLD survives CI, merges and closure', () =>
  assert.equal(
    nextStatus({ hold: true, merged: true, acceptance: { verified: true } }),
    'Arbitrage',
  ));
test('acceptance requires target, children and all changes', () => {
  const a = {
    acceptance: { verified: true },
    dependencies_complete: true,
    children_complete: true,
    required_prs_complete: true,
    target_verified: true,
  };
  assert.equal(nextStatus(a), 'Terminé');
  for (const k of [
    'dependencies_complete',
    'children_complete',
    'required_prs_complete',
    'target_verified',
  ])
    assert.notEqual(nextStatus({ ...a, [k]: false }), 'Terminé');
});
test('a previously completed issue without valid acceptance stays in Validation', () => {
  assert.equal(
    nextStatus({ status: 'Terminé', closedCompleted: true, dependencies_complete: false }),
    'Validation',
  );
});
test('Project blockages include links to the dependencies and CI evidence', () => {
  const blockage = projectBlockage(
    {
      dependencies_complete: false,
      dependencies: [
        { url: 'https://github.com/Silicium-Project/Workbench/issues/12', accepted: false },
      ],
      children_complete: true,
      children: [],
      pull_requests: [
        {
          url: 'https://github.com/Silicium-Project/Workbench/pull/13',
          check_url: 'https://github.com/Silicium-Project/Workbench/actions/runs/14',
          ci: 'failure',
          changes_requested: false,
          merged: false,
        },
      ],
      linked_pull_requests: [
        { url: 'https://github.com/Silicium-Project/Workbench/pull/13', merged: false },
      ],
      required_prs_complete: false,
      closedCompleted: false,
      acceptance: null,
      merged: false,
      validation_target: 'CI',
      preparation: 'Validée',
      owner: 'member',
      size: 'S',
    },
    'https://github.com/Silicium-Project/Workbench/issues/11',
    'En cours',
  );
  assert.match(blockage, /issues\/12/);
  assert.match(blockage, /actions\/runs\/14/);
});
test('Project blockages expose blocked subtask and review evidence', () => {
  const issueUrl = 'https://github.com/Silicium-Project/Workbench/issues/21';
  const childUrl = 'https://github.com/Silicium-Project/Workbench/issues/22';
  const prUrl = 'https://github.com/Silicium-Project/Workbench/pull/23';
  const blocked = projectBlockage(
    {
      dependencies_complete: true,
      children_complete: false,
      children: [{ url: childUrl, accepted: false }],
      pull_requests: [],
      linked_pull_requests: [],
      required_prs_complete: false,
      closedCompleted: false,
      acceptance: null,
      merged: false,
      validation_target: 'CI',
      preparation: 'Validée',
      owner: 'member',
      size: 'S',
    },
    issueUrl,
    'En cours',
  );
  assert.match(blocked, /Sous-tâches non acceptées/);
  assert.match(blocked, new RegExp(childUrl.replaceAll('/', '\\/')));

  const review = projectBlockage(
    {
      dependencies_complete: true,
      children_complete: true,
      children: [],
      pull_requests: [{ url: prUrl, draft: false, ci: 'success', changes_requested: false }],
      linked_pull_requests: [{ url: prUrl, merged: false }],
      required_prs_complete: false,
      closedCompleted: false,
      acceptance: null,
      merged: false,
      validation_target: 'CI',
      preparation: 'Validée',
      owner: 'member',
      size: 'S',
    },
    issueUrl,
    'Revue',
  );
  assert.match(review, /Revue humaine en attente/);
  assert.match(review, new RegExp(prUrl.replaceAll('/', '\\/')));

  const closedPr = projectBlockage(
    {
      dependencies_complete: true,
      children_complete: true,
      children: [],
      pull_requests: [],
      linked_pull_requests: [{ url: prUrl, merged: false, closed: true }],
      required_prs_complete: false,
      closedCompleted: false,
      acceptance: null,
      merged: false,
      validation_target: 'CI',
      preparation: 'Validée',
      owner: 'member',
      size: 'S',
    },
    issueUrl,
    'En cours',
  );
  assert.match(closedPr, /PR fermées sans fusion à arbitrer/);
  assert.match(closedPr, new RegExp(prUrl.replaceAll('/', '\\/')));
});
test('applied Project sync output contains only aggregate data', () => {
  const output = projectSyncOutput({
    apply: true,
    items: [{ issue: 'https://github.com/Silicium-Project/Workbench/issues/1' }],
    statusUpdates: 2,
    blockageUpdates: 3,
  });
  assert.deepEqual(output, {
    schema_version: 1,
    apply: true,
    processed_items: 1,
    status_updates: 2,
    blockage_updates: 3,
  });
  assert.doesNotMatch(JSON.stringify(output), /github\.com|issues\/1/);
});
test('failed public Project sync hides private issue and API diagnostics', () => {
  const output = projectSyncFailureOutput({
    error: Object.assign(
      new Error(
        'private issue title https://github.com/Silicium-Project/planning-private/issues/4 token',
      ),
      { exitCode: 4 },
    ),
    processedItems: 7,
    statusUpdates: 2,
    blockageUpdates: 3,
  });
  assert.equal(output.failure_kind, 'rate_limit');
  assert.deepEqual(
    {
      processed_items: output.processed_items,
      status_updates: output.status_updates,
      blockage_updates: output.blockage_updates,
    },
    { processed_items: 7, status_updates: 2, blockage_updates: 3 },
  );
  assert.doesNotMatch(JSON.stringify(output), /private issue title|planning-private|token/);
});
test('public Project sync gates untrusted workflow sources and checks out only main', () => {
  const workflow = readFileSync(
    new URL('../../.github/workflows/project-sync.yml', import.meta.url),
    'utf8',
  );
  assert.match(
    workflow,
    /event_name != 'pull_request_target'[\s\S]*head\.repo\.full_name == github\.repository/,
  );
  assert.match(
    workflow,
    /event_name != 'workflow_run'[\s\S]*head_repository\.full_name == github\.repository/,
  );
  assert.match(workflow, /ref: main/);
  assert.match(workflow, /persist-credentials: 'false'/);
  assert.match(workflow, /repositories: Workbench,planning-private/);
});
test('abandoned work is not counted as delivered', () =>
  assert.equal(nextStatus({ abandoned: true }), 'Abandonné'));
test('closed children require accepted Project completion and cannot disappear from the inventory', () => {
  const child = { id: 'child', state: 'CLOSED', stateReason: 'COMPLETED' };
  const item = (status) => ({
    fieldValues: { nodes: [{ field: { name: 'Status' }, name: status }] },
  });
  assert.equal(dependencyAccepted(child, new Map([['child', item('Terminé')]])), true);
  for (const status of ['Validation', 'Abandonné', 'Arbitrage'])
    assert.equal(dependencyAccepted(child, new Map([['child', item(status)]])), false);
  assert.equal(dependencyAccepted(child, new Map()), false);
  assert.equal(
    dependencyAccepted(
      { ...child, stateReason: 'NOT_PLANNED' },
      new Map([['child', item('Terminé')]]),
    ),
    false,
  );
});
test('truncated or missing relationship pages cannot silently satisfy dependencies', () => {
  const complete = { nodes: [], pageInfo: { hasNextPage: false } };
  const content = {
    url: 'https://github.com/Silicium-Project/Fusion/issues/1',
    blockedBy: complete,
    subIssues: complete,
  };
  assert.doesNotThrow(() => assertCompleteRelations([{ content }]));
  for (const incomplete of [{ nodes: [] }, { nodes: [], pageInfo: { hasNextPage: true } }])
    assert.throws(
      () => assertCompleteRelations([{ content: { ...content, blockedBy: incomplete } }]),
      /incomplete/,
    );
});
