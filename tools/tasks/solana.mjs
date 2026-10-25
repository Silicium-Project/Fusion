/** Disposable localnet, explicit genesis program ID, one SBF build and no Devnet access. */
import { run, root, Failure, readJson } from '../lib/process.mjs';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, rmSync, readFileSync, openSync, closeSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createServer } from 'node:net';
const cwd=resolve(root,'chain/solana'),home=mkdtempSync(resolve(tmpdir(),'silicium-localnet-'));
const binary=resolve(cwd,'target/deploy/solana_layer.so');
const digest=()=>createHash('sha256').update(readFileSync(binary)).digest('hex');
let validator;let log;
async function freePort() {
  const server=createServer();await new Promise((ok,bad)=>server.once('error',bad).listen(0,'127.0.0.1',ok));
  const port=server.address().port;await new Promise(ok=>server.close(ok));return port;
}
try {
 const wallet=resolve(home,'wallet.json');
 run(['solana-keygen','new','--no-bip39-passphrase','--silent','--outfile',wallet]);
 const pubkey=run(['solana-keygen','pubkey',wallet]).stdout.trim();
 const env={ANCHOR_WALLET:wallet,RUSTUP_TOOLCHAIN:'1.89.0'};
 const build=run(['anchor','build','--provider.cluster','localnet'],{cwd,env,timeout:2_400_000});
 process.stdout.write(build.stdout);process.stderr.write(build.stderr);
 if(!existsSync(binary))throw new Failure('SBF build missing');
 const before=digest(),idl=readJson(resolve(cwd,'target/idl/solana_layer.json'));
 const declared=readFileSync(resolve(cwd,'programs/solana-layer/src/lib.rs'),'utf8').match(/declare_id!\("([1-9A-HJ-NP-Za-km-z]+)"\)/)?.[1];
 if(!declared||idl.address!==declared)throw new Failure('IDL/program address mismatch');
 const port=await freePort(),faucet=await freePort();
 const url=`http://127.0.0.1:${port}`;
 log=openSync(resolve(home,'validator.log'),'w',0o600);
 validator=spawn('solana-test-validator',['--reset','--quiet','--ledger',resolve(home,'ledger'),'--rpc-port',String(port),'--faucet-port',String(faucet),'--bind-address','127.0.0.1','--rpc-bind-address','127.0.0.1','--mint',pubkey,'--bpf-program',declared,binary],{cwd,stdio:['ignore',log,log]});
 validator.on('error',()=>{});
 let ready=false;
 for(let i=0;i<90;i++) {
  if(validator.exitCode!==null||validator.signalCode)throw new Failure('Disposable validator stopped before readiness');
  try {const response=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'getHealth'}),signal:AbortSignal.timeout(1000)});ready=(await response.json()).result==='ok';}catch{}
  if(ready)break;await new Promise(ok=>setTimeout(ok,500));
 }
 if(!ready)throw new Failure('Disposable validator did not become ready');
 const result=run(['anchor','test','--skip-build','--skip-deploy','--skip-local-validator','--provider.cluster',url,'--provider.wallet',wallet],{cwd,env:{...env,ANCHOR_PROVIDER_URL:url},timeout:2_400_000,allowFailure:true});
 process.stdout.write(result.stdout);process.stderr.write(result.stderr);
 if(digest()!==before)throw new Failure('Program changed between build and qualification');
 if(result.status)throw new Failure('Anchor localnet qualification failed');
 console.log(`Qualified SBF sha256: ${before}`);
}finally{
 if(validator&&validator.exitCode===null){validator.kill('SIGTERM');await new Promise(ok=>{validator.once('exit',ok);setTimeout(()=>{validator.kill('SIGKILL');ok();},5000).unref();});}
 if(log!==undefined)closeSync(log);rmSync(home,{recursive:true,force:true});
}
