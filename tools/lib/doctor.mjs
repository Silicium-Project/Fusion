/** Discover prerequisite failures without installing or changing a developer machine. */
import { readJson, run, root } from './process.mjs';
import { resolve } from 'node:path';
export function doctor({ profile = 'tooling' } = {}) {
  const versions = readJson(resolve(root, 'tools/config/toolchains.json'));
  const definitions = {
    node: ['node', '--version'], git: ['git', '--version'], gh: ['gh', '--version'],
    npm: ['npm', '--version'], cargo: ['cargo', '--version'], go: ['go', 'version'],
    docker: ['docker', 'version', '--format', '{{.Server.Version}}'],
    anchor: ['anchor', '--version'], solana: ['solana', '--version'], python: ['python3', '--version'],
  };
  const profiles = { tooling: ['node','git'], web: ['node','npm','git'], api: ['go','git'], node: ['node','npm','cargo','git'], network: ['cargo','python','git'], solana: ['node','cargo','anchor','solana','git'], delivery: ['node','gh','docker','git'] };
  const wanted = profile === 'all' ? Object.keys(definitions) : profiles[profile];
  if (!wanted) throw new Error(`Unknown profile ${profile}`);
  const checks = wanted.map((name) => {
    const r = run(definitions[name], { allowFailure: true, timeout: 15_000 });
    const actual = (r.stdout || r.stderr).split('\n')[0].trim();
    const pinned=versions[name==='cargo'?'rust':name]??null;
    const found=actual.match(/\b(\d+\.\d+(?:\.\d+)?)/)?.[1];
    const compatible=!pinned||found===pinned||(name==='python'&&found?.startsWith(pinned+'.'));
    return { tool: name, available: r.status === 0, compatible: r.status === 0 && compatible, actual: r.status ? null : actual, pinned, error: r.status ? r.error ?? r.stderr.trim() : !compatible?'Install the pinned toolchain before CI qualification':null };
  });
  return { schema_version: 1, profile, status: checks.every((x) => x.compatible) ? 'success' : 'blocked', checks, instructions: 'docs/development/commands.md' };
}
