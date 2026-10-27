import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  nextStatus,
  projectBlockage,
  dependencyAccepted,
  issueStartBlockers,
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
test('issue start accepts a fully prepared, assigned issue without open blockers', () => {
  assert.deepEqual(
    issueStartBlockers({
      fields: {
        Status: 'Prêt',
        Préparation: 'Validée',
        'Validation cible': 'CI',
        Size: 'S',
      },
      issue: { state: 'OPEN', assignees: { nodes: [{ login: 'member' }] } },
      viewerLogin: 'member',
    }),
    [],
  );
});
test('issue start reports every missing preparation, dependency, ownership and WIP condition', () => {
  const blockers = issueStartBlockers({
    fields: {
      Status: 'Backlog',
      Préparation: 'À compléter',
      'Validation cible': 'Inconnue',
      Size: '',
      Phase: 'HOLD',
    },
    issue: { state: 'CLOSED', assignees: { nodes: [] } },
    viewerLogin: 'Luis1454',
    dependencies: [{ url: 'https://github.com/Silicium-Project/Workbench/issues/41' }],
    busyItems: [{ content: { url: 'https://github.com/Silicium-Project/Workbench/issues/42' } }],
  });
  assert.match(blockers.join('; '), /Validation cible/);
  assert.match(blockers.join('; '), /Status must be Prêt/);
  assert.match(blockers.join('; '), /Préparation must be Validée/);
  assert.match(blockers.join('; '), /Size must be set/);
  assert.match(blockers.join('; '), /HOLD requires explicit arbitration/);
  assert.match(blockers.join('; '), /Issue must be OPEN/);
  assert.match(blockers.join('; '), /issues\/41/);
  assert.match(blockers.join('; '), /Assign this issue to @Luis1454/);
  assert.match(blockers.join('; '), /issues\/42/);
});
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
test('Project sync preserves human blockers and replaces stale automatic blockers', () => {
  const issueUrl = 'https://github.com/Silicium-Project/Workbench/issues/31';
  const prUrl = 'https://github.com/Silicium-Project/Workbench/pull/32';
  const manual = 'Quota Actions privé épuisé ; plafond de dépense maintenu à zéro.';
  const base = {
    dependencies_complete: false,
    dependencies: [
      { url: 'https://github.com/Silicium-Project/Workbench/issues/33', accepted: false },
    ],
    children_complete: true,
    children: [],
    pull_requests: [{ url: prUrl, draft: true, ci: 'pending', merged: false, closed: false }],
    linked_pull_requests: [{ url: prUrl, merged: false, closed: false }],
    required_prs_complete: false,
    closedCompleted: false,
    acceptance: null,
    merged: false,
    validation_target: 'CI',
    preparation: 'Validée',
    owner: 'member',
    size: 'S',
  };
  const first = projectBlockage(
    {
      ...base,
      manual_blockage: [
        manual,
        'Dépendances non acceptées',
        'CI requise en attente ou en échec',
        'Clôture sans preuve d’acceptation vérifiée',
      ].join(' · '),
    },
    issueUrl,
    'En cours',
  );
  assert.match(first, new RegExp(manual.replaceAll('.', '\\.')));
  assert.deepEqual(
    first.split(' · ').filter((value) => !value.startsWith('[auto] ')),
    [manual],
  );
  assert.match(first, /\[auto\] Dépendances non acceptées/);

  const refreshed = projectBlockage(
    {
      ...base,
      dependencies_complete: true,
      dependencies: [],
      manual_blockage: first,
      pull_requests: [{ url: prUrl, draft: false, ci: 'success', merged: false, closed: false }],
    },
    issueUrl,
    'Revue',
  );
  assert.match(refreshed, new RegExp(manual.replaceAll('.', '\\.')));
  assert.doesNotMatch(refreshed, /\[auto\] Dépendances non acceptées/);
  assert.match(refreshed, /\[auto\] Revue humaine en attente/);
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
test('public Project sync dry-run uses aggregate output and hides private issue data', () => {
  const output = projectSyncOutput({
    apply: false,
    publicWorkflow: true,
    items: [
      {
        issue: 'https://github.com/Silicium-Project/planning-private/issues/4',
        status_changed: true,
        blockage_changed: true,
        blockage: 'private issue title and dependency',
      },
    ],
  });
  assert.deepEqual(output, {
    schema_version: 1,
    apply: false,
    processed_items: 1,
    predicted_status_updates: 1,
    predicted_blockage_updates: 1,
  });
  assert.doesNotMatch(JSON.stringify(output), /planning-private|private issue title|issues\/4/);
});
test('failed public Project sync hides private issue and API diagnostics', () => {
  const output = projectSyncFailureOutput({
    apply: true,
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
test('failed public Project dry-run identifies read-only mode and hides private diagnostics', () => {
  const output = projectSyncFailureOutput({
    apply: false,
    error: Object.assign(new Error('private issue title and token'), { exitCode: 3 }),
    processedItems: 2,
    statusUpdates: 0,
    blockageUpdates: 0,
  });
  assert.equal(output.apply, false);
  assert.equal(output.status, 'failed');
  assert.doesNotMatch(JSON.stringify(output), /private issue title|token/);
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
  for (const permission of [
    'permission-actions: read',
    'permission-checks: read',
    'permission-contents: read',
    'permission-deployments: read',
    'permission-issues: read',
    'permission-pull-requests: read',
  ])
    assert.ok(workflow.includes(permission), `missing least-privilege token scope: ${permission}`);
  assert.match(workflow, /default: dry-run/);
  assert.match(
    workflow,
    /event_name != 'workflow_dispatch' \|\| github\.ref == 'refs\/heads\/main'/,
  );
  assert.match(workflow, /inputs\.mode == 'dry-run' && 'read' \|\| 'write'/);
  assert.match(
    workflow,
    /SILICIUM_PROJECT_AUTOMATION_ENABLED == '1'[\s\S]*inputs\.mode == 'dry-run'/,
  );
  assert.match(workflow, /node tools\/ci\/project-sync\.mjs --apply/);
  assert.match(workflow, /node tools\/ci\/project-sync\.mjs\n/);
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
