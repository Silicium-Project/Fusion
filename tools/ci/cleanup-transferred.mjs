/** Only the successful release's temporary artifacts are eligible for deletion. */
import { api, repository } from '../lib/github.mjs';
import { readJson, root, Failure } from '../lib/process.mjs';
import { resolve } from 'node:path';
const m=readJson(resolve(root,'.artifacts/publish/manifest.json'));
const release=api(`repos/${repository}/releases/tags/${m.release_id}`);
if(release.draft||!m.assets.every(a=>release.assets.some(b=>a.name===b.name&&a.size===b.size&&b.digest===`sha256:${a.sha256}`)))throw new Failure('Durable transfer digest not confirmed; keep temporary artifacts');
const names=new Set(['candidate-input','candidate-images','installers-Linux','installers-Windows','unsigned-Windows']);
const rows=api(`repos/${repository}/actions/runs/${process.env.GITHUB_RUN_ID}/artifacts?per_page=100`).artifacts;
for(const a of rows.filter(x=>names.has(x.name)))api(`repos/${repository}/actions/artifacts/${a.id}`,{method:'DELETE'});
// Compiled CI outputs are durable inside the published OCI images/installers.
const qualified=api(`repos/${repository}/actions/runs/${m.qualification.run_id}/artifacts?per_page=100`).artifacts;
for(const a of qualified.filter(x=>['qualification-plan','web-output','api-binary','network-binaries','node-ui-output'].includes(x.name)||x.name.startsWith('report-')))api(`repos/${repository}/actions/artifacts/${a.id}`,{method:'DELETE'});
