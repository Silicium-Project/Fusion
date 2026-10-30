/** Process and file boundaries shared by local tools and GitHub Actions. */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { dirname, resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export class Failure extends Error {
  constructor(message, code = 1) {
    super(message);
    this.exitCode = code;
  }
}
export function run(
  command,
  { cwd = root, env = {}, input, allowFailure = false, timeout = 600_000 } = {},
) {
  let [exe, ...args] = command;
  if (process.platform === 'win32' && ['npm', 'npx'].includes(exe)) {
    const cli = resolve(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js');
    if (!existsSync(cli))
      throw new Failure(
        'npm CLI missing beside node.exe; repair the documented Node installation.',
        2,
      );
    args = [cli, ...(exe === 'npx' ? ['exec', '--'] : []), ...args];
    exe = process.execPath;
  }
  const p = spawnSync(exe, args, {
    cwd,
    env: { ...process.env, ...env },
    input,
    encoding: 'utf8',
    timeout,
    maxBuffer: 32 * 1024 * 1024,
    windowsHide: true,
  });
  const result = {
    status: p.status ?? 1,
    stdout: p.stdout ?? '',
    stderr: p.stderr ?? '',
    error: p.error?.message,
  };
  if (result.status && !allowFailure)
    throw new Failure(
      `${command[0]} failed (${result.status}): ${result.error ?? result.stderr.slice(-3000)}`,
    );
  return result;
}
/** Run with output streamed to this process, so a hung child leaves a readable log. */
export function runLive(command, { cwd = root, env = {}, timeout = 600_000 } = {}) {
  const [exe, ...args] = command;
  const p = spawnSync(exe, args, {
    cwd,
    env: { ...process.env, ...env },
    stdio: 'inherit',
    timeout,
    windowsHide: true,
  });
  return {
    status: p.status ?? 1,
    timedOut: p.error?.code === 'ETIMEDOUT',
    error: p.error?.message,
  };
}
export const git = (...args) => run(['git', ...args]).stdout.trim();
export const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'));
export function writeJson(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = `${path}.${process.pid}.tmp`;
  writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  renameSync(temp, path);
}
export function inside(path) {
  const abs = resolve(root, path),
    rel = relative(root, abs);
  if (isAbsolute(rel) || rel === '..' || rel.startsWith('../') || rel.startsWith('..\\'))
    throw new Failure('Path escapes repository.', 2);
  return abs;
}
export function parseArgs(argv) {
  const args = [],
    options = {};
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (!token.startsWith('--')) {
      args.push(token);
      continue;
    }
    const [key, inline] = token.slice(2).split(/=(.*)/s, 2);
    if (Object.hasOwn(options, key)) throw new Failure(`Duplicate option --${key}`, 2);
    options[key] = inline ?? (argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true);
  }
  return { args, options };
}
export function print(value, json = false) {
  console.log(json || typeof value !== 'string' ? JSON.stringify(value, null, 2) : value);
}
