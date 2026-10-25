/** Explicit GitHub runner bootstrap. Never installs operating-system packages on a user's PC. */
import { resolve } from 'node:path';
import { existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { run, root, readJson, Failure } from '../lib/process.mjs';
const suite = process.argv[2];
if (process.env.GITHUB_ACTIONS !== 'true') throw new Failure('Runner bootstrap is CI-only; use dev doctor locally', 2);
const tools = readJson(resolve(root, 'tools/config/toolchains.json'));
const output = (args, options = {}) => { const r=run(args,{timeout:2_400_000,...options});process.stdout.write(r.stdout);process.stderr.write(r.stderr);return r; };
const rust = ['network','network-wasm','network-integration','node-native','node-windows','solana'].includes(suite);
if (rust) {
  output(['rustup','toolchain','install',suite==='solana'?tools.rust_solana:tools.rust,'--profile','minimal','--component','clippy,rustfmt']);
}
if (process.platform === 'linux' && ['node-native','solana'].includes(suite)) {
  output(['sudo','apt-get','update']);
  const packages = suite === 'node-native'
    ? ['libgtk-3-dev','libwebkit2gtk-4.1-dev','libayatana-appindicator3-dev','librsvg2-dev','patchelf','pkg-config']
    : ['pkg-config','libssl-dev','libudev-dev','clang','cmake'];
  output(['sudo','apt-get','install','-y','--no-install-recommends',...packages]);
}
if (['network-integration','infrastructure'].includes(suite)) output(['python3','-m','pip','install','-r','network/requirements-dev.txt']);
if (suite === 'solana') {
  output(['npm','install','--global',`yarn@${tools.yarn}`]);
  const home = resolve(process.env.RUNNER_TOOL_CACHE, 'silicium-solana', tools.solana);
  mkdirSync(home,{recursive:true});
  // Versioned upstream installer, never a moving stable release.
  const url=`https://release.anza.xyz/v${tools.solana}/install`;
  output(['curl','--fail','--location','--retry','2',url,'--output',resolve(home,'install.sh')]);
  output(['bash',resolve(home,'install.sh'),'--data-dir',home,'--no-modify-path']);
  const bin=resolve(home,'active_release/bin');
  const anchorRoot=resolve(process.env.RUNNER_TOOL_CACHE,'silicium-anchor',tools.anchor);
  const env={RUSTUP_TOOLCHAIN:tools.rust_solana};
  const pins=readJson(resolve(root,'tools/config/upstreams.json'));
  if (!existsSync(resolve(anchorRoot,'bin/anchor'))) output(['cargo','install','--locked','--git','https://github.com/coral-xyz/anchor','--rev',pins.anchor,'anchor-cli','--root',anchorRoot],{env});
  appendFileSync(process.env.GITHUB_PATH,`${bin}\n${resolve(anchorRoot,'bin')}\n`);
}
console.log(`Runner prepared for ${suite}`);
