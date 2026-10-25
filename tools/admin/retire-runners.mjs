/** Retire CI registration only; do not stop application services or interrupt busy jobs. */
import { api } from '../lib/github.mjs';
import { Failure } from '../lib/process.mjs';
const apply = process.argv.includes('--apply');
const entries = [];
for (const name of ['Fusion', 'Network', 'BackEnd', 'FrontEnd']) {
  const repo = `Silicium-Project/${name}`;
  const permissions = api(`repos/${repo}/actions/permissions`);
  if (permissions.enabled) throw new Failure(`Suspend ${repo} Actions before retiring runners`);
  const runners = api(`repos/${repo}/actions/runners?per_page=100`);
  if (runners.total_count > 100)
    throw new Failure('Unexpected runner inventory; review pagination');
  for (const runner of runners.runners) {
    if (runner.busy)
      throw new Failure(`Runner ${repo}/${runner.id} is busy; let its operation finish`);
    entries.push({ repository: repo, id: runner.id, name: runner.name, status: runner.status });
  }
}
if (apply)
  for (const r of entries)
    api(`repos/${r.repository}/actions/runners/${r.id}`, { method: 'DELETE' });
console.log(JSON.stringify({ schema_version: 1, apply, registrations: entries }, null, 2));
