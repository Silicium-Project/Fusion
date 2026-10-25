import { api, repository, requireWriter } from './github.mjs';
import { Failure } from './process.mjs';
export function diagnosticRequest(environment, apply = false) {
  if (!['dev', 'prod'].includes(environment))
    throw new Failure('Provide --environment dev|prod', 2);
  const request = {
    schema_version: 1,
    operation: 'ops.diagnose',
    status: apply ? 'requested' : 'planned',
    workflow: 'diagnostics.yml',
    ref: 'main',
    environment,
    effects: 'read-only host observations; creates a short-lived GitHub report',
  };
  if (apply) {
    requireWriter();
    if (api(`repos/${repository}`).private)
      throw new Failure(
        'Actions remain suspended for a private integration checkout; no VPS or paid runner fallback',
        4,
      );
    api(`repos/${repository}/actions/workflows/diagnostics.yml/dispatches`, {
      method: 'POST',
      body: { ref: 'main', inputs: { environment } },
    });
  }
  return request;
}
