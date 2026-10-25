/** Pure status policy plus bounded Project mutations. Closure always requires acceptance. */
import { api, pages, graphql, issueRef, requireWriter, repository } from './github.mjs';
import { Failure } from './process.mjs';
import { inspectEvidence, acceptanceChecklistComplete } from './evidence.mjs';

export function nextStatus(item) {
  if (item.hold || item.status === 'Arbitrage') return 'Arbitrage';
  if (item.abandoned) return 'Abandonné';
  if (item.acceptance?.verified && item.children_complete && item.required_prs_complete && item.target_verified) return 'Terminé';
  if (item.merged) return 'Validation';
  if (item.pull_requests?.length) {
    const current = item.pull_requests.filter((x) => !x.superseded && !x.closed);
    if (current.length && current.every((x) => !x.draft && x.ci === 'success' && !x.changes_requested)) return 'Revue';
    if (current.length) return 'En cours';
  }
  if (item.started) return 'En cours';
  if (item.preparation === 'Validée' && ['Documentation','CI','Dev','Prod'].includes(item.validation_target) && item.dependencies_complete && item.owner && item.size) return 'Prêt';
  if (item.status && ['Backlog', 'Prêt'].includes(item.status)) return 'Backlog';
  return 'À qualifier';
}
export function projectState() {
  const data = graphql(`query($cursor:String){organization(login:"Silicium-Project"){projectV2(number:12){id fields(first:100){nodes{... on ProjectV2Field{id name} ... on ProjectV2SingleSelectField{id name options{id name}}}} items(first:100,after:$cursor){nodes{id fieldValues(first:40){nodes{... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2SingleSelectField{id name}}} ... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2Field{id name}}}}} content{... on Issue{id number url state stateReason body repository{nameWithOwner} assignees(first:10){nodes{login}} blockedBy(first:100){nodes{id state stateReason}} subIssues(first:100){nodes{id state stateReason}}}}}pageInfo{hasNextPage endCursor}}}}}`);
  const project = data.organization.projectV2; const items = [...project.items.nodes];
  let cursor = project.items.pageInfo;
  while (cursor.hasNextPage) {
    const page = graphql(`query($cursor:String){organization(login:"Silicium-Project"){projectV2(number:12){items(first:100,after:$cursor){nodes{id fieldValues(first:40){nodes{... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2SingleSelectField{id name}}} ... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2Field{id name}}}}} content{... on Issue{id number url state stateReason body repository{nameWithOwner} assignees(first:10){nodes{login}} blockedBy(first:100){nodes{id state stateReason}} subIssues(first:100){nodes{id state stateReason}}}}}pageInfo{hasNextPage endCursor}}}}}`, { cursor: cursor.endCursor }).organization.projectV2.items;
    items.push(...page.nodes); cursor = page.pageInfo;
  }
  return { ...project, items };
}
export function fieldValues(item) {
  return Object.fromEntries(item.fieldValues.nodes.filter((x) => x.field).map((x) => [x.field.name, x.name ?? x.text]));
}
export function setField(project, itemId, fieldName, value) {
  const field = project.fields.nodes.find((x) => x.name === fieldName);
  if (!field) throw new Failure(`Missing Project field ${fieldName}; run the reviewed administration setup`, 3);
  const input = field.options ? { singleSelectOptionId: field.options.find((x) => x.name === value)?.id } : { text: value };
  if (field.options && !input.singleSelectOptionId) throw new Failure(`Missing Project option ${fieldName}/${value}`, 3);
  return graphql('mutation($project:ID!,$item:ID!,$field:ID!,$value:ProjectV2FieldValue!){updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:$value}){projectV2Item{id}}}', { project: project.id, item: itemId, field: field.id, value: input });
}
export function startIssue(url, apply = false) {
  const ref = issueRef(url), viewer = requireWriter(ref.repo), project = projectState();
  const item = project.items.find((x) => x.content?.url === ref.url);
  if (!item) throw new Failure('Issue is not in Project 12', 3);
  const f = fieldValues(item), issue = item.content;
  if (!['Documentation','CI','Dev','Prod'].includes(f['Validation cible']) || f.Status !== 'Prêt' || f['Préparation'] !== 'Validée' || issue.state !== 'OPEN') throw new Failure('Issue is not prepared and ready', 3);
  if (issue.blockedBy.nodes.some((x) => x.state !== 'CLOSED' || x.stateReason !== 'COMPLETED')) throw new Failure('Open dependencies remain', 3);
  if (!issue.assignees.nodes.some((x) => x.login === viewer.login)) throw new Failure('Assign the issue to the contributor before starting it', 3);
  const busy = project.items.filter((x) => x.id !== item.id && fieldValues(x).Status === 'En cours' && x.content?.assignees?.nodes.some((a) => a.login === viewer.login));
  if (busy.length) throw new Failure('WIP limit reached: finish or explicitly arbitrate the active tranche', 3);
  if (apply) setField(project, item.id, 'Status', 'En cours');
  return { schema_version: 1, operation: 'issue.start', issue: url, status: apply ? 'applied' : 'planned', target: 'En cours' };
}
export function acceptIssue(url, evidence, { apply = false, humanApproved = false } = {}) {
  const ref = issueRef(url), viewer = requireWriter(ref.repo);
  if (viewer.type !== 'User' || !humanApproved) throw new Failure('Explicit human approval is required; agents must not self-accept', 3);
  const project = projectState(), item = project.items.find((x) => x.content?.url === ref.url);
  if (!item || !['Validation','Terminé'].includes(fieldValues(item).Status)) throw new Failure('Issue must be in Validation', 3);
  if (item.content.subIssues.nodes.some((x) => x.state !== 'CLOSED' || x.stateReason !== 'COMPLETED')) throw new Failure('Required children remain open', 3);
  if (!acceptanceChecklistComplete(item.content.body)) throw new Failure('Complete the acceptance checklist before requesting closure', 3);
  const verification = inspectEvidence(evidence, fieldValues(item)['Validation cible'], ref.url);
  const body = `<!-- silicium-acceptance:v1 ${JSON.stringify(verification)} -->\nAcceptation humaine explicite par @${viewer.login}.\nPreuve : ${verification.evidence_url}`;
  if (apply) {
    const existing=pages(`repos/${ref.repo}/issues/${ref.number}/comments`).some(c=>c.user?.login===viewer.login&&c.body===body);
    if(!existing)api(`repos/${ref.repo}/issues/${ref.number}/comments`, { method: 'POST', body: { body } });
    setField(project, item.id, 'Status', 'Terminé');
    api(`repos/${ref.repo}/issues/${ref.number}`, { method: 'PATCH', body: { state: 'closed', state_reason: 'completed' } });
  }
  return { schema_version: 1, operation: 'issue.accept', status: apply ? 'applied' : 'planned', issue: url, evidence: verification.evidence_url, actor: viewer.login };
}
