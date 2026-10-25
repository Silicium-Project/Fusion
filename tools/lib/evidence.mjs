/** Acceptance requires live, independent review and qualification evidence, not a URL-shaped string. */
import { api, repository } from './github.mjs';
import { Failure } from './process.mjs';
export function acceptanceChecklistComplete(body) {
  const section=body.match(/## Conditions d[’']acceptation([^]*?)(?=\n## |$)/i)?.[1]
    ?? body.match(/## Critères d[’']acceptation([^]*?)(?=\n## |$)/i)?.[1];
  return Boolean(section && /- \[[xX]\]/.test(section) && !/- \[ \]/.test(section));
}
export function independentApproval(pr,reviews) {
  const latest=new Map();
  for(const r of reviews)if(r.user?.login && (!latest.has(r.user.login)||Date.parse(r.submitted_at)>Date.parse(latest.get(r.user.login).submitted_at)))latest.set(r.user.login,r);
  return [...latest.values()].some(r=>r.user.type==='User'&&r.user.login!==pr.user.login&&r.state==='APPROVED'&&r.commit_id===pr.head.sha);
}
export function inspectEvidence(url,target,issueUrl,{request=api}={}) {
  if(!['Documentation','CI','Dev','Prod'].includes(target))throw new Failure('Set an explicit validation target',3);
  const parsed=new URL(url),match=parsed.pathname.match(/^\/Silicium-Project\/Fusion\/actions\/runs\/([1-9][0-9]*)$/);
  if(parsed.protocol!=='https:'||parsed.host!=='github.com'||!match||parsed.search||parsed.hash)throw new Failure('Evidence must be a permanent Fusion Actions run URL',2);
  const run=request(`repos/${repository}/actions/runs/${match[1]}`);
  const expected=['Dev','Prod'].includes(target)?'.github/workflows/deploy.yml':'.github/workflows/ci.yml';
  if(run.conclusion!=='success'||run.head_branch!=='main'||run.head_repository?.full_name!==repository||run.path?.split('@')[0]!==expected)throw new Failure('Evidence is not a successful trusted main execution of the target workflow',3);
  if(expected.endsWith('/ci.yml')&&run.event!=='push')throw new Failure('A PR or partial manual CI is not acceptance evidence',3);
  const jobs=request(`repos/${repository}/actions/runs/${run.id}/jobs?per_page=100`).jobs;
  if(expected.endsWith('/ci.yml')&&!jobs.some(j=>j.name==='ci/required'&&j.conclusion==='success'&&j.status==='completed'))throw new Failure('Required CI gate did not execute',3);
  let sourceSha=run.head_sha;let deployment=null;
  if(['Dev','Prod'].includes(target)) {
    const environment=target==='Dev'?'development':'production';
    const deployments=request(`repos/${repository}/deployments?environment=${environment}&per_page=100`);
    deployment=deployments.find(d=>String(d.payload?.run_id)===String(run.id));
    if(!deployment||!deployment.payload?.manifest_digest||!deployment.payload?.release_id)throw new Failure('Missing deployment identity and manifest digest',3);
    const statuses=request(`repos/${repository}/deployments/${deployment.id}/statuses?per_page=100`);
    if(statuses[0]?.state!=='success')throw new Failure('Deployment is not currently successful',3);
    sourceSha=deployment.sha;
  }
  const query=`repo:${repository} is:pr in:body "${issueUrl}"`;
  const search=request(`search/issues?q=${encodeURIComponent(query)}&per_page=100`);
  if(search.total_count<1||search.total_count>100)throw new Failure('Link all contributing PRs to the issue by canonical URL',3);
  const prs=[];
  for(const item of search.items) {
    const pr=request(`repos/${repository}/pulls/${item.number}`);
    if(!pr.merged_at||pr.base.ref!=='main')throw new Failure('A contributing PR remains unmerged',3);
    const reviews=request(`repos/${repository}/pulls/${item.number}/reviews?per_page=100`);
    const authorizedReviews=reviews.filter(r=>r.user?.type==='User'&&['admin','maintain','write'].includes(request(`repos/${repository}/collaborators/${encodeURIComponent(r.user.login)}/permission`).permission));
    if(!independentApproval(pr,authorizedReviews))throw new Failure('Independent human approval of the current PR head is missing',3);
    const compare=request(`repos/${repository}/compare/${pr.merge_commit_sha}...${sourceSha}`);
    if(!['ahead','identical'].includes(compare.status))throw new Failure('Evidence does not contain every contributing change',3);
    prs.push(pr.html_url);
  }
  return {schema_version:1,verified:true,source_sha:sourceSha,run_id:run.id,target,evidence_url:parsed.href,issue_url:issueUrl,pr_urls:prs,deployment_id:deployment?.id??null};
}
