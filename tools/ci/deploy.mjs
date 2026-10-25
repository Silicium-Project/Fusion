/** Request records and transfer immutable release assets through GitHub. */
import { readFileSync, mkdirSync, writeFileSync, chmodSync } from 'node:fs';
import { resolve } from 'node:path';
import { api, repository, verifiedRun } from '../lib/github.mjs';
import { root, run, readJson, Failure } from '../lib/process.mjs';
import { requireManifest, sha256 } from '../lib/manifest.mjs';
const dir=resolve(root,'.artifacts/deploy');mkdirSync(dir,{recursive:true});
const rid=process.env.RELEASE_ID,channel=process.env.RELEASE_CHANNEL;
if(!['dev','prod'].includes(channel)||!new RegExp(`^${channel}-[0-9]+\\.[0-9]+\\.[0-9]+(?:-dev\\.[0-9]+)?-[a-f0-9]{12}$`).test(rid??''))throw new Failure('Invalid deployment identity');
run(['gh','release','download',rid,'--repo',repository,'--dir',dir]);
run(['gpgv','--keyring',resolve(root,'contracts/trust/release.gpg'),resolve(dir,'manifest.json.asc'),resolve(dir,'manifest.json')]);
const m=requireManifest(readJson(resolve(dir,'manifest.json')));
if(m.release_id!==rid||m.channel!==channel)throw new Failure('Release/channel mismatch');
verifiedRun(m.qualification.run_id,{sha:m.source_sha});
for(const a of m.assets)if(sha256(readFileSync(resolve(dir,a.name)))!==a.sha256)throw new Failure('Asset integrity failure');
const digest=sha256(readFileSync(resolve(dir,'manifest.json')));
const env=channel==='dev'?'development':'production';
const deployment=api(`repos/${repository}/deployments`,{method:'POST',body:{ref:m.source_sha,environment:env,auto_merge:false,required_contexts:[],transient_environment:channel==='dev',production_environment:channel==='prod',payload:{run_id:process.env.GITHUB_RUN_ID,release_id:rid,manifest_digest:digest}}});
const status=(state)=>api(`repos/${repository}/deployments/${deployment.id}/statuses`,{method:'POST',body:{state,log_url:`https://github.com/${repository}/actions/runs/${process.env.GITHUB_RUN_ID}`,auto_inactive:state==='success'}});
status('in_progress');
try {
 const host=process.env.DEPLOY_SSH_HOST,user=process.env.DEPLOY_SSH_USER;
 if(!/^[a-zA-Z0-9.-]+$/.test(host??'')||!/^silicium-deploy$/.test(user??''))throw new Failure('Configure the restricted deployment identity');
 const key=resolve(dir,'ssh.key'),known=resolve(dir,'known_hosts');
 if(!process.env.DEPLOY_SSH_KEY||!process.env.DEPLOY_SSH_KNOWN_HOSTS)throw new Failure('Missing protected SSH configuration');
 writeFileSync(key,process.env.DEPLOY_SSH_KEY,{mode:0o600});writeFileSync(known,process.env.DEPLOY_SSH_KNOWN_HOSTS,{mode:0o600});
 const ssh=['-i',key,'-o',`UserKnownHostsFile=${known}`,'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=15'];
 const dest=`${user}@${host}`,remote=`/var/lib/silicium-delivery/incoming/${rid}`;
 run(['ssh',...ssh,dest,`mkdir -p ${remote}`]);
 run(['scp',...ssh,resolve(dir,'manifest.json'),resolve(dir,'manifest.json.asc'),...m.assets.map(a=>resolve(dir,a.name)),`${dest}:${remote}/`],{timeout:600_000});
 // This root-owned entry point is installed separately; do not execute uploaded scripts as root.
 const result=run(['ssh',...ssh,dest,`sudo -n /usr/local/sbin/silicium-apply --candidate ${remote} --channel ${channel}`],{timeout:600_000});
 const applied=JSON.parse(result.stdout);
 if(applied.release_id!==rid||applied.manifest_digest!==digest)throw new Failure('Host did not confirm the expected candidate');
 status('success');console.log(JSON.stringify({schema_version:1,status:'success',release_id:rid,manifest_digest:digest,deployment_id:deployment.id}));
}catch(e){status('failure');throw e;}
