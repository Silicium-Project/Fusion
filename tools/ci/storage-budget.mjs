/** Fail before an upload can consume the organization's temporary artifact budget. */
import { api, pages, repository } from '../lib/github.mjs';
import { Failure } from '../lib/process.mjs';
export function remainingBudget(usage, incoming, limit = 400 * 1024 ** 2) {
  if (![usage, incoming, limit].every(Number.isSafeInteger) || usage < 0 || incoming < 0 || usage + incoming >= limit) throw new Failure('Temporary artifact budget exhausted; delete transferred artifacts or wait for expiry. No VPS fallback.', 4);
  return limit - usage - incoming;
}
if (process.argv[1]?.endsWith('/storage-budget.mjs')) {
  // An organization-scoped read token is required: a repository token cannot prove org usage.
  const repos = pages('orgs/Silicium-Project/repos?type=all');
  let usage = 0;
  for (const repo of repos) {
    for (let page=1;;page++) {
      const rows=api(`repos/${repo.full_name}/actions/artifacts?per_page=100&page=${page}`).artifacts;
      usage+=rows.filter(x=>!x.expired).reduce((n,x)=>n+x.size_in_bytes,0);
      if(rows.length<100)break;
    }
  }
  const incoming=Number(process.env.SILICIUM_INCOMING_BYTES ?? 64*1024**2);
  console.log(JSON.stringify({schema_version:1,repository,usage_bytes:usage,remaining_bytes:remainingBudget(usage,incoming)}));
}
