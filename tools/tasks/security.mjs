/** Scan reachable source history and validate active workflows. No secret values leave the scanner. */
import { resolve } from 'node:path';
import { readFileSync } from 'node:fs';
import { readJson, root, run, Failure } from '../lib/process.mjs';
import { installTool } from '../lib/download.mjs';
const v=readJson(resolve(root,'tools/config/toolchains.json'));
const dest=resolve(root,'.artifacts/tools');
const scanner=await installTool({repository:'gitleaks/gitleaks',version:v.gitleaks,name:'gitleaks',suffix:'linux_x64.tar.gz',destination:dest});
const linter=await installTool({repository:'rhysd/actionlint',version:v.actionlint,name:'actionlint',suffix:'linux_amd64.tar.gz',destination:dest});
for(const cmd of [[scanner,'git',root,'--log-opts=--all','--redact=100','--no-banner','--report-format=json','--report-path',resolve(root,'.artifacts/security.json')],[linter,'-shellcheck=']]){
 const p=run(cmd,{allowFailure:true,timeout:600_000});process.stdout.write(p.stdout);process.stderr.write(p.stderr);if(p.status)throw new Failure('Required security/workflow check failed');
}
console.log('Secret-history scan and active workflow validation passed.');

run(['node','tools/tasks/solana-key-audit.mjs']);
