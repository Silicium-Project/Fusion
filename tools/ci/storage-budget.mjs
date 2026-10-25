/** Fail before an upload can consume the organization's temporary artifact budget. */
import { api, pages, repository } from '../lib/github.mjs';
import { Failure, run } from '../lib/process.mjs';
import { createPrivateKey, sign } from 'node:crypto';
export function requireCoverage(installation, org, repos) {
  if (installation.repository_selection !== 'all' || installation.account?.login !== 'Silicium-Project' || installation.suspended_at) {
    throw new Failure('Budget observer must be an active App installed on all organization repositories', 3);
  }
  if (!repos.length || new Set(repos.map(repo=>repo.id)).size !== repos.length
    || repos.some(repo=>repo.owner?.login !== 'Silicium-Project')) throw new Failure('Incomplete organization repository inventory', 3);
  if (Number.isInteger(org.total_private_repos) && repos.filter(repo=>repo.private).length !== org.total_private_repos) {
    throw new Failure('Budget token cannot see every private repository', 3);
  }
  if (Number.isInteger(org.public_repos) && repos.filter(repo=>!repo.private).length !== org.public_repos) {
    throw new Failure('Budget token cannot see every public repository', 3);
  }
}
function installationRecord() {
  const id=process.env.SILICIUM_BUDGET_INSTALLATION_ID;
  const client=process.env.SILICIUM_BUDGET_APP_CLIENT_ID,key=process.env.SILICIUM_BUDGET_APP_PRIVATE_KEY;
  if(!/^[1-9][0-9]*$/.test(id??'')||!client||!key)throw new Failure('Protected App identity is required to verify organization-wide budget coverage',3);
  const now=Math.floor(Date.now()/1000),encode=value=>Buffer.from(JSON.stringify(value)).toString('base64url');
  const payload=`${encode({alg:'RS256',typ:'JWT'})}.${encode({iat:now-60,exp:now+240,iss:client})}`;
  const jwt=`${payload}.${sign('RSA-SHA256',Buffer.from(payload),createPrivateKey(key)).toString('base64url')}`;
  // Authenticate as the App only for this metadata request. Never print or persist the JWT.
  return JSON.parse(run(['gh','api',`app/installations/${id}`],{env:{GH_TOKEN:jwt}}).stdout);
}
export function remainingBudget(usage, incoming, limit = 400 * 1024 ** 2) {
  if (![usage, incoming, limit].every(Number.isSafeInteger) || usage < 0 || incoming < 0 || usage + incoming >= limit) throw new Failure('Temporary artifact budget exhausted; delete transferred artifacts or wait for expiry. No VPS fallback.', 4);
  return limit - usage - incoming;
}
if (process.argv[1]?.endsWith('/storage-budget.mjs')) {
  // An organization-scoped read token is required: a repository token cannot prove org usage.
  const repos = pages('orgs/Silicium-Project/repos?type=all');
  const organization=api('orgs/Silicium-Project');
  if(process.env.GITHUB_ACTIONS==='true')requireCoverage(installationRecord(),organization,repos);
  else requireCoverage({repository_selection:'all',account:{login:'Silicium-Project'}},organization,repos);
  let usage = 0;
  for (const repo of repos) {
    for (let page=1;;page++) {
      const rows=api(`repos/${repo.full_name}/actions/artifacts?per_page=100&page=${page}`).artifacts;
      usage+=rows.filter(x=>!x.expired).reduce((n,x)=>n+x.size_in_bytes,0);
      if(rows.length<100)break;
    }
  }
  const incoming=Number(process.env.SILICIUM_INCOMING_BYTES ?? 64*1024**2);
  console.log(JSON.stringify({schema_version:1,repository,repositories_observed:repos.length,usage_bytes:usage,remaining_bytes:remainingBudget(usage,incoming)}));
}
