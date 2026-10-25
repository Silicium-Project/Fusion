/** Qualify actual network processes on the runner, never against the VPS. */
import { run, root } from '../lib/process.mjs';
import { resolve } from 'node:path';
run(['bash', 'ci/e2e.sh'], { cwd: resolve(root, 'network'), timeout: 1_800_000 });
console.log('Network process integration passed.');
