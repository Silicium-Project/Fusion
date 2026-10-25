/** Privileged workflows may consume only a successful main push from the CI workflow. */
import { verifiedRun } from '../lib/github.mjs';
import { appendFileSync } from 'node:fs';
const r=verifiedRun(process.env.QUALIFICATION_RUN,{sha:process.env.QUALIFICATION_SHA||undefined});
if(process.env.GITHUB_OUTPUT) appendFileSync(process.env.GITHUB_OUTPUT,`sha=${r.head_sha}\nsource_sha=${r.head_sha}\nrun=${r.id}\n`);
console.log(JSON.stringify({source_sha:r.head_sha,run_id:r.id,status:'qualified'}));
