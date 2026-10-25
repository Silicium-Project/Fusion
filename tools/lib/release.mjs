/** Release planning is read-only; deployment requests go through GitHub exclusively. */
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { api, verifiedRun, requireWriter, repository } from './github.mjs';
import { root, git, readJson, Failure } from './process.mjs';
import { requireManifest, packageVersions } from './manifest.mjs';
export function releasePlan({ channel = 'dev', version, run: runId, sha = git('rev-parse', 'HEAD') } = {}) {
  if (!['dev','prod'].includes(channel) || !version) throw new Failure('Provide --channel dev|prod and --version', 2);
  const versions = packageVersions(version);
  if (channel === 'prod' && version.includes('-')) throw new Failure('Production requires a stable version', 2);
  if (channel === 'dev' && !version.includes('-dev.')) throw new Failure('Development requires a unique dev sequence', 2);
  if (!/^[a-f0-9]{40}$/.test(sha)) throw new Failure('Use an exact source SHA', 2);
  const qualification = runId ? verifiedRun(runId, { sha }) : null;
  return { schema_version: 1, operation: 'release.plan', status: qualification ? 'qualified' : 'requires_qualification', source_sha: sha, channel, version, package_versions: versions,
    release_id: `${channel}-${version}-${sha.slice(0,12)}`, qualification_run: qualification?.html_url ?? null };
}
export function requestDeploy(path, { environment = 'dev', apply = false } = {}) {
  const manifest = requireManifest(readJson(resolve(path)));
  if (!['dev','prod'].includes(environment) || manifest.channel !== environment) throw new Failure('Candidate/environment mismatch', 2);
  const viewer = requireWriter();
  verifiedRun(manifest.qualification.run_id, { sha: manifest.source_sha });
  const result = { schema_version: 1, operation: 'deploy.request', status: apply ? 'requested' : 'planned', release_id: manifest.release_id, environment, workflow: 'deploy.yml', actor: viewer.login };
  if (apply) api(`repos/${repository}/actions/workflows/deploy.yml/dispatches`, { method: 'POST', body: { ref: 'main', inputs: { release_id: manifest.release_id, environment } } });
  return result;
}
