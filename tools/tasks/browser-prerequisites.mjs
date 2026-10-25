/** Browser installation is explicit and confined to disposable GitHub runners. */
import { resolve } from 'node:path';
import { run, root, Failure } from '../lib/process.mjs';
const cwd=resolve(root,'apps/web');
if(process.env.GITHUB_ACTIONS==='true') {
 const p=run(['npm','exec','--','playwright','install','--with-deps','chromium'],{cwd,timeout:600_000});
 process.stdout.write(p.stdout);process.stderr.write(p.stderr);
} else {
 const p=run(['node','--input-type=module','-e',"import{chromium}from'@playwright/test';import{existsSync}from'node:fs';process.exit(existsSync(chromium.executablePath())?0:1)"],{cwd,allowFailure:true});
 if(p.status)throw new Failure('Chromium missing: install the documented Playwright browser explicitly; no OS package is installed by dev test.',2);
}
