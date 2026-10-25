import test from 'node:test';
import assert from 'node:assert/strict';
import { validateManifest, packageVersions } from '../../tools/lib/manifest.mjs';
const sha='a'.repeat(40);
const candidate=()=>({schema_version:1,source_sha:sha,channel:'dev',version:'0.3.0-dev.1',release_id:`dev-0.3.0-dev.1-${sha.slice(0,12)}`,qualification:{source_sha:sha,status:'success',run_id:123},components:{...Object.fromEntries(['api','web','network'].map(name=>[name,{source_sha:sha,image:`ghcr.io/silicium-project/${name}@sha256:${'b'.repeat(64)}`}])),node:{source_sha:sha,version:'0.3.0-dev.1',channel:'dev'}},assets:['packages.tar.gz','deployment.tar.gz','qualification.json'].map(name=>({name,sha256:'c'.repeat(64),size:12}))});
test('complete immutable identity validates',()=>assert.deepEqual(validateManifest(candidate()),[]));
test('mutable images, stale qualification and prod prereleases fail',()=>{
 for(const edit of [m=>m.components.api.image='api:latest',m=>m.qualification.source_sha='b'.repeat(40),m=>m.channel='prod']){const m=candidate();edit(m);assert.ok(validateManifest(m).length);}
});
test('asset names cannot escape the snapshot',()=>{const m=candidate();m.assets=[{name:'../wallet',sha256:'a'.repeat(64),size:1}];assert.ok(validateManifest(m).length);});
test('versions retain prerelease ordering and unique Windows sequence',()=>{
 assert.deepEqual(packageVersions('0.3.0-dev.12'),{semver:'0.3.0-dev.12',deb:'0.3.0~dev.12',rpm:'0.3.0~dev.12',rpm_release:'1',windows:'0.3.0.12'});
 assert.equal(packageVersions('0.3.0').windows,'0.3.0.65535');
 for(const v of ['0.3.0+hidden','0.3.0-dev.0','0.3.0-dev.65536','$(id)'])assert.throws(()=>packageVersions(v));
});
