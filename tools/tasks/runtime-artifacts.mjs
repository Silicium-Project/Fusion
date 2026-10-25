/** Collect already-built runtime executables for the image assembler. */
import { copyFileSync, mkdirSync, chmodSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { root, Failure, run } from '../lib/process.mjs';
const cwd=resolve(root,'network');
// The process E2E already built the first four; reputation has its own crate.
run(['cargo','build','--release','--locked','-p','reputation_bridge'],{cwd,timeout:1_800_000});
const dest=resolve(root,'.artifacts/build/network');mkdirSync(dest,{recursive:true});
for(const [name,out] of [['p2p_node','p2p_node'],['compute_daemon','compute_daemon'],['silicium-raytracer','silicium-raytracer'],['solana_worker_wallet','solana-worker-wallet'],['reputation_bridge','reputation_bridge']]) {
 const source=resolve(cwd,'target/release',name);
 if(!existsSync(source))throw new Failure(`Required runtime executable absent: ${name}`);
 copyFileSync(source,resolve(dest,out));chmodSync(resolve(dest,out),0o755);
}
console.log('Qualified runtime binaries collected without rebuilding the node.');
