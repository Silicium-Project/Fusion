/** Pure status policy plus bounded Project mutations. Closure always requires acceptance. */
import { api, pages, graphql, issueRef, requireWriter, repository } from './github.mjs';
import { Failure } from './process.mjs';
import { inspectEvidence, acceptanceChecklistComplete } from './evidence.mjs';

export const integrationRepository = 'Silicium-Project/Integration';

export function projectRequiredCheckName(repo) {
  if (repo === repository) return 'ci/required';
  if (repo === integrationRepository) return 'integration/required';
  throw new Failure(`Project sync does not inspect pull requests from ${repo}`, 3);
}

export function projectRequiredCheckConclusion(checkRuns, repo) {
  const requiredName = projectRequiredCheckName(repo);
  const required = checkRuns.filter(
    (check) => check.name === requiredName && check.app?.slug === 'github-actions',
  );
  return required.length === 1 ? required[0].conclusion : 'pending';
}

export function nextStatus(item) {
  if (item.hold || item.status === 'Arbitrage') return 'Arbitrage';
  if (item.abandoned) return 'Abandonné';
  if (
    item.acceptance?.verified &&
    item.dependencies_complete &&
    item.children_complete &&
    item.required_prs_complete &&
    item.target_verified
  )
    return 'Terminé';
  if (item.closedCompleted) return 'Validation';
  if (item.merged) return 'Validation';
  if (item.pull_requests?.length) {
    const current = item.pull_requests.filter((x) => !x.superseded && !x.closed);
    if (
      current.length &&
      current.every((x) => !x.draft && x.ci === 'success' && !x.changes_requested)
    )
      return 'Revue';
    if (current.length) return 'En cours';
  }
  if (item.started) return 'En cours';
  if (
    item.preparation === 'Validée' &&
    ['Documentation', 'CI', 'Dev', 'Prod'].includes(item.validation_target) &&
    item.dependencies_complete &&
    item.owner &&
    item.size
  )
    return 'Prêt';
  if (item.status && ['Backlog', 'Prêt'].includes(item.status)) return 'Backlog';
  return 'À qualifier';
}
export function projectBlockage(item, issueUrl, next) {
  const blockers = [];
  const manual = String(item.manual_blockage ?? '')
    .split(' · ')
    .map((value) => value.trim())
    .filter(Boolean)
    .filter(
      (value) =>
        !value.startsWith('[auto] ') &&
        ![
          'Dépendances non acceptées',
          'CI requise en attente ou en échec',
          'Clôture sans preuve d’acceptation vérifiée',
        ].includes(value),
    );
  const linkList = (items, fallback) => {
    const urls = items.map((x) => x.url).filter(Boolean);
    const shown = urls.slice(0, 2);
    const remaining = urls.length - shown.length;
    return `${shown.length ? shown.join(', ') : fallback}${remaining > 0 ? ` (+${remaining})` : ''}`;
  };
  if (!item.dependencies_complete)
    blockers.push(
      `Dépendances non acceptées: ${linkList(
        item.dependencies.filter((x) => !x.accepted),
        issueUrl,
      )}`,
    );
  if (!item.children_complete)
    blockers.push(
      `Sous-tâches non acceptées: ${linkList(
        item.children.filter((x) => !x.accepted),
        issueUrl,
      )}`,
    );
  const failing = (item.pull_requests ?? []).filter(
    (x) => !x.merged && (x.ci !== 'success' || x.changes_requested),
  );
  if (failing.length)
    blockers.push(
      `CI ou revue en attente: ${linkList(
        failing.map((x) => ({ url: x.check_url || x.url })),
        issueUrl,
      )}`,
    );
  if ((next === 'Validation' || item.closedCompleted) && !item.required_prs_complete) {
    const unmerged = (item.linked_pull_requests ?? []).filter((x) => !x.merged);
    blockers.push(
      `${unmerged.length ? 'PR non fusionnées' : 'Aucune PR liée'}: ${linkList(unmerged, issueUrl)}`,
    );
  }
  const closedUnmerged = (item.linked_pull_requests ?? []).filter((x) => x.closed && !x.merged);
  if (closedUnmerged.length)
    blockers.push(`PR fermées sans fusion à arbitrer: ${linkList(closedUnmerged, issueUrl)}`);
  if (item.closedCompleted && !item.acceptance?.verified)
    blockers.push(`Clôture sans preuve d’acceptation vérifiée: ${issueUrl}`);
  else if ((item.merged || next === 'Validation') && !item.acceptance?.verified)
    blockers.push(
      `Validation de la cible ${item.validation_target || 'non définie'} en attente: ${issueUrl}`,
    );
  if (next === 'Revue') {
    const reviewable = (item.pull_requests ?? []).filter(
      (pullRequest) => !pullRequest.draft && pullRequest.ci === 'success',
    );
    blockers.push(`Revue humaine en attente: ${linkList(reviewable, issueUrl)}`);
  }
  if (next === 'En cours' && !(item.pull_requests ?? []).some((pullRequest) => !pullRequest.closed))
    blockers.push(`Travail en cours sans PR active: ${issueUrl}`);
  if (['Backlog', 'À qualifier'].includes(next)) {
    const missing = [];
    if (item.preparation !== 'Validée') missing.push('préparation');
    if (!['Documentation', 'CI', 'Dev', 'Prod'].includes(item.validation_target))
      missing.push('cible');
    if (!item.owner) missing.push('responsable');
    if (!item.size) missing.push('taille');
    if (missing.length)
      blockers.push(`Préparation incomplète (${missing.join(', ')}): ${issueUrl}`);
  }
  return [...manual, ...blockers.map((blocker) => `[auto] ${blocker}`)].join(' · ');
}
export function dependencyAccepted(child, itemsById) {
  const item = itemsById.get(child.id);
  return (
    child.state === 'CLOSED' &&
    child.stateReason === 'COMPLETED' &&
    Boolean(item) &&
    fieldValues(item).Status === 'Terminé'
  );
}
export function issueStartBlockers({
  fields,
  issue,
  viewerLogin,
  dependencies = [],
  busyItems = [],
}) {
  const blockers = [];
  const show = (value) => (value == null || value === '' ? '(missing)' : String(value));
  const validTargets = ['Documentation', 'CI', 'Dev', 'Prod'];
  if (!validTargets.includes(fields['Validation cible']))
    blockers.push(
      `Validation cible must be one of ${validTargets.join(', ')} (found ${show(fields['Validation cible'])})`,
    );
  if (fields.Status !== 'Prêt') blockers.push(`Status must be Prêt (found ${show(fields.Status)})`);
  if (fields['Préparation'] !== 'Validée')
    blockers.push(`Préparation must be Validée (found ${show(fields['Préparation'])})`);
  if (!fields.Size) blockers.push('Size must be set');
  if (fields.Phase === 'HOLD') blockers.push('HOLD requires explicit arbitration');
  if (issue.state !== 'OPEN') blockers.push(`Issue must be OPEN (found ${show(issue.state)})`);

  const links = (items) => {
    const urls = items.map((item) => item.url).filter(Boolean);
    const shown = urls.slice(0, 3);
    const remaining = urls.length - shown.length;
    return `${shown.join(', ') || '(issue URL unavailable)'}${remaining > 0 ? ` (+${remaining})` : ''}`;
  };
  if (dependencies.length)
    blockers.push(`Dependencies need accepted completion: ${links(dependencies)}`);
  if (!issue.assignees.nodes.some((assignee) => assignee.login === viewerLogin))
    blockers.push(`Assign this issue to @${viewerLogin} before starting it`);
  if (busyItems.length)
    blockers.push(
      `WIP limit reached; active tranche(s): ${links(busyItems.map((item) => item.content ?? {}))}`,
    );
  return blockers;
}
export function assertCompleteRelations(items) {
  for (const item of items.filter((item) => item.content?.url))
    for (const name of ['blockedBy', 'subIssues'])
      if (
        item.content[name]?.pageInfo?.hasNextPage !== false ||
        !Array.isArray(item.content[name]?.nodes)
      )
        throw new Failure(
          `Project relationship data is incomplete for ${item.content.url}/${name}; expand pagination before changing its state`,
          3,
        );
}
export function projectState() {
  const data = graphql(`
    query ($cursor: String) {
      organization(login: "Silicium-Project") {
        projectV2(number: 12) {
          id
          fields(first: 100) {
            nodes {
              ... on ProjectV2Field {
                id
                name
              }
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
            }
          }
          items(first: 100, after: $cursor) {
            nodes {
              id
              fieldValues(first: 40) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field {
                      ... on ProjectV2SingleSelectField {
                        id
                        name
                      }
                    }
                  }
                  ... on ProjectV2ItemFieldTextValue {
                    text
                    field {
                      ... on ProjectV2Field {
                        id
                        name
                      }
                    }
                  }
                }
              }
              content {
                ... on Issue {
                  id
                  number
                  url
                  state
                  stateReason
                  body
                  repository {
                    nameWithOwner
                  }
                  assignees(first: 10) {
                    nodes {
                      login
                    }
                  }
                  blockedBy(first: 100) {
                    pageInfo {
                      hasNextPage
                    }
                    nodes {
                      id
                      url
                      state
                      stateReason
                    }
                  }
                  subIssues(first: 100) {
                    pageInfo {
                      hasNextPage
                    }
                    nodes {
                      id
                      url
                      state
                      stateReason
                    }
                  }
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
  `);
  const project = data.organization.projectV2;
  const items = [...project.items.nodes];
  let cursor = project.items.pageInfo;
  while (cursor.hasNextPage) {
    const page = graphql(
      `
        query ($cursor: String) {
          organization(login: "Silicium-Project") {
            projectV2(number: 12) {
              items(first: 100, after: $cursor) {
                nodes {
                  id
                  fieldValues(first: 40) {
                    nodes {
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field {
                          ... on ProjectV2SingleSelectField {
                            id
                            name
                          }
                        }
                      }
                      ... on ProjectV2ItemFieldTextValue {
                        text
                        field {
                          ... on ProjectV2Field {
                            id
                            name
                          }
                        }
                      }
                    }
                  }
                  content {
                    ... on Issue {
                      id
                      number
                      url
                      state
                      stateReason
                      body
                      repository {
                        nameWithOwner
                      }
                      assignees(first: 10) {
                        nodes {
                          login
                        }
                      }
                      blockedBy(first: 100) {
                        pageInfo {
                          hasNextPage
                        }
                        nodes {
                          id
                          url
                          state
                          stateReason
                        }
                      }
                      subIssues(first: 100) {
                        pageInfo {
                          hasNextPage
                        }
                        nodes {
                          id
                          url
                          state
                          stateReason
                        }
                      }
                    }
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
          }
        }
      `,
      { cursor: cursor.endCursor },
    ).organization.projectV2.items;
    items.push(...page.nodes);
    cursor = page.pageInfo;
  }
  assertCompleteRelations(items);
  return { ...project, items };
}
export function fieldValues(item) {
  return Object.fromEntries(
    item.fieldValues.nodes.filter((x) => x.field).map((x) => [x.field.name, x.name ?? x.text]),
  );
}
export function projectSyncOutput({
  apply,
  items,
  statusUpdates = 0,
  blockageUpdates = 0,
  publicWorkflow = process.env.GITHUB_ACTIONS === 'true',
}) {
  if (!apply && !publicWorkflow) return { schema_version: 1, apply, items };
  if (!apply)
    return {
      schema_version: 1,
      apply,
      processed_items: items.length,
      predicted_status_updates: items.filter((item) => item.status_changed).length,
      predicted_blockage_updates: items.filter((item) => item.blockage_changed).length,
    };
  return {
    schema_version: 1,
    apply,
    processed_items: items.length,
    status_updates: statusUpdates,
    blockage_updates: blockageUpdates,
  };
}
export function projectSyncFailureOutput({
  apply = true,
  error,
  processedItems,
  statusUpdates,
  blockageUpdates,
}) {
  const failureCode = Number.isInteger(error?.exitCode) ? error.exitCode : 1;
  return {
    schema_version: 1,
    apply,
    status: 'failed',
    failure_kind: failureCode === 4 ? 'rate_limit' : 'reconciliation',
    processed_items: processedItems,
    status_updates: statusUpdates,
    blockage_updates: blockageUpdates,
    diagnostics: 'Per-item diagnostics are suppressed in public workflow logs.',
  };
}
export function setField(project, itemId, fieldName, value) {
  const field = project.fields.nodes.find((x) => x.name === fieldName);
  if (!field)
    throw new Failure(
      `Missing Project field ${fieldName}; run the reviewed administration setup`,
      3,
    );
  const input = field.options
    ? { singleSelectOptionId: field.options.find((x) => x.name === value)?.id }
    : { text: value };
  if (field.options && !input.singleSelectOptionId)
    throw new Failure(`Missing Project option ${fieldName}/${value}`, 3);
  return graphql(
    'mutation($project:ID!,$item:ID!,$field:ID!,$value:ProjectV2FieldValue!){updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:$value}){projectV2Item{id}}}',
    { project: project.id, item: itemId, field: field.id, value: input },
  );
}
export function startIssue(url, apply = false) {
  const ref = issueRef(url),
    viewer = requireWriter(ref.repo),
    project = projectState();
  const item = project.items.find((x) => x.content?.url === ref.url);
  if (!item) throw new Failure('Issue is not in Project 12', 3);
  const f = fieldValues(item),
    issue = item.content;
  const itemsById = new Map(
    project.items.filter((x) => x.content?.id).map((x) => [x.content.id, x]),
  );
  const busy = project.items.filter(
    (x) =>
      x.id !== item.id &&
      fieldValues(x).Status === 'En cours' &&
      x.content?.assignees?.nodes.some((a) => a.login === viewer.login),
  );
  const dependencies = issue.blockedBy.nodes.filter(
    (child) => !dependencyAccepted(child, itemsById),
  );
  const blockers = issueStartBlockers({
    fields: f,
    issue,
    viewerLogin: viewer.login,
    dependencies,
    busyItems: busy,
  });
  if (blockers.length) throw new Failure(`Issue is not ready: ${blockers.join('; ')}`, 3);
  if (apply) setField(project, item.id, 'Status', 'En cours');
  return {
    schema_version: 1,
    operation: 'issue.start',
    issue: url,
    status: apply ? 'applied' : 'planned',
    target: 'En cours',
  };
}
export function acceptIssue(url, evidence, { apply = false, humanApproved = false } = {}) {
  const ref = issueRef(url),
    viewer = requireWriter(ref.repo);
  if (viewer.type !== 'User' || !humanApproved)
    throw new Failure('Explicit human approval is required; agents must not self-accept', 3);
  const project = projectState(),
    item = project.items.find((x) => x.content?.url === ref.url);
  if (!item || !['Validation', 'Terminé'].includes(fieldValues(item).Status))
    throw new Failure('Issue must be in Validation', 3);
  if (fieldValues(item).Phase === 'HOLD' || ref.repo.endsWith('/planning-private'))
    throw new Failure('HOLD requires a separate explicit arbitration', 3);
  const itemsById = new Map(
    project.items.filter((x) => x.content?.id).map((x) => [x.content.id, x]),
  );
  if (
    ![...item.content.subIssues.nodes, ...item.content.blockedBy.nodes].every((child) =>
      dependencyAccepted(child, itemsById),
    )
  )
    throw new Failure(
      'Required children and dependencies must have accepted completion in the Project',
      3,
    );
  if (!acceptanceChecklistComplete(item.content.body))
    throw new Failure('Complete the acceptance checklist before requesting closure', 3);
  const verification = inspectEvidence(evidence, fieldValues(item)['Validation cible'], ref.url);
  const body = `<!-- silicium-acceptance:v1 ${JSON.stringify(verification)} -->\nAcceptation humaine explicite par @${viewer.login}.\nPreuve : ${verification.evidence_url}`;
  if (apply) {
    const existing = pages(`repos/${ref.repo}/issues/${ref.number}/comments`).some(
      (c) => c.user?.login === viewer.login && c.body === body,
    );
    if (!existing)
      api(`repos/${ref.repo}/issues/${ref.number}/comments`, { method: 'POST', body: { body } });
    setField(project, item.id, 'Status', 'Terminé');
    api(`repos/${ref.repo}/issues/${ref.number}`, {
      method: 'PATCH',
      body: { state: 'closed', state_reason: 'completed' },
    });
  }
  return {
    schema_version: 1,
    operation: 'issue.accept',
    status: apply ? 'applied' : 'planned',
    issue: url,
    evidence: verification.evidence_url,
    actor: viewer.login,
  };
}
