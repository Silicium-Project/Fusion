/** Artifact names are selected by the trusted planner, never supplied by a pull request event. */
import { resolve } from 'node:path';
import { root, run, readJson, Failure } from '../lib/process.mjs';
import { verifiedRun, repository } from '../lib/github.mjs';
const id=process.env.CI_RUN;verifiedRun(id,{sha:run(['git','rev-parse','HEAD']).stdout.trim()});
const inputs=readJson(resolve(root,'.artifacts/candidate/inputs.json'));
const locations={api:'.artifacts/build/api',web:'apps/web/.output',network:'.artifacts/build/network'};
for(const [component,name] of Object.entries(inputs.artifacts)) {
 if(component==='node')continue;
 if(!locations[component])throw new Failure('Unexpected build component');
 run(['gh','run','download',String(id),'--repo',repository,'--name',name,'--dir',locations[component]],{timeout:600_000});
}
