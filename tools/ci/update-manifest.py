#!/usr/bin/env python3
"""Keep the installed updater's Ed25519 trust anchor and canonical payload."""
import base64,datetime,hashlib,json,os,subprocess,tempfile
from pathlib import Path

def payload(release):
    return ('\n'.join(['silicium-update-v1',release['channel'],release['platform'],release['version'],release['sha256'],str(release['size_bytes']),release['url'],release['content_id'],''])).encode()

def build(snapshot,identity,base,trust):
    key=os.environ.get('UPDATE_SIGNING_KEY','')
    if not key:raise RuntimeError('Missing existing Ed25519 UPDATE_SIGNING_KEY; automatic key replacement is forbidden')
    releases=[];suffix='-dev'if identity['channel']=='dev'else''
    with tempfile.TemporaryDirectory(prefix='silicium-updater-sign-')as temp:
        temp=Path(temp);private=temp/'private.pem';private.write_text(key);os.chmod(private,0o600)
        public=subprocess.run(['openssl','pkey','-in',str(private),'-pubout','-outform','DER'],capture_output=True,check=True).stdout[-32:]
        if hashlib.sha256(public).hexdigest()!=trust['key_id'] or base64.b64encode(public).decode()!=trust['public_key_base64']:
            raise RuntimeError('Updater trust anchor mismatch; restore the existing key or review an explicit trust migration')
        for platform,name in [('windows-x86_64',f'silicium-node-windows{suffix}.exe'),('linux-x86_64',f'silicium-node-linux{suffix}.AppImage')]:
            path=snapshot/name
            if not path.is_file():raise RuntimeError(f'Missing updater artifact for {platform}')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            release={'version':identity['version'],'build':identity['source_sha'],'channel':identity['channel'],'platform':platform,'url':f'{base}/{name}','sha256':digest,'content_id':digest,'size_bytes':path.stat().st_size,'auto_install':True,'check_interval_seconds':30 if identity['channel']=='dev' else 21600,'signing_key_id':trust['key_id']}
            message=temp/'message';message.write_bytes(payload(release));signature=temp/'signature'
            subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(private),'-in',str(message),'-out',str(signature)],check=True,capture_output=True)
            pub=temp/'public.pem';pub.write_bytes(subprocess.run(['openssl','pkey','-in',str(private),'-pubout'],capture_output=True,check=True).stdout)
            subprocess.run(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(pub),'-in',str(message),'-sigfile',str(signature)],check=True,capture_output=True)
            release['signature']=base64.b64encode(signature.read_bytes()).decode();releases.append(release)
    result={'schema_version':1,'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'publisher_channel':identity['channel'],'publisher_build':identity['source_sha'],'channels':{identity['channel']:releases[0]},'releases':releases}
    (snapshot/'update-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
