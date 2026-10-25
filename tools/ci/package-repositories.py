#!/usr/bin/env python3
"""Build a complete signed snapshot on GitHub. Never generate client trust keys."""
import gzip, hashlib, json, os, re, shutil, subprocess, tarfile, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def command(args, *, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True).stdout

def fingerprint(home):
    rows=command(['gpg','--batch','--homedir',str(home),'--with-colons','--list-secret-keys']).decode().splitlines()
    return [r.split(':')[9] for r in rows if r.startswith('fpr:')]

def import_key(home, name, pinned=None):
    value=os.environ.get(name+'_KEY','')
    expected=os.environ.get(name+'_FINGERPRINT','').upper()
    if not value or not re.fullmatch(r'[A-F0-9]{40,64}',expected):
        raise RuntimeError(f'Missing protected {name}_KEY or pinned {name}_FINGERPRINT')
    if pinned is not None and expected!=pinned:raise RuntimeError(f'{name}: configured trust differs from the reviewed client key')
    home.mkdir(mode=0o700)
    # Key contents are passed via stdin and never appear in process arguments or logs.
    subprocess.run(['gpg','--batch','--homedir',str(home),'--import'],input=value.encode(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if expected not in fingerprint(home):raise RuntimeError(f'{name}: trust fingerprint mismatch')
    return expected

def sign(home,key,file,clear=False):
    args=['gpg','--batch','--yes','--homedir',str(home),'--local-user',key]
    if clear:args+=['--output',str(file.parent/'InRelease'),'--clearsign',str(file)]
    else:args+=['--armor','--output',str(file)+'.asc','--detach-sign',str(file)]
    command(args)

def main():
    if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('Signing is restricted to protected GitHub jobs')
    identity=json.loads((ROOT/'.artifacts/candidate/identity.json').read_text())
    rid=identity['release_id'];channel=identity['channel'];suite='dev' if channel=='dev' else 'stable'
    source=ROOT/'.artifacts/installers';publish=ROOT/'.artifacts/publish';publish.mkdir(parents=True,exist_ok=True)
    snapshot=ROOT/'.artifacts/snapshot';snapshot.mkdir(exist_ok=False)
    downloads=os.environ.get('DOWNLOAD_BASE_URL','').rstrip('/')
    if not downloads.startswith('https://'):raise RuntimeError('An explicit HTTPS download origin is required')
    # Immutable URLs prevent a refresh spanning two snapshots from mixing metadata and payloads.
    base=f'{downloads}/snapshots/{rid}'
    with tempfile.TemporaryDirectory(prefix='silicium-sign-') as temp:
        temp=Path(temp);apt_home=temp/'apt';rpm_home=temp/'rpm'
        trust=json.loads((ROOT/'contracts/trust/packages.json').read_text())['channels'][channel]
        if not all(trust.get(k,{}).get('fingerprint')for k in ['apt','rpm']):raise RuntimeError('Missing reviewed package trust anchors')
        apt_key=import_key(apt_home,'APT_SIGNING',trust['apt']['fingerprint']);rpm_key=import_key(rpm_home,'RPM_SIGNING',trust['rpm']['fingerprint'])
        apt=snapshot/'apt';pool=apt/'pool/main';binary=apt/f'dists/{suite}/main/binary-amd64';rpm=snapshot/'rpm'
        for p in [pool,binary,rpm]:p.mkdir(parents=True)
        debs=list(source.glob('*.deb'));rpms=list(source.glob('*.rpm'));exes=list(source.glob('*.exe'));appimages=list(source.glob('*.AppImage'))
        if any(len(x)!=1 for x in [debs,rpms,exes,appimages]):raise RuntimeError('Candidate requires exactly one qualified DEB, RPM, AppImage and Windows installer')
        deb=debs[0];deb_version=command(['dpkg-deb','-f',str(deb),'Version']).decode().strip()
        expected=identity['version'].replace('-dev.','~dev.')
        if deb_version!=expected:raise RuntimeError('DEB version does not match candidate')
        shutil.copy2(deb,pool/deb.name)
        packages=command(['dpkg-scanpackages','--arch','amd64','pool/main','/dev/null'],cwd=apt)
        (binary/'Packages').write_bytes(packages);(binary/'Packages.gz').write_bytes(gzip.compress(packages,mtime=0))
        cfg=temp/'apt.conf';cfg.write_text(f'APT::FTPArchive::Release::Origin "Silicium Project";\nAPT::FTPArchive::Release::Suite "{suite}";\nAPT::FTPArchive::Release::Codename "{suite}";\nAPT::FTPArchive::Release::Components "main";\nAPT::FTPArchive::Release::Architectures "amd64";\n')
        release=apt/f'dists/{suite}/Release';release.write_bytes(command(['apt-ftparchive','-c',str(cfg),'release',f'dists/{suite}'],cwd=apt))
        sign(apt_home,apt_key,release,True);sign(apt_home,apt_key,release)
        (release.parent/'Release.asc').rename(release.parent/'Release.gpg')
        (apt/'silicium-packages.asc').write_bytes(command(['gpg','--homedir',str(apt_home),'--armor','--export',apt_key]))
        command(['gpg','--homedir',str(apt_home),'--verify',str(release.parent/'InRelease')])
        (apt/'silicium.sources').write_text(f'Types: deb\nURIs: {base}/apt\nSuites: {suite}\nComponents: main\nArchitectures: amd64\nSigned-By: /etc/apt/keyrings/silicium-{channel}.gpg\n')
        package=rpm/rpms[0].name;shutil.copy2(rpms[0],package)
        env={**os.environ,'GNUPGHOME':str(rpm_home)}
        command(['rpmsign','--define',f'_gpg_name {rpm_key}','--define',f'_gpg_path {rpm_home}','--addsign',str(package)],env=env)
        (rpm/'silicium-rpm-signing.asc').write_bytes(command(['gpg','--homedir',str(rpm_home),'--armor','--export',rpm_key]))
        db=temp/'rpmdb';db.mkdir()
        command(['rpmkeys','--dbpath',str(db),'--import',str(rpm/'silicium-rpm-signing.asc')]);command(['rpmkeys','--dbpath',str(db),'--checksig',str(package)])
        command(['createrepo_c',str(rpm)]);sign(rpm_home,rpm_key,rpm/'repodata/repomd.xml')
        command(['gpg','--homedir',str(rpm_home),'--verify',str(rpm/'repodata/repomd.xml.asc'),str(rpm/'repodata/repomd.xml')])
        (rpm/'silicium-node.repo').write_text(f'[silicium-{channel}]\nname=Silicium Node ({channel})\nbaseurl={base}/rpm\nenabled=1\ngpgcheck=1\nrepo_gpgcheck=1\ngpgkey={base}/rpm/silicium-rpm-signing.asc\nmetadata_expire=300\n')
        suffix='-dev' if channel=='dev' else ''
        for file,ext in [(debs[0],'deb'),(package,'rpm'),(exes[0],'exe'),(appimages[0],'AppImage')]:shutil.copy2(file,snapshot/f'silicium-node-{ "windows" if ext=="exe" else "linux"}{suffix}.{ext}')
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('updates',Path(__file__).with_name('update-manifest.py'));updates=module_from_spec(spec);spec.loader.exec_module(updates)
        updates.build(snapshot,identity,base,json.loads((ROOT/'contracts/trust/update.json').read_text()))
        files={str(p.relative_to(snapshot)):hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.rglob('*') if p.is_file()}
        (snapshot/'snapshot.json').write_text(json.dumps({'schema_version':1,'release_id':rid,'files':files},indent=2))
        with tarfile.open(publish/'packages.tar.gz','w:gz') as tar:tar.add(snapshot,arcname='downloads')
    print('Signed APT/DNF snapshot assembled; installation qualification is mandatory before publication.')

if __name__=='__main__':main()
